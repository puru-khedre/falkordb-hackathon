# ContextAnchor — Codebase & Architecture Impact Guardian

**Graph Hacks: Context for AI Agents** (WeMakeDevs × FalkorDB)
Tracks entered: **Track 1 (Act on Connected Data)** · **Track 2 (Agent Memory)** · **Track 3 (Company Brain)** — unified in one project.

AI coding agents drift: they break a function three other teams depend on, violate a
team rule nobody told them, and never know who owns the code. ContextAnchor gives an
agent the context it's missing **before it edits**, by querying one **FalkorDB** graph:

1. **What breaks?** — multi-hop `CALLS` traversal + native `algo.betweenness` chokepoints.
2. **What rule forbids it?** — team rules stored as persistent graph memory.
3. **Who owns it, and why?** — owner from real `git log` history, linked to the ADR.

Remove FalkorDB and every one of these stops — there is no second store. **The graph is the product.**

---

## Prerequisites

You only need Docker. Everything else runs inside the containers.

| Requirement | Notes |
|---|---|
| **Docker + Docker Compose v2** | Docker Desktop (macOS/Windows) or Docker Engine + `docker compose` (Linux). That's the only hard dependency. |
| **Free ports** | `8000` (web), `9000` (MCP/SSE), `6379` (FalkorDB). Stop anything using them first. |
| **~2 GB free RAM & disk** | For the FalkorDB + two app containers and the first image build. |
| **Internet (first build only)** | To pull the `falkordb/falkordb` image and `pip install` dependencies. After that it runs offline. |

No Python, Node, or database install is required on the host.

### Credentials (optional — the app runs fully offline without them)

ContextAnchor works with **zero keys**: the sample graph auto-seeds and every verdict
comes straight from FalkorDB (offline graph mode). Keys only add extras:

- **`NVIDIA_API_KEY`** — enables LLM-written natural-language summaries (NVIDIA NIM). Without it, a deterministic graph template is used.
- **`GITHUB_TOKEN`** — only needed to ingest **private** repos.

Add either in the UI (**Manage → Settings**) or in a `.env` file (see `.env.example`).

> 📩 **For judges:** if you'd like to review the LLM-narration feature without creating
> your own NVIDIA account, I can share a pre-provisioned key — please contact me at
> **[ADD YOUR EMAIL / DISCORD HANDLE HERE]**. The app is fully functional for review
> without it.

---

## Quick start (one command)

```bash
git clone <this-repo-url>
cd contextanchor         # or falkordb-hackathon
docker compose up --build
```

Then open:
- **Web dashboard** → http://localhost:8000
- **Landing / about page** → http://localhost:8000/landing
- **In-app docs & tutorials** → http://localhost:8000/docs
- **MCP server (SSE)** → http://localhost:9000/sse

The sample microservices graph auto-seeds on first boot, so the dashboard is live
immediately — click a **Try it** scenario or the **Guided demo tour**.

### Verify the install (optional but recommended)

```bash
# tool logic against the live graph + end-to-end over the MCP SSE server
docker compose exec mcp python -m app.selftest all
```
Expect `GRAPH TESTS: PASS` and `SSE TESTS: PASS`.

### Point it at your own code
- **UI:** paste a GitHub URL (e.g. `https://github.com/pallets/flask`) or a local path into **Codebase → Ingest**.
- **CLI:** `docker compose exec web python -m app.ingest --repo https://github.com/user/repo`

Python repos are parsed precisely with the stdlib `ast`; JS/TS/Go/Java use a lightweight
regex pass. Ownership comes from the repo's real `git log`.

---

## What it does (capabilities)

