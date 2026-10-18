"""ContextAnchor MCP server  the real product surface.

Any AI coding agent (Cursor, Claude Code, Claude Desktop) connects to this and
calls `analyze_change` BEFORE it edits a function. The agent gets the blast
radius, the team rules it would violate, and the owner  straight from the
FalkorDB graph  so it stops drifting and breaking conventions.

This is exactly the hackathon theme: real, queryable context for AI agents.

Run (SSE, for remote/containerised agents):
    python -m app.mcp_server
Run (stdio, for a local agent config):
    python -m app.mcp_server --stdio
"""
import os
import sys
try:
    from fastmcp import FastMCP            # standalone fastmcp 2.x (preferred)
except Exception:                          # pragma: no cover
    from mcp.server.fastmcp import FastMCP  # official mcp 1.x fallback

from app.falkor_client import FalkorClient, DEFAULT_GRAPH, slug
from app import agent
from app import diff_analyze

mcp = FastMCP("ContextAnchor")
_client = None


def client():
    global _client
    if _client is None:
        _client = FalkorClient()
    return _client


def _resolve(project="", function=""):
    """Pick the graph to query: explicit project, else project containing function, else newest repo, else sample."""
    c = client()
    projects = c.list_projects()
    all_graphs = [p["graph"] for p in projects]
    if project:
        if project in all_graphs:
            c.use(project)
        elif ("proj_" + slug(project)) in all_graphs:
            c.use("proj_" + slug(project))
        else:
            c.use(project if (project.startswith("proj_") or project == DEFAULT_GRAPH) else "proj_" + slug(project))
        return c
    non_sample = [p["graph"] for p in reversed(projects) if p.get("kind") != "sample"]
    search_order = non_sample + [DEFAULT_GRAPH]
    if function:
        for g in search_order:
            c.use(g)
            if c.run("MATCH (f:Function {name:$n}) RETURN f LIMIT 1", {"n": function}).result_set:
                return c
    c.use(non_sample[0] if non_sample else DEFAULT_GRAPH)
    return c


@mcp.tool()
def list_projects() -> list:
    """List ingested codebases (projects) available to query."""
    return client().list_projects()


@mcp.tool()
def list_functions(project: str = "") -> list:
    """List functions in a project's code graph."""
    return _resolve(project).functions_list()


@mcp.tool()
def analyze_change(function: str, project: str = "") -> dict:
    """Assess the impact of changing `function` BEFORE editing it.
    Returns a verdict (BLOCK/REVIEW/SAFE), the blast radius (upstream callers and
    impacted APIs), any team rules it violates, the code owner, and the global
    chokepoint  all derived from the FalkorDB graph."""
    c = _resolve(project, function)
    r = c.resolve(function)
    if r["candidates"]:
        return {"error": "ambiguous function name; pass a full fid (file::name)",
                "candidates": r["candidates"]}
    if not r["fid"]:
        return {"error": f"No function '{function}' in project '{c.active}'."}
    res = agent.analyze(c, r["fid"])
    res["project"] = c.active
    res["recommendation"] = agent.narrate(res)["text"]
    res.pop("highlights", None)
    res.pop("viz", None)
    return res


@mcp.tool()
def blast_radius(function: str, project: str = "") -> dict:
    """Upstream callers (1-4 hops) and live API endpoints affected by `function`."""
    c = _resolve(project, function); r = c.resolve(function)
    return c.blast_radius(r["fid"]) if r["fid"] else {"error": "unknown/ambiguous function", "candidates": r.get("candidates", [])}


@mcp.tool()
def team_rules(function: str, project: str = "") -> list:
    """Team/architecture rules that govern `function` (persistent graph memory)."""
    c = _resolve(project, function); r = c.resolve(function)
    return c.rules_for(r["fid"]) if r["fid"] else []


@mcp.tool()
def find_owner(function: str, project: str = "") -> dict:
    """Code owner (from real git history) and any ADR applying to `function`."""
    c = _resolve(project, function); r = c.resolve(function)
    return c.ownership(r["fid"]) if r["fid"] else {}


@mcp.tool()
def chokepoints(project: str = "") -> list:
    """Top betweenness-centrality chokepoints (single points of failure)."""
    return _resolve(project).centrality(limit=5)



