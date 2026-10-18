# FalkorDB Developer Cheat Sheet & Hackathon Playbook

This document contains exact syntax, working code snippets, and implementation blueprints for building an AI Agent using FalkorDB.

---

## 1. Quick Setup (Docker & Python)

### Docker Compose (`docker-compose.yml`)
Run FalkorDB locally with one command:
```yaml
version: '3.8'

services:
  falkordb:
    image: falkordb/falkordb:latest
    container_name: falkordb_instance
    ports:
      - "6379:6379"
    volumes:
      - falkor_data:/data

volumes:
  falkor_data:
```

### Python Connection (`falkordb-py`)
Install the official client:
```bash
pip install falkordb
```

Connect and query:
```python
from falkordb import FalkorDB

# Connect to local FalkorDB instance
db = FalkorDB(host='localhost', port=6379)

# Select or create an isolated graph (Multi-graph support)
graph = db.select_graph('hackathon_graph')

# Execute Cypher
res = graph.query("""
    CREATE (u:User {id: 'u1', name: 'Rahul'})-[:ROLE]->(r:Role {title: 'Dev'})
    RETURN u.name, r.title
""")

for record in res.result_set:
    print(record[0], record[1])
```

---

## 2. FalkorDB Superpower: Hybrid Search (Vector + Graph)

FalkorDB has built-in **HNSW vector search**. You don't need a separate vector database (like Pinecone or Chroma).

### A. Create a Vector Index on Nodes
```cypher
CREATE VECTOR INDEX FOR (c:Chunk) ON (c.embedding) 
OPTIONS {dimension: 1536, similarityFunction: 'cosine'};
```
*(Options for `similarityFunction` are `'cosine'` or `'euclidean'`)*.

### B. Insert Nodes with Vector Embeddings
```python
# Embedding array from OpenAI / SentenceTransformers
embedding = [0.012, -0.045, 0.089, ...]  # 1536 floats

graph.query("""
    CREATE (c:Chunk {id: 'c1', text: 'Auth service crashed on port 8080', embedding: vecf32($vec)})
""", {'vec': embedding})
```

### C. Query: Vector Search + 2-Hop Graph Traversal in ONE Query
```cypher
// 1. Vector similarity to find closest incident
CALL db.idx.vector.queryNodes('Chunk', 'embedding', 3, vecf32($query_vec))
YIELD node AS chunk, score

// 2. Immediate graph expansion from that node
MATCH (chunk)<-[:HAS_CHUNK]-(inc:Incident)-[:AFFECTS]->(s:Service)-[:DEPENDS_ON]->(db:Database)
RETURN inc.title, s.name, db.name, score
ORDER BY score DESC;
```

---

## 3. FalkorDB Built-in Graph Algorithms (`CALL algo.*`)

These run natively in C/GraphBLAS with sub-millisecond execution.

### A. PageRank (Find the most influential or critical node)
Identifies the most central system, package, or person based on incoming links:
```cypher
CALL algo.pageRank('Service', 'CALLS') 
YIELD node, score
RETURN node.name AS service_name, score
ORDER BY score DESC 
LIMIT 5;
```

### B. Betweenness Centrality (Find Bottlenecks / Chokepoints)
Finds the single point of failure (node that sits on the most shortest paths):
```cypher
CALL algo.betweennessCentrality('Service', 'DEPENDS_ON') 
YIELD node, score
RETURN node.name AS bottleneck_service, score
ORDER BY score DESC 
LIMIT 3;
```

### C. Shortest Path (Dependency or Blast Radius Chain)
```cypher
MATCH (start:Service {name: 'PaymentGateway'}), (end:Database {name: 'UsersDB'})
MATCH p = shortestPath((start)-[:DEPENDS_ON*..10]->(end))
RETURN p;
```

---

## 4. Graph Schema Discovery (How LLM Inspects the Graph)

To let an LLM agent write Cypher queries dynamically, it needs to know the schema.

### Schema Introspection Queries
```cypher
// Get all node labels
CALL db.labels();

// Get all relationship types
CALL db.relationshipTypes();

// Get all property keys
CALL db.propertyKeys();
```

### Python Function to Format Schema for LLM System Prompt
```python
def get_graph_schema(graph):
    labels = [r[0] for r in graph.query("CALL db.labels()").result_set]
    rels = [r[0] for r in graph.query("CALL db.relationshipTypes()").result_set]
    props = [r[0] for r in graph.query("CALL db.propertyKeys()").result_set]
    return f"""
Graph Schema:
- Node Labels: {labels}
- Relationships: {rels}
- Available Properties: {props}
"""
```

---

## 5. Agent Tool Pattern (ReAct Agent Example)

When the agent wants to query FalkorDB, define a clean tool:

```python
from falkordb import FalkorDB

db = FalkorDB(host='localhost', port=6379)
graph = db.select_graph('agent_context')

def query_falkordb_tool(cypher_query: str) -> str:
    """Executes a Cypher query on FalkorDB and returns JSON results."""
    try:
        res = graph.query(cypher_query)
        rows = [record for record in res.result_set]
        return {"status": "success", "row_count": len(rows), "data": rows}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def find_chokepoint_tool() -> str:
    """Runs Betweenness Centrality to find single points of failure."""
    query = "CALL algo.betweennessCentrality('Service', 'DEPENDS_ON') YIELD node, score RETURN node.name, score ORDER BY score DESC LIMIT 3"
    res = graph.query(query)
    return [{"service": r[0], "bottleneck_score": r[1]} for r in res.result_set]
```

---

## 6. Frontend Graph Data Format (For Cytoscape.js or Vis.js)

To show a live glowing graph in the UI during the demo video:

```python
def get_visualization_payload(graph, cypher_query="MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50"):
    res = graph.query(cypher_query)
    nodes = {}
    edges = []
    
    for row in res.result_set:
        src, rel, dest = row[0], row[1], row[2]
        
        # Node format
        nodes[src.id] = {"id": str(src.id), "label": list(src.labels)[0] if src.labels else "Node", "title": src.properties.get("name", str(src.id))}
        nodes[dest.id] = {"id": str(dest.id), "label": list(dest.labels)[0] if dest.labels else "Node", "title": dest.properties.get("name", str(dest.id))}
        
        # Edge format
        edges.append({
            "from": str(src.id),
            "to": str(dest.id),
            "label": rel.relation,
            "properties": rel.properties
        })
        
    return {
        "nodes": list(nodes.values()),
        "edges": edges
    }
```

---

## 7. Complete Hackathon Track Blueprints

### Blueprint 1: Track 1 (Agents That Act on Connected Data)
**Project Title:** IncidentPulse / BlastRadius Agent
- **Nodes:**
  - `(:Service {name, port, status})`
  - `(:Database {name, type})`
  - `(:Commit {hash, author, message, timestamp})`
  - `(:Alert {id, severity, message, timestamp})`
- **Edges:**
  - `(:Service)-[:DEPENDS_ON]->(:Service|Database)`
  - `(:Commit)-[:DEPLOYED_TO]->(:Service)`
  - `(:Alert)-[:TRIGGERED_ON]->(:Service)`
  - `(:Developer)-[:AUTHORED]->(:Commit)`
- **Agent Workflow:**
  1. Receives an alert: "PaymentService error rate > 15%".
  2. Runs 2-hop Cypher to find all downstream dependent services.
  3. Runs Shortest Path / Commit lookup to find the latest deployment.
  4. Runs `algo.betweennessCentrality` to check if PaymentService is a global bottleneck.
  5. Outputs automated mitigation plan + root cause commit.

### Blueprint 2: Track 2 (Agent Memory and Coordination)
**Project Title:** Synapse - Multi-Agent Swarm Memory
- **Topology:**
  - `db.select_graph('shared_team_memory')`
  - `db.select_graph('researcher_agent_memory')`
  - `db.select_graph('planner_agent_memory')`
- **Nodes:**
  - `(:Session {id, created_at})`
  - `(:Fact {text, confidence, source})`
  - `(:Decision {choice, rationale, timestamp})`
  - `(:Task {id, status, assigned_to})`
- **Edges:**
  - `(:Session)-[:LEARNED]->(:Fact)`
  - `(:Fact)-[:LED_TO]->(:Decision)`
  - `(:Decision)-[:SPAWNED_TASK]->(:Task)`
- **Agent Workflow:**
  1. Researcher agent reads web/docs, stores extracted facts as nodes.
  2. Planner agent queries `shared_team_memory`, checks uncompleted tasks, and executes them without context loss across chat sessions.

### Blueprint 3: Track 3 (Company Brain)
**Project Title:** OrgMind - Unified Company Knowledge & Ownership Graph
- **Nodes:**
  - `(:Employee {name, role, email})`
  - `(:Project {name, repo_url, status})`
  - `(:Doc {title, url, category})`
  - `(:DecisionRecord {title, status, date})`
- **Edges:**
  - `(:Employee)-[:OWNS]->(:Project)`
  - `(:Employee)-[:WROTE]->(:Doc)`
  - `(:Doc)-[:DEFINES]->(:Project)`
  - `(:DecisionRecord)-[:IMPACTS]->(:Project)`
- **Agent Workflow:**
  1. User asks: "Who should I talk to about changing the auth token expiration, and why was it set to 15 mins?"
  2. Agent executes Cypher multi-hop query: `(Doc)-[:DEFINES]->(:Project {name: 'Auth'})<-[:OWNS]-(Employee)`.
  3. Returns author name, meeting notes link, and exact rationale.
