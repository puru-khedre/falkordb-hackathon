# MASTER HANDOVER DOCUMENT: ContextAnchor
**Target Hackathon:** Graph Hacks: Context for AI Agents (WeMakeDevs & FalkorDB)  
**Deadline:** October 18, 2026 at 11:59 PM IST (Urgent: ~5 hours remaining)  
**Total Prize Pool:** $20,000 (iPhone 18 Pro, PS5 with GTA VI, M6 Mac Mini, AirPods 5)  
**Project Selected:** **`ContextAnchor`** (The Visual Codebase & Architecture Impact Guardian)  
**Primary Language/Stack:** Python (FastAPI) + FalkorDB + Tailwind CSS + Cytoscape.js

---

## 1. Hackathon Requirements & Submission Checklist

Every submission must include (Rule #10):
1. **Public GitHub Repository** (Do not execute remote push git commands; let the user push).
2. **README.md** with:
   - Setup instructions (Single command `docker compose up`).
   - Graph data model diagram & schema explanation.
   - Cypher queries and graph algorithms used.
   - The tracks entered: **Track 1, Track 2, and Track 3** (The project unifies all three).
   - Disclosure of AI assistant use (Rule #11).
3. **Demo Video (2–3 minutes):**
   - **Crucial Constraint:** The user CANNOT record voiceover.
   - The demo must be **100% visual and silent-friendly** (ambient background music, on-screen text banners, glowing nodes, and 1-click interactive demo scenarios).
4. **FalkorDB as Primary Database:**
   - Rule #3: The product MUST break if FalkorDB is removed. It relies on multi-hop traversals and native graph algorithms (`algo.betweennessCentrality`, `algo.pageRank`).

---

## 2. Why This Project Was Chosen (The 3 User Criteria)

The user evaluated 6 different real-world ideas against 3 strict constraints:
1. **Valid & Heavy FalkorDB Use:** Relies directly on Cypher multi-hop call graphs and C-based GraphBLAS algorithms.
2. **Zero External Cloud Accounts / Frictionless Setup:** No AWS, Datadog, PagerDuty, or Jira cloud setup. Everything is 100% local and self-contained.
3. **Silent Visual Demo Appeal:** 1-click scenario buttons that visually animate the graph, glowing affected nodes in neon red (blast radius) and author nodes in green.

---

## 3. The Core Concept: How All 3 Tracks Are Unified

`ContextAnchor` is an architecture governance and blast-radius engine that anchors AI agents and developers to team rules and code dependencies:

```
                      [ UNIFIED FALKORDB GRAPH ]

     ┌────────────────────────────┼────────────────────────────┐
     ▼                            ▼                            ▼
[Track 1: Act on Data]    [Track 2: Agent Memory]    [Track 3: Company Brain]
 "Blast Radius & Safety"   "Team Rules & Constraints" "Ownership & Architecture"
  - Multi-hop call graph    - Persistent team memory   - File & function owners
  - algo.betweenness          across chat sessions     - Git PR history
    (Bottleneck score)      - "Max 50% discount cap"   - Architecture Decision
  - Downstream API impact   - "No raw SQL queries"       Records (ADRs)
```

### The Unified User Workflow:
User clicks or asks: *"I want to modify the `calculate_discount()` function in `billing.py`."*
1. **Track 1 (Blast Radius):** FalkorDB runs a 2-hop Cypher traversal finding downstream APIs (`/checkout`, `/invoices`) and runs `algo.betweennessCentrality` to calculate a high impact score.
2. **Track 2 (Team Memory):** Checks persistent team rules node: Recalls *"Rule #4 (Sprint 18): Discounts cannot exceed 50%"*.
3. **Track 3 (Company Brain):** Checks ownership: *"Originally authored by Priya in PR #102 for Jira #PAY-88"*.
4. **Result:** Visual graph turns affected nodes **Neon Red**, displays warning badge for Rule #4, and suggests contacting Priya.

---

## 4. Graph Schema Specification

### Node Labels:
- `(:File {path: String, module: String})`
- `(:Function {name: String, file: String, line_no: Int, is_entrypoint: Bool})`
- `(:Endpoint {route: String, method: String, service: String})`
- `(:Developer {name: String, email: String, role: String})`
- `(:TeamRule {id: String, rule_text: String, severity: String, created_at: String})`
- `(:ADR {id: String, title: String, decision: String, status: String})`

### Relationship Types:
- `(:File)-[:CONTAINS]->(:Function)`
- `(:Function)-[:CALLS]->(:Function)`
- `(:Endpoint)-[:EXECUTES]->(:Function)`
- `(:Developer)-[:AUTHORED {commits: Int, last_touched: String}]->(:File|Function)`
- `(:TeamRule)-[:GOVERNS]->(:Function|File)`
- `(:ADR)-[:APPLIES_TO]->(:Function|File)`

---

## 5. Key Cypher Queries & Graph Algorithms

### Query 1: Multi-Hop Blast Radius (Track 1)
```cypher
MATCH (target:Function {name: $func_name})
MATCH path = (caller:Function)-[:CALLS*1..4]->(target)
OPTIONAL MATCH (ep:Endpoint)-[:EXECUTES]->(caller)
RETURN caller.name AS affected_function, 
       caller.file AS file, 
       ep.route AS impacted_api,
       length(path) AS hop_depth
ORDER BY hop_depth ASC;
```

### Query 2: Betweenness Centrality (Find Bottleneck / Chokepoint)
```cypher
CALL algo.betweennessCentrality('Function', 'CALLS') 
YIELD node, score
RETURN node.name AS function_name, node.file AS file, score
ORDER BY score DESC 
LIMIT 5;
```

### Query 3: Check Team Rules & Architecture Memory (Track 2)
```cypher
MATCH (target:Function {name: $func_name})
MATCH (rule:TeamRule)-[:GOVERNS]->(target)
RETURN rule.id AS rule_id, rule.rule_text AS rule, rule.severity AS severity;
```

### Query 4: Trace Ownership & ADR Context (Track 3)
```cypher
MATCH (target:Function {name: $func_name})<-[:CONTAINS]-(f:File)
OPTIONAL MATCH (dev:Developer)-[a:AUTHORED]->(f)
OPTIONAL MATCH (adr:ADR)-[:APPLIES_TO]->(f)
RETURN dev.name AS primary_author, 
       a.commits AS commit_count, 
       adr.id AS adr_id, 
       adr.title AS adr_title, 
       adr.decision AS decision;
```

---

## 6. Verified Environment & Working Credentials

- **Docker:** Installed & working (`Docker version 29.7.2`)
- **Python:** Python 3.9.6 installed
- **Node.js:** v22.22.3 installed
- **NVIDIA NIM API Key (100% Tested & Verified Working):**
  - Key: `<stored in .env as NVIDIA_API_KEY>`
  - Base URL: `https://integrate.api.nvidia.com/v1/chat/completions`
  - Tested Model: `meta/llama-3.2-11b-vision-instruct` (Returns successful text completions)

---

## 7. Zero-Friction Evaluator Experience (Judges' Workflow)

To guarantee that judges score the project top marks without technical friction:
1. **Single Command Start:**
   ```bash
   docker compose up
   ```
2. **Automatic Data Seeding:**
   - When the backend boots, if FalkorDB is empty, `seed_data.py` runs automatically.
   - Loads a realistic microservices codebase graph (Auth Service, Payment Service, Orders, Database queries, Git history, and Team Rules).
3. **Ingest Custom Repositories:**
   - CLI: `python ingest.py --repo /path/to/any/codebase`
   - Built with Python's standard `ast` module (zero external compiler dependencies).
4. **Offline / Fallback Graph-Engine Mode:**
   - If the judge does not provide an API key, the system does NOT crash.
   - It runs deterministic Cypher queries and algorithm procedures directly on FalkorDB, returning accurate JSON results and highlighting nodes on the UI graph.
5. **Pre-configured 1-Click Interactive Demo Buttons:**
   At the top of the web UI:
   - Button 1: `[Scenario 1: Refactor calculate_discount (Payment Service)]`
   - Button 2: `[Scenario 2: Architecture Rule Violation (Token Handling)]`
   - Button 3: `[Scenario 3: Ownership & ADR Audit (Auth Handler)]`

---

## 8. Recommended File Structure for the Implementation

```
radiant-maxwell/
├── docker-compose.yml           # Runs falkordb (6379) + web app (8000)
├── Dockerfile                   # Python 3.9 container for FastAPI backend
├── requirements.txt             # fastapi, uvicorn, falkordb, httpx, jinja2
├── .env.example                 # NVIDIA_API_KEY, FALKORDB_HOST, FALKORDB_PORT
├── app/
│   ├── main.py                  # FastAPI server & API endpoints
│   ├── falkor_client.py         # FalkorDB connection, queries, & algorithms
│   ├── ingest.py                # Python AST code parser (builds graph from code)
│   ├── seed_data.py             # Realistic sample repo graph data loader
│   ├── agent.py                 # LLM ReAct agent (NVIDIA model + Cypher tools + fallback)
│   └── static/
│       ├── index.html           # Modern dark-mode dashboard (Tailwind CSS)
│       ├── app.js               # Cytoscape.js interactive glowing graph & event handlers
│       └── styles.css           # Neon glow styles for nodes and badges
├── sample_repo/                 # The bundled sample microservices repo
│   ├── auth_service.py
│   ├── billing_service.py
│   ├── order_service.py
│   └── database.py
├── docs/                        # All research and design guides
│   ├── falkordb_hackathon_guide.md
│   ├── falkordb_developer_cheat_sheet.md
│   ├── all_six_ideas_internet_validated.md
│   └── master_handover_contextanchor.md
└── README.md                    # Comprehensive hackathon README with visual diagrams
```

---

## 9. Immediate Next Actions for the Implementing Agent
1. Create `docker-compose.yml` to spin up `falkordb/falkordb:latest` on port `6379`.
2. Build `app/falkor_client.py` and `app/seed_data.py` to populate the sample graph.
3. Build `app/main.py` with the 3 scenario endpoints and graph visualization payload.
4. Build `app/static/index.html` with Cytoscape.js to render the glowing code graph.
5. Verify the 1-click demo buttons work seamlessly end-to-end.
6. Write the final `README.md` and demo video outline.