# ======================================================================
#  v2 upgrade — write-back, diff analysis, discovery, refactor guidance,
#  plus native MCP resources and prompts. The original 7 tools are intact.
# ======================================================================
def _next_rule_id(c):
    import re as _re
    ids = [r["id"] for r in c.all_rules()]
    nums = [int(m.group(1)) for i in ids for m in [_re.match(r"RULE-(\d+)$", str(i))] if m]
    n = (max(nums) + 1) if nums else 1
    rid = f"RULE-{n}"
    while rid in ids:
        n += 1
        rid = f"RULE-{n}"
    return rid


@mcp.tool()
def record_rule(rule_text: str, severity: str = "MEDIUM", function: str = "",
                file: str = "", project: str = "", rule_id: str = "") -> dict:
    """Write a NEW team rule / architecture decision into the FalkorDB graph
    memory, so every future analysis enforces it. This is two-way memory
    write-back: the agent doesn't only read context, it grows it.

    rule_text: the rule, e.g. "No raw SQL in the service layer".
    severity : HIGH | MEDIUM | LOW (HIGH makes governed functions BLOCK).
    function : optional function the rule governs (name or file::name).
    file     : optional file path the rule governs.
    rule_id  : optional explicit id; auto-generated (RULE-N) if omitted."""
    if not (rule_text or "").strip():
        return {"error": "rule_text is required"}
    sev = (severity or "MEDIUM").upper()
    if sev not in ("HIGH", "MEDIUM", "LOW"):
        sev = "MEDIUM"
    c = _resolve(project)
    rid = (rule_id or "").strip() or _next_rule_id(c)
    target_file = (file or "").strip() or None
    tfid = None
    if (function or "").strip():
        r = c.resolve(function.strip())
        if r["candidates"]:
            return {"error": "ambiguous function; pass file::name",
                    "candidates": r["candidates"]}
        if not r["fid"]:
            return {"error": f"no function '{function}' in project '{c.active}'"}
        tfid = r["fid"]
    c.add_rule(rid, rule_text.strip(), sev, target_file=target_file)
    governs = {}
    if tfid:
        c.run("""MATCH (r:TeamRule {id:$id}),(f:Function {fid:$fid})
                 MERGE (r)-[:GOVERNS]->(f)""", {"id": rid, "fid": tfid})
        governs["function"] = tfid
    if target_file:
        governs["file"] = target_file
    return {"recorded": True, "id": rid, "rule_text": rule_text.strip(),
            "severity": sev, "project": c.active, "governs": governs}


@mcp.tool()
def analyze_diff(diff: str, project: str = "") -> dict:
    """Analyze a full unified git diff at once (many files/functions). Maps every
    changed hunk to its function and returns the PR-level verdict, combined blast
    radius, impacted APIs, violated team rules, suggested reviewers (code owners),
    and a ready-to-post markdown review."""
    if not (diff or "").strip():
        return {"error": "diff is required (unified git diff text)"}
    c = _resolve(project)
    report = diff_analyze.analyze_diff(c, diff)
    report["project"] = c.active
    report["markdown"] = diff_analyze.to_markdown(report, c.active)
    return report


@mcp.tool()
def search_codebase(query: str, project: str = "", limit: int = 10) -> dict:
    """Discovery tool: find matching functions, files, endpoints, team rules and
    ADRs from a keyword or natural-language query. Use this first when you don't
    know the exact function name to pass to analyze_change."""
    if not (query or "").strip():
        return {"error": "query is required"}
    c = _resolve(project)
    res = c.search(query, limit=limit)
    res["project"] = c.active
    res["query"] = query
    return res