- **Blast-radius analysis** — one click shows every upstream caller and live API endpoint a function change would affect, as a focused, readable graph.
- **Chokepoint detection** — native betweenness centrality ranks the real single points of failure in the call graph.
- **Team rules as memory** — architecture/convention rules live as graph nodes and are enforced on every check; agents can also **write new rules back**.
- **Ownership + ADRs** — the code owner (from git) and the architecture decision behind the code, in the same answer.
- **Grounded Ask** — natural-language questions answered strictly from graph facts, so the LLM can't hallucinate.
- **Any repo, multi-project** — each repo is its own FalkorDB graph; switch between them.
- **Developer & agent integrations** — MCP server, GitHub PR impact bot, pre-commit/CI gate, and auto-generated `CLAUDE.md` / `.cursorrules`.

---

## How it uses FalkorDB

FalkorDB is the only datastore. Every feature is a graph operation:

| Capability | FalkorDB feature |
|---|---|
| Blast radius | Multi-hop variable-length traversal `(:Function)-[:CALLS*1..3]->(:Function)` |
| Chokepoints | Native GraphBLAS algorithm `CALL algo.betweenness(... samplingSeed:7)` |
| Multi-project | Multiple graphs in one instance (`proj_<name>` + a `ca_meta` registry graph) |
| Agent memory | `MERGE` / `SET` / `DETACH DELETE` on `TeamRule` nodes & `GOVERNS` edges |
| Owner + ADR | `OPTIONAL MATCH` joining `Developer`, `File`, `ADR` in a single query |
| Discovery (NL search) | List predicate `any()` + `toLower`/`CONTAINS` across labels |
| Schema | `CALL db.labels / db.relationshipTypes / db.propertyKeys` |

A full breakdown with code references is in [`docs/falkordb_feature_usage.md`](docs/falkordb_feature_usage.md).

### Graph data model
```
        (:Developer)                         (:ADR)
             |                                  |
         [:AUTHORED]                       [:APPLIES_TO]
             v                                  v
(:TeamRule)-[:GOVERNS]->(:File)-[:CONTAINS]->(:Function)
             |                                  ^  |
             +------[:GOVERNS]------------------+  | [:CALLS*1..4]
                                                   v
(:Endpoint)-[:EXECUTES]------------------------>(:Function)
```
Nodes: `File`, `Function` (keyed by `fid = file::name`), `Endpoint`, `Developer`, `TeamRule`, `ADR`.
Relationships: `CONTAINS`, `CALLS`, `EXECUTES`, `AUTHORED`, `GOVERNS`, `APPLIES_TO`.

### Key Cypher
```cypher
-- Blast radius (Track 1)
MATCH (t:Function {fid:$fid})
MATCH p = (c:Function)-[:CALLS*1..3]->(t)
RETURN c.name, c.file, min(length(p)) AS hops ORDER BY hops;

-- Chokepoint, native algorithm (Track 1)
CALL algo.betweenness({nodeLabels:['Function'], relationshipTypes:['CALLS'],
                       samplingSize:10000, samplingSeed:7})
YIELD node, score RETURN node.name, score ORDER BY score DESC LIMIT 5;

-- Owner + ADR in one traversal (Track 3)
MATCH (:Function {fid:$fid})<-[:CONTAINS]-(f:File)
OPTIONAL MATCH (d:Developer)-[a:AUTHORED]->(f)
OPTIONAL MATCH (adr:ADR)-[:APPLIES_TO]->(f)
RETURN d.name, a.commits, adr.id, adr.title;
```

---

## MCP server — use it from your AI agent

ContextAnchor **is** an MCP (Model Context Protocol) server so a coding agent can pull
real context before editing. It exposes **11 tools, 2 resources and 2 prompts** over
**SSE** (`http://localhost:9000/sse`) or **stdio** (`python -m app.mcp_server --stdio`).

