# ContextAnchor  Handover (current state)

> For a fresh AI agent / new account continuing this project. The full code is on
> disk; read this + the code and you can continue without the chat history.

## What it is
**ContextAnchor**  a codebase & architecture impact guardian for the
**Graph Hacks: Context for AI Agents** hackathon (WeMakeDevs x FalkorDB,
deadline 18 Oct 2026 11:59 PM IST). Before a function is changed it answers, off a
single **FalkorDB** graph:
1. What breaks? (multi-hop CALLS traversal + `algo.betweenness` chokepoint)
2. What team rule does it violate? (TeamRule nodes = graph memory)
3. Who owns it & why? (Developer from real git history + ADR)
Unifies all 3 hackathon tracks. If FalkorDB is removed, nothing works (Rule #3).

## Stack
Python 3.12 - FastAPI - FalkorDB (falkordb 1.8) - Cytoscape.js + dagre - fastmcp -
Docker Compose. LLM = NVIDIA NIM (optional; graph-template fallback).

## Run
```bash
docker compose up --build        # web :8000, mcp(SSE) :9000, falkordb :6379
```
Sample graph auto-seeds (and auto-reseeds if schema is outdated  see startup in
app/main.py). No API key needed (offline graph mode); set LLM/GitHub in the UI
(Manage -> Settings, stored in FalkorDB `ca_meta`) or via .env.

## File map
- `app/main.py`          FastAPI: routes /api/analyze, /scenario, /overview, /graph,
                         /functions, /ingest, /ask, /settings, /rule(+delete),
                         /project/(delete|refresh), /export/rules, /analyze_diff,
                         /analyze_file. Serves / (dashboard) and /manage.
- `app/falkor_client.py` All FalkorDB queries. Multi-project (one graph per repo +
                         `ca_meta` registry/config). Functions keyed by **fid =
                         file::name** (unique). Key methods: resolve(), func_info(),
                         blast_radius(fid), centrality(), rules_for(fid),
                         ownership(fid), impact_viz(fid), get_llm_config(),
                         get_github_token(), get/set_config, project CRUD.
- `app/agent.py`         analyze(client, fid) -> verdict+blast+rules+owner+highlights;
                         narrate(analysis, cfg); answer_question(cfg, q, context).
- `app/ingest.py`        Parse repos. Python=ast (precise). JS/TS/Go/Java=regex
                         (approximate). Extracts fid, CALLS, endpoints, docstrings
                         (`doc`). git_owners() from real git log. GitHub token ->
                         clones PRIVATE repos.
- `app/seed_data.py`     Curated sample microservices graph (auth/billing/orders/db)
                         with fids + docs + rules + ADRs.
- `app/mcp_server.py`    fastmcp SSE server. Tools: analyze_change, blast_radius,
                         team_rules, find_owner, chokepoints, list_functions,
                         list_projects. (Use OFFICIAL mcp SDK client to test, not
                         fastmcp Client  it has a pydantic incompat.)
- `app/diff_analyze.py`  Unified-diff -> changed functions -> PR-level impact + markdown.
- `app/pr_bot.py` + `.github/workflows/contextanchor.yml`  GitHub PR impact bot.
- `app/genrules.py`      Generate CLAUDE.md/.cursorrules from the graph.
- `app/check.py`         CLI gate (exit 1 on BLOCK) for pre-commit/CI.
- `integrations/`        Claude Code PreToolUse hook + git pre-commit hook.
- `app/static/`          index.html (dashboard), manage.html (repos+rules+settings),
                         app.js, manage.js, styles.css. Cytoscape + dagre layout.

## Data model
Nodes: File{path,module}, Function{fid,name,file,line_no,lang,doc,is_entrypoint},
Endpoint{route,method,service}, Developer{name,email,role}, TeamRule{id,rule_text,
severity,created_at}, ADR{id,title,decision,status}. Config/Project live in `ca_meta`.
Rels: CONTAINS, CALLS, EXECUTES, AUTHORED{commits,last_touched}, GOVERNS, APPLIES_TO.

## State (as of this handover)
WORKING (verified live): web dashboard, 3 sample scenarios, native algo.betweenness,
real repo ingest + git owners, multi-language ingest (JS/Go tested), fid name-collision
fix, MCP server (7 tools, official SDK client), diff analysis, CLAUDE.md export,
CLI gate, Manage page (project CRUD + rules CRUD), LLM+GitHub settings, Ask (grounded),
project-overview center with clickable chokepoint chips, function docstrings.
Just fixed: `_llm_narrate` signature bug that 500'd analyze/scenario (needs web rebuild).
BUILT but not CI-tested: PR bot workflow, pre-edit hooks.

## Gotchas / decisions (IMPORTANT)
- Functions are keyed by **fid (file::name)**, NOT name. User input (name) is resolved
  via client.resolve(); ambiguous names return candidates (409 / list).
- Startup AUTO-RESEEDS the sample if it lacks fid or doc (schema drift). Real repos
  (proj_*) do NOT auto-migrate  re-ingest them via Manage -> Refresh.
- Multi-language is regex-based for non-Python (approximate call attribution; some
  false edges). Python (ast) is precise. Full fix = tree-sitter (not done, time).
- LLM key + GitHub token stored plaintext in FalkorDB `ca_meta` Config (local app).
  Resolved as: config value OR env (NVIDIA_API_KEY / GITHUB_TOKEN). NVIDIA key is in
  `.env` (gitignored)  do NOT commit it.
- **Edit the files from ONE place.** A separate QA agent was editing check.py/mcp_server
  .py/diff_analyze.py concurrently and caused merge conflicts/bugs. Coordinate edits.
- Device/cloud: this was built via a bridge; the dev runs Docker via colima on macOS.
- To test changes: rebuild only what changed (`docker compose up -d --build web`).

## Submission still TODO
- Record silent demo video (2-3 min): scenarios 1/2/3, ingest a real repo, Ask,
  MCP from an agent. Outline in earlier chat.
- Final README polish (README.md is current). Push to a PUBLIC GitHub repo
  (user pushes; key is gitignored).

## Next ideas (if time)
tree-sitter multi-language; PR bot live CI run; richer Ask (more graph context);
vector/HNSW semantic search; bus-factor dashboard.
