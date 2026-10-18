# ContextAnchor — Codebase & Architecture Impact Guardian

**Graph Hacks: Context for AI Agents** (WeMakeDevs — FalkorDB)
Tracks: **Track 1 (Act on Connected Data)**, **Track 2 (Agent Memory)**, **Track 3 (Company Brain)** — unified.

AI coding agents drift: they break a function 3 other teams depend on, violate a
team rule nobody told them, and never know who owns the code. ContextAnchor gives
an agent that missing context **before it edits** by querying one FalkorDB graph:

1. **What breaks?** — multi-hop call-graph traversal + `algo.betweenness` chokepoint.
2. **What rule forbids it?** — team rules stored as persistent graph memory.
3. **Who owns it, and why?** — owner from **real git history** + the ADR.

Remove FalkorDB and every one of these stops — there is no second store. The
graph *is* the product (Rule #3).

---

## This is a real product, not a demo

- **Ingest any real Python repo** by GitHub URL or local path. The call graph is
  parsed with the stdlib `ast`; **ownership comes from the repo's actual
  `git log`** (real authors, commit counts, last-touched), and FastAPI/Flask
  route decorators become live `Endpoint` nodes.
- **Multi-project** — each repo is its own FalkorDB graph; switch between them.
- **Your AI agent uses it live** through the built-in **MCP server** (below).
- **Gate real changes** from the terminal / pre-commit with the CLI.
- The bundled sample microservices graph is just a zero-setup way to try it.

---

## Quick start

```bash
docker compose up --build
```
- Web dashboard — **http://localhost:8000**
- MCP server (SSE) — **http://localhost:9000/sse**

The sample graph auto-seeds on first boot, so the UI is live immediately. No API
key is required — without one it runs in **offline graph mode** (verdicts come
straight from FalkorDB). Add `NVIDIA_API_KEY` to `.env` for LLM-written summaries.

> **Explore the app:** a guided landing page at `/landing`, and full in-app **docs & tutorials** at `/docs` — including step-by-step MCP setup for Claude Code, Cursor and Claude Desktop, an environment-variable reference, and troubleshooting.

### Point it at your own code
- **UI:** paste a GitHub URL (e.g. `https://github.com/pallets/flask`) or a local
  path into **Codebase — Ingest**.
- **CLI:** `docker compose exec web python -m app.ingest --repo https://github.com/user/repo`

---

## Use it from an AI agent (MCP)

ContextAnchor is an MCP server. Point Cursor / Claude Desktop / Claude Code at it
and the agent can call these tools before editing code:

`analyze_change(function)` — `blast_radius` — `team_rules` — `find_owner`
`chokepoints` — `list_functions` — `list_projects`

**SSE (running via docker compose):**
```json
{ "mcpServers": { "contextanchor": { "url": "http://localhost:9000/sse" } } }
```
**stdio (local):** `python -m app.mcp_server --stdio`

Typical agent flow: *"edit `calculate_discount`"* — agent calls
`analyze_change("calculate_discount")` — gets `BLOCK` + blast radius + RULE-4 +
owner — writes the compliant change instead.

## Gate a change in git (pre-commit / CI)

```bash
python -m app.check calculate_discount      # exit 1 on BLOCK
```

---

## Graph data model

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

| Node | Key properties |
|---|---|
| `File` | path, module |
| `Function` | name, file, line_no, is_entrypoint |
| `Endpoint` | route, method, service |
| `Developer` | name, email, role |
| `TeamRule` | id, rule_text, severity, created_at |
| `ADR` | id, title, decision, status |

Relationships: `CONTAINS`, `CALLS`, `EXECUTES`, `AUTHORED` (commits, last_touched),
`GOVERNS`, `APPLIES_TO`.

---

## Cypher & algorithms

**Blast radius (Track 1):**
```cypher
MATCH (target:Function {name:$name})
MATCH p = (caller:Function)-[:CALLS*1..4]->(target)
WITH caller, min(length(p)) AS depth
RETURN caller.name, caller.file, depth ORDER BY depth;
```
**Chokepoint (native GraphBLAS algorithm, deterministic seed):**
```cypher
CALL algo.betweenness({nodeLabels:['Function'], relationshipTypes:['CALLS'],
                       samplingSize:10000, samplingSeed:7})
YIELD node, score RETURN node.name, score ORDER BY score DESC LIMIT 5;
```
(Falls back to a graph-native upstream-reach traversal if the procedure is absent.)

**Rules (Track 2):**
```cypher
MATCH (rule:TeamRule)-[:GOVERNS]->(:Function {name:$name})
RETURN rule.id, rule.rule_text, rule.severity;
```
**Ownership + ADR (Track 3):**
```cypher
MATCH (:Function {name:$name})<-[:CONTAINS]-(f:File)
OPTIONAL MATCH (dev:Developer)-[a:AUTHORED]->(f)
OPTIONAL MATCH (adr:ADR)-[:APPLIES_TO]->(f)
RETURN dev.name, a.commits, adr.id, adr.title;
```

---

## Architecture
```
Browser (Cytoscape.js)        AI agent (Cursor/Claude)
        │ HTTP/JSON                   │ MCP (SSE/stdio)
   FastAPI (app/main.py)        app/mcp_server.py
        └────────────┬───────────────┘
                 app/agent.py  ──►  FalkorDB  (Cypher + algo.*)
                      │
             NVIDIA NIM LLM (optional narration; graph-template fallback)
```
Python 3.12 · FastAPI · FalkorDB · Cytoscape.js · MCP · Docker Compose.

## AI disclosure
Built during the hackathon with help from an AI assistant (Claude) for scaffolding
and code. All graph modeling, Cypher, algorithm choices and architecture were
directed and reviewed by the author, who can explain every part. Only public /
synthetic / self-owned data is used.

---

## Developer & AI-harness integrations

ContextAnchor plugs into where developers and their AI agents actually work.

**1. GitHub PR Impact Bot** — `.github/workflows/contextanchor.yml`
On every pull request a FalkorDB service spins up, the repo is ingested, the PR
diff is mapped to functions, and a comment is posted with the combined blast
radius, violated team rules, and the code owners to tag as reviewers. Set
`CA_STRICT=1` to fail the check on a BLOCK verdict.

**2. Diff-aware analysis** — `POST /api/analyze_diff`
Feed a unified diff; ContextAnchor maps changed hunks to functions (via graph
line numbers) and returns the PR-level verdict, blast radius, rules and reviewers.
Also `POST /api/analyze_file` for a whole file.

**3. Auto-generated agent rules** — `GET /api/export/rules?format=claude|cursor`
Generates an always-fresh `CLAUDE.md` / `.cursorrules` from the graph (hard rules,
chokepoints to edit carefully, ownership, API entrypoints) so the agent's base
context never rots.
```bash
python -m app.genrules --project proj_myrepo --format claude > CLAUDE.md
```

**4. Live pre-edit hooks** — `integrations/`
- **Claude Code**: `integrations/claude-code/` — a PreToolUse hook warns (and
  blocks on BLOCK) before the agent edits risky code. Merge `settings.json` into
  your repo's `.claude/settings.json`.
- **git pre-commit**: `integrations/git-hooks/pre-commit` — blocks a commit whose
  staged diff hits a BLOCK; override with `git commit --no-verify`.

Closed loop: new rules can be written back into the graph via the REST
`POST /api/rule` endpoint (or the dashboard's **Add a team rule**), so the team's
memory grows over time.
