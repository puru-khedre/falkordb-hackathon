# FalkorDB core-feature usage in ContextAnchor

_A map of which FalkorDB / openCypher capabilities the project actually exercises,
with code references — for the demo and for judging against Rule #3 ("the product
must break if FalkorDB is removed")._

## Features used (demo highlights)

### 1. Native graph algorithm — `algo.betweenness` (GraphBLAS)
`app/falkor_client.py` → `centrality()`:
```cypher
CALL algo.betweenness({nodeLabels:['Function'], relationshipTypes:['CALLS'],
                       samplingSize:10000, samplingSeed:7})
YIELD node, score RETURN node.fid, node.name, score ORDER BY score DESC LIMIT 5
```
Runs in C/GraphBLAS, not a Python loop. Deterministic (`samplingSeed`). Falls back
to a graph-native upstream-reach traversal only if the procedure is unavailable.
> **Say:** "Chokepoints come from FalkorDB's native betweenness-centrality algorithm."

### 2. Multi-hop variable-length traversal (the "what breaks" core)
`blast_radius()`, `impact_viz()` — `(caller)-[:CALLS*1..3]->(target)` and `*0..3`.
One traversal returns every upstream caller + impacted endpoint.
> **Say:** "The whole blast radius is a single Cypher traversal — no joins, no N+1."

### 3. Multiple graphs in one instance (multi-tenancy)
Every ingested repo is its own graph (`proj_<name>`); a separate `ca_meta` graph holds
the project registry + app config. `db.select_graph(...)` throughout `falkor_client.py`.
> **Say:** "Each codebase is an isolated graph in one FalkorDB; switch projects instantly."

### 4. Graph as live memory — reads AND writes
`MERGE` / `SET` / `DETACH DELETE` create and remove `TeamRule` nodes and `GOVERNS`
edges. Now driven live by the MCP `record_rule` tool (two-way write-back).
> **Say:** "The agent writes new rules back with MERGE — memory grows, it isn't a static file."

### 5. Rich property graph + multi-entity join in one query
6 node labels (`File, Function, Endpoint, Developer, TeamRule, ADR`) and 6 relationship
types (`CONTAINS, CALLS, EXECUTES, AUTHORED, GOVERNS, APPLIES_TO`). `ownership()` stitches
file + owner + ADR with `OPTIONAL MATCH` in one query (6 OPTIONAL MATCHes total).
Aggregations: `count`, `min`, `max`.
> **Say:** "Owner, ADR, rules and callers — answered from one graph, one query."

### 6. openCypher breadth + schema introspection
List predicate `any()`, string functions `toLower` / `CONTAINS` / `coalesce` (the new NL
`search_codebase`), query parameters, `ORDER BY` / `LIMIT`, and procedures
`CALL db.labels / db.relationshipTypes / db.propertyKeys`.

## Not used (honest roadmap — don't claim these)
- **Full-text search index** (`db.idx.fulltext.*`) — search currently uses `toLower CONTAINS` scans.
- **Vector / HNSW semantic search** — not implemented.
- **Indexes / constraints** (`CREATE INDEX`) — none (fine at demo scale).
- **Other algorithms** — only `betweenness`; `algo.pageRank`, BFS, WCC unused.

## Verdict
ContextAnchor uses FalkorDB as a genuine primary database: multi-hop traversal +
native graph algorithm + multiple graphs + read/write graph memory. Remove FalkorDB and
blast radius, chokepoints, rule governance and ownership all stop — there is no second
store. The main unused surfaces are full-text and vector indexes.