**Tools**
| Tool | What it returns |
|---|---|
| `analyze_change(function)` | Verdict (BLOCK/REVIEW/SAFE) + blast radius + rules + owner + chokepoint |
| `blast_radius(function)` | Upstream callers (1–4 hops) + impacted API endpoints |
| `team_rules(function)` | Team/architecture rules governing the function |
| `find_owner(function)` | Code owner (from git) + applicable ADR |
| `chokepoints()` | Top betweenness-centrality single points of failure |
| `list_functions()` / `list_projects()` | Graph-wide discovery helpers |
| `record_rule(rule_text, severity, …)` | **Write** a new rule/decision into graph memory (two-way) |
| `analyze_diff(diff)` | PR-level verdict from a full unified diff (combined blast radius, rules, reviewers, markdown) |
| `search_codebase(query)` | NL/keyword discovery across functions, files, endpoints, rules, ADRs |
| `get_refactor_guide(function)` | Actionable safe-refactor checklist for a BLOCK verdict |

**Resources** (IDEs read these without a tool call)
`contextanchor://projects` · `contextanchor://rules/{project}`

**Prompts** (ready-made agent workflows)
`safe_refactor(function)` · `review_patch(diff)`

### Connect your client
**Claude Code**
```bash
claude mcp add --transport sse contextanchor http://localhost:9000/sse
```
**Cursor** — add to `~/.cursor/mcp.json`:
```json
{ "mcpServers": { "contextanchor": { "url": "http://localhost:9000/sse" } } }
```
**Claude Desktop** — add to `claude_desktop_config.json` (bridges SSE over stdio):
```json
{ "mcpServers": { "contextanchor": { "command": "npx", "args": ["-y","mcp-remote","http://localhost:9000/sse"] } } }
```
Full per-client setup, stdio config and troubleshooting are in **http://localhost:8000/docs** (Tutorial 3).

---

## Other integrations
- **GitHub PR impact bot** — `.github/workflows/contextanchor.yml` comments blast radius, violated rules and reviewers on every PR. Set `CA_STRICT=1` to fail on BLOCK.
- **Pre-commit / CI gate** — `python -m app.check <function>` exits 1 on BLOCK.
- **Fresh agent rules** — `GET /api/export/rules?format=claude|cursor` regenerates `CLAUDE.md` / `.cursorrules` from the graph.
- **Claude Code pre-edit hook** — `integrations/claude-code/` warns/blocks before the agent edits risky code.

---

## Project structure
```
app/
  main.py          FastAPI routes + serves the web UI
  falkor_client.py All FalkorDB / Cypher queries (the data layer)
  agent.py         Per-function analysis + verdict + narration
  ingest.py        Repo parsing (ast / regex) + git owners
  seed_data.py     Curated sample microservices graph
  mcp_server.py    MCP server — 11 tools, 2 resources, 2 prompts
  diff_analyze.py  Unified-diff → PR-level impact
  genrules.py      CLAUDE.md / .cursorrules generator
  check.py         CLI gate for pre-commit / CI
  selftest.py      Live tool + SSE verification
  static/          Dashboard, landing, docs, manage (Cytoscape + dagre)
integrations/      Claude Code hook + git pre-commit hook
docs/              Handover, FalkorDB feature map, this project's docs
```

## Troubleshooting
- **Port already in use** → free `8000` / `9000` / `6379`, or change the mappings in `docker-compose.yml`.
- **MCP tools don't appear in the client** → confirm the stream: `curl -N http://localhost:9000/sse`; then fully restart the client.
- **Ingested repo looks stale after an update** → re-ingest from **Manage → Refresh**.
- **MCP container won't start** → `docker compose build --no-cache mcp`; test with the official MCP SDK client (`mcp.client.sse`), not the stand-alone fastmcp client.

## Tech stack
Python 3.12 · FastAPI · **FalkorDB** (`falkordb` 1.8) · FastMCP · Cytoscape.js + dagre · NVIDIA NIM (optional) · Docker Compose.

## AI disclosure
Built during the hackathon with help from an AI assistant (Claude) for scaffolding and
code. All graph modeling, Cypher, algorithm choices and architecture were directed and
reviewed by the author, who can explain every part. Only public / synthetic / self-owned
data is used.
