# ContextAnchor — The Complete MCP Master Guide

> **Focus:** 100% MCP (Model Context Protocol) Server for AI Coding Agents  
> **Server Port:** `http://localhost:9000/sse` (or stdio mode)  
> **Supported IDEs:** Cursor, Claude Desktop, Claude Code, Antigravity, Windsurf  

---

## 1. How to Run ContextAnchor Fully Locally

### Prerequisites
- Docker & Docker Compose (or Colima on macOS)

### Start the Server (1-Command Boot)
```bash
cd ~/falkordb-hackathon
docker compose up -d
```

### Verify Local Health
```bash
# 1. Check containers (falkordb, web, mcp must be Up)
docker compose ps

# 2. Check MCP SSE endpoint (should return event: endpoint)
curl -s -N --max-time 3 http://localhost:9000/sse | head -c 120
```

---

## 2. How to Configure ContextAnchor in Your AI Tools

### A. Cursor IDE
1. Open **Cursor Settings** (`Cmd + ,` or Click the gear icon).
2. Go to **Features** $\rightarrow$ **MCP**.
3. Click **Add New MCP Server**.
4. Fill in:
   - **Name:** `contextanchor`
   - **Type:** `sse`
   - **URL:** `http://localhost:9000/sse`
5. Click **Save**. You will see a green dot with 11 tools available.

### B. Claude Desktop
Add ContextAnchor to your Claude Desktop config file:
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "contextanchor": {
      "url": "http://localhost:9000/sse"
    }
  }
}
```
*(If running in local stdio mode without docker, use:*
```json
{
  "mcpServers": {
    "contextanchor": {
      "command": "python",
      "args": ["-m", "app.mcp_server", "--stdio"],
      "cwd": "/Users/purusottamkhedre/falkordb-hackathon"
    }
  }
}
```
*)*

### C. Claude Code (CLI)
In your terminal, run:
```bash
claude mcp add contextanchor -- http://localhost:9000/sse
```
Or add to your project's `.claude/settings.json`:
```json
{
  "mcpServers": {
    "contextanchor": {
      "url": "http://localhost:9000/sse"
    }
  }
}
```

### D. Google Antigravity / Gemini CLI
Add to `~/.gemini/antigravity/mcp.json`:
```json
{
  "mcpServers": {
    "contextanchor": {
      "url": "http://localhost:9000/sse"
    }
  }
}
```

---

## 3. Complete Tools Reference (All 11 Tools)

ContextAnchor provides 11 tools across 4 categories:

### Category 1: Impact & Risk Analysis (Core Guards)

#### 1. `analyze_change`
- **What it does:** Primary pre-edit guard. Derives a risk verdict (`BLOCK`, `REVIEW`, `SAFE`), upstream blast radius, violated rules, code owner, and chokepoint before an agent modifies code.
- **Parameters:**
  - `function` *(string, required)*: Function name (e.g. `calculate_discount`) or unique FID (`billing_service.py::calculate_discount`).
  - `project` *(string, optional)*: Target project name (auto-detected if omitted).
- **Example Output:**
  ```json
  {
    "verdict": "BLOCK",
    "risk_level": "high",
    "blast_radius": {
      "affected_functions": [{"function": "checkout", "hops": 1}, {"function": "create_invoice", "hops": 1}],
      "impacted_apis": [{"route": "/invoices", "method": "GET"}]
    },
    "team_rules": [{"id": "RULE-4", "rule": "Discounts can never exceed 50%", "severity": "HIGH"}],
    "ownership": {"author": {"name": "Arjun Rao", "email": "arjun@acme.dev"}}
  }
  ```

#### 2. `blast_radius`
- **What it does:** Returns purely the connected call-graph tree (1–3 hops upstream callers) and live API endpoints exposed by the function.
- **Parameters:** `function`, `project` (optional).

#### 3. `analyze_diff` (NEW v2)
- **What it does:** Multi-file patch checker. Takes a full unified `git diff` and maps every hunk to functions, aggregating PR-level risk and reviewers in one call.
- **Parameters:**
  - `diff` *(string, required)*: The unified diff text (`--- a/file ... +++ b/file ...`).
  - `project` *(string, optional)*.
- **Example Output:**
  ```json
  {
    "verdict": "BLOCK",
    "changed_functions": [{"function": "calculate_discount", "verdict": "BLOCK"}],
    "reviewers": [{"name": "Arjun Rao", "commits": 9}],
    "markdown": "## ContextAnchor impact review — BLOCK\n..."
  }
  ```

---

### Category 2: Agent Memory & Two-Way Write-Back (Track 2)

#### 4. `team_rules`
- **What it does:** Returns all persistent team rules governing a function or its parent file.
- **Parameters:** `function`, `project` (optional).

#### 5. `record_rule` (NEW v2)
- **What it does:** Two-way memory write-back. Allows the AI agent to write a NEW team rule or architecture decision into FalkorDB graph memory so it is enforced in all future sessions.
- **Parameters:**
  - `rule_text` *(string, required)*: The rule, e.g. *"Never log sensitive credentials in plaintext"*.
  - `severity` *(string, optional)*: `HIGH` (causes BLOCK), `MEDIUM`, or `LOW`. Default is `MEDIUM`.
  - `function` *(string, optional)*: Specific function name or FID to govern.
  - `file` *(string, optional)*: Specific file path to govern.
  - `rule_id` *(string, optional)*: Custom ID (auto-generated as `RULE-N` if omitted).
  - `project` *(string, optional)*.
- **Example Output:**
  ```json
  {
    "recorded": true,
    "id": "RULE-10",
    "rule_text": "Never log sensitive credentials in plaintext",
    "severity": "HIGH",
    "governs": {"file": "auth_service.py"}
  }
  ```

---

### Category 3: Codebase Discovery & Navigation

#### 6. `search_codebase` (NEW v2)
- **What it does:** Discovery engine. Searches functions, files, endpoints, rules, and ADRs via keywords or natural language.
- **Parameters:**
  - `query` *(string, required)*: Keyword or phrase (e.g. *"discount"*, *"token"*, *"auth"*).
  - `project` *(string, optional)*.
  - `limit` *(int, default=10)*.
- **Example Output:**
  ```json
  {
    "functions": [{"name": "calculate_discount", "file": "billing_service.py"}],
    "rules": [{"id": "RULE-4", "rule": "Discounts can never exceed 50%"}],
    "adrs": [{"id": "ADR-07", "title": "Expand-contract for billing changes"}]
  }
  ```

#### 7. `list_functions`
- **What it does:** Lists all tracked functions in a project's code graph.
- **Parameters:** `project` (optional).

#### 8. `list_projects`
- **What it does:** Lists all ingested codebases available to query.
- **Parameters:** None.

---

### Category 4: Ownership & Guided Refactoring (Track 3)

#### 9. `get_refactor_guide` (NEW v2)
- **What it does:** Turns a `BLOCK` verdict into an actionable step-by-step checklist. Tells the agent who to consult, which upstream callers need updates, and which ADR to follow.
- **Parameters:** `function`, `project` (optional).
- **Example Output:**
  ```json
  {
    "verdict": "BLOCK",
    "checklist": [
      "Comply with RULE-4 (HIGH): Discounts can never exceed 50%",
      "Follow architecture decision ADR-07 — Expand-contract for billing changes",
      "Update/verify 3 upstream caller(s): checkout(), create_invoice(), place_order()",
      "Re-test the live endpoint(s): GET /invoices, POST /checkout",
      "Get sign-off from the code owner: Arjun Rao (Billing Engineer)"
    ]
  }
  ```

#### 10. `find_owner`
- **What it does:** Returns the primary git author (commits, last-touched) and linked ADR from git history.
- **Parameters:** `function`, `project` (optional).

#### 11. `chokepoints`
- **What it does:** Identifies top single-points-of-failure using GraphBLAS betweenness centrality.
- **Parameters:** `project` (optional).

---

## 4. Native FastMCP Resources & Prompts

### Resources
IDEs auto-inject these into context without making a manual tool call:
1. `contextanchor://projects`: Real-time JSON list of all ingested codebases.
2. `contextanchor://rules/{project}`: Live dynamic rules markdown (`CLAUDE.md` equivalent) generated straight from FalkorDB.