@mcp.tool()
def get_refactor_guide(function: str, project: str = "") -> dict:
    """Actionable safe-refactoring checklist for a function: which callers to
    update, which live APIs to re-test, which team rules and ADRs to respect, and
    which code owner to consult. Turns a BLOCK verdict into concrete steps."""
    c = _resolve(project, function)
    r = c.resolve(function)
    if r["candidates"]:
        return {"error": "ambiguous function; pass file::name",
                "candidates": r["candidates"]}
    if not r["fid"]:
        return {"error": f"no function '{function}' in project '{c.active}'"}
    a = agent.analyze(c, r["fid"])
    callers = a["blast_radius"]["affected_functions"]
    apis = a["blast_radius"]["impacted_apis"]
    rules = a["team_rules"]
    own = a.get("ownership", {}) or {}
    author = own.get("author")
    adr = own.get("adr")

    steps = []
    for rule in rules:
        steps.append(f"Comply with {rule['id']} ({rule['severity']}): {rule['rule']}")
    if adr:
        steps.append(f"Follow architecture decision {adr['id']} — {adr['title']}: {adr['decision']}")
    if callers:
        nm = ", ".join(f"{x['function']}()" for x in callers[:8])
        steps.append(f"Update/verify {len(callers)} upstream caller(s): {nm}")
    if apis:
        rt = ", ".join(f"{x['method']} {x['route']}" for x in apis)
        steps.append(f"Re-test the live endpoint(s): {rt}")
    if author:
        steps.append(f"Get sign-off from the code owner: {author['name']} ({author.get('role', 'owner')}).")
    steps.append("Add/keep tests covering each caller path above before merging.")
    if not (rules or callers or apis):
        steps = ["Low-risk leaf function (SAFE): no upstream callers, APIs or rules. "
                 "Still add a unit test for the new behaviour."]

    return {
        "function": a["function"],
        "fid": a["fid"],
        "project": c.active,
        "verdict": a["verdict"],
        "risk_level": a["risk_level"],
        "callers_to_update": callers,
        "apis_to_retest": apis,
        "rules_to_follow": rules,
        "adr_to_respect": adr,
        "owner_to_consult": author,
        "checklist": steps,
        "recommendation": agent.narrate(a, c.get_llm_config())["text"],
    }


# ---- Native MCP resources (IDEs read these without a tool call) --------
@mcp.resource("contextanchor://projects")
def projects_resource() -> str:
    """All ingested codebases (projects) available to query."""
    import json
    return json.dumps(client().list_projects(), indent=2)


@mcp.resource("contextanchor://rules/{project}")
def rules_resource(project: str) -> str:
    """Live team rules for a project — persistent architecture memory."""
    import json
    c = _resolve(project)
    return json.dumps({"project": c.active, "rules": c.all_rules()}, indent=2)


# ---- Native MCP prompts (ready-made agent workflows) -------------------
@mcp.prompt()
def safe_refactor(function: str, project: str = "") -> str:
    """Guidelines for safely changing a function using ContextAnchor."""
    scope = f" in project '{project}'" if project else ""
    return (
        f"You are about to change `{function}()`{scope}. Before editing, use the "
        f"ContextAnchor MCP tools to stay safe:\n"
        f"1. Call analyze_change(\"{function}\") for the verdict, blast radius, "
        f"governing team rules and the code owner.\n"
        f"2. Call get_refactor_guide(\"{function}\") and follow its checklist step by step.\n"
        f"3. If the verdict is BLOCK, do NOT bypass the rule — rework the change to comply, "
        f"or escalate to the listed owner.\n"
        f"4. Update every upstream caller it lists and re-test the impacted endpoints.\n"
        f"Only then write the change."
    )


@mcp.prompt()
def review_patch(diff: str) -> str:
    """Guidelines for reviewing a unified git diff with ContextAnchor."""
    return (
        "Review this patch with ContextAnchor before approving.\n"
        "1. Call analyze_diff with the full unified diff below.\n"
        "2. Report the PR-level verdict, combined blast radius, any violated team "
        "rules, and the suggested reviewers (code owners).\n"
        "3. Block the merge if the verdict is BLOCK; request the owner's review if REVIEW.\n\n"
        f"```diff\n{diff}\n```"
    )


def _main():
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "9000"))
    if "--stdio" in sys.argv:
        mcp.run(transport="stdio")
        return
    try:
        mcp.run(transport="sse", host=host, port=port)
    except TypeError:
        try:
            mcp.settings.host = host
            mcp.settings.port = port
        except Exception:
            pass
        mcp.run(transport="sse")


if __name__ == "__main__":
    _main()