### Prompts
1. `safe_refactor(function, project)`: Ready-made agent workflow instructing the model to check blast radius, rules, and owner before editing.
2. `review_patch(diff)`: Ready-made PR review workflow evaluating a unified diff against ContextAnchor.

---

## 5. Live Demo Script: Presenting Every MCP Tool (Step-by-Step)

In a live demo, show an AI agent (Cursor or Terminal Client) solving a real development problem in 5 steps:

### Step 1: Discovery (`search_codebase`)
- **Agent action:** *"I need to change discount calculation, but I don't know the exact function name."*
- **Call:** `search_codebase(query="discount")`
- **Shows:** Finds `calculate_discount` in `billing_service.py`, plus `RULE-4` and `ADR-07`.

### Step 2: Impact Check (`analyze_change`)
- **Agent action:** *"Let me check if it's safe to edit `calculate_discount`."*
- **Call:** `analyze_change(function="calculate_discount")`
- **Shows:** `BLOCK` verdict! Warns about 3 upstream callers, 2 live APIs, and `RULE-4`.

### Step 3: Unblocking with Actionable Guide (`get_refactor_guide`)
- **Agent action:** *"I was blocked. How do I safely refactor this?"*
- **Call:** `get_refactor_guide(function="calculate_discount")`
- **Shows:** Concrete checklist: follow `ADR-07` expand-contract, update `checkout()`, tag owner `Arjun Rao`.

### Step 4: Patch Validation (`analyze_diff`)
- **Agent action:** *"I drafted my multi-file patch. Let me validate the whole diff."*
- **Call:** `analyze_diff(diff="--- a/billing_service.py ...")`
- **Shows:** Consolidated PR-level impact report and reviewer suggestions.

### Step 5: Memory Write-Back (`record_rule`)
- **Agent action:** *"We decided never to log customer tax IDs during checkout. Let me store this rule for the team."*
- **Call:** `record_rule(rule_text="Never log customer tax ID", severity="HIGH", file="billing_service.py")`
- **Shows:** Saved as `RULE-11` in FalkorDB. Now any future agent editing this file is instantly protected!
