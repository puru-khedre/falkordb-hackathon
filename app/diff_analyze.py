"""Diff-aware impact analysis.

Takes a unified diff, maps each changed hunk to the function that contains it
(using line numbers already in the graph), then aggregates a PR-level impact:
worst verdict, combined blast radius, all violated rules, and the owners to tag
as reviewers. Powers both the GitHub PR bot and the git pre-commit hook.
"""
import re
from app import agent

_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE = re.compile(r"^\+\+\+ b/(.+)$")
_RANK = {"SAFE": 0, "REVIEW": 1, "BLOCK": 2}
_RANK_INV = {v: k for k, v in _RANK.items()}


def changed_hunks(diff_text):
    """Yield (file_path, new_line_start) for every hunk in the diff."""
    cur = None
    for line in diff_text.splitlines():
        m = _FILE.match(line)
        if m:
            cur = m.group(1)
            continue
        h = _HUNK.match(line)
        if h and cur and cur != "/dev/null":
            yield cur, int(h.group(1))


def _func_at(client, path, line):
    import os
    base = os.path.basename(path)
    res = client.run("""MATCH (f:Function)
                        WHERE (f.file = $p OR f.file = $base OR $p ENDS WITH ('/' + f.file) OR f.file ENDS WITH ('/' + $p)) AND f.line_no <= $l
                        RETURN f.fid ORDER BY f.line_no DESC LIMIT 1""",
                     {"p": path, "base": base, "l": line})
    return res.result_set[0][0] if res.result_set else None


def changed_functions(client, diff_text):
    names = []
    for path, line in changed_hunks(diff_text):
        fn = _func_at(client, path, line)
        if fn and fn not in names:
            names.append(fn)
    return names


def analyze_diff(client, diff_text):
    fids = changed_functions(client, diff_text)
    fidset = set(fids)
    per_fn, affected, apis, rules, reviewers = [], {}, {}, {}, {}
    worst = 0
    for fid in fids:
        a = agent.analyze(client, fid)
        worst = max(worst, _RANK[a["verdict"]])
        per_fn.append({"function": a["function"], "verdict": a["verdict"]})
        for x in a["blast_radius"]["affected_functions"]:
            if x.get("fid") not in fidset:
                affected[x.get("fid", x["function"])] = x
        for x in a["blast_radius"]["impacted_apis"]:
            apis[(x["method"], x["route"])] = x
        for r in a["team_rules"]:
            rules[r["id"]] = r
        own = a.get("ownership", {})
        if own.get("author"):
            au = own["author"]
            reviewers[au["name"]] = au
    return {
        "changed_functions": per_fn,
        "verdict": _RANK_INV[worst] if fids else "SAFE",
        "affected_functions": list(affected.values()),
        "impacted_apis": list(apis.values()),
        "team_rules": list(rules.values()),
        "reviewers": list(reviewers.values()),
        "count": len(fids),
    }


def analyze_file(client, path):
    import os
    base = os.path.basename(path)
    # Check file-level rules
    file_rules = client.run("""MATCH (r:TeamRule)-[:GOVERNS]->(fl:File)
                               WHERE fl.path = $p OR fl.path = $base OR $p ENDS WITH ('/' + fl.path) OR fl.path ENDS WITH ('/' + $p)
                               RETURN r.id, r.severity""",
                            {"p": path, "base": base}).result_set
    worst = 0
    file_rule_ids = []
    for r in file_rules:
        file_rule_ids.append(r[0])
        sev = r[1]
        worst = max(worst, 2 if sev == "HIGH" else 1)

    res = client.run("""MATCH (f:Function)
                        WHERE f.file = $p OR f.file = $base OR $p ENDS WITH ('/' + f.file) OR f.file ENDS WITH ('/' + $p)
                        RETURN f.fid ORDER BY f.line_no""",
                     {"p": path, "base": base})
    fids = [r[0] for r in res.result_set]
    per_fn = []
    # Cap batch analysis to avoid timeouts on massive files
    for fid in fids[:40]:
        a = agent.analyze(client, fid)
        worst = max(worst, _RANK[a["verdict"]])
        rules_list = [r["id"] for r in a["team_rules"]] + file_rule_ids
        per_fn.append({"function": a["function"], "verdict": a["verdict"],
                       "rules": list(dict.fromkeys(rules_list)),
                       "affected": len(a["blast_radius"]["affected_functions"])})
    return {"file": path, "verdict": _RANK_INV[worst] if (fids or file_rules) else "SAFE",
            "functions": per_fn}


def to_markdown(report, project=""):
    v = report["verdict"]
    icon = {"BLOCK": "", "REVIEW": "", "SAFE": ""}[v]
    lines = [f"## {icon} ContextAnchor impact review  **{v}**"]
    if project:
        lines.append(f"_project: `{project}`_")
    if not report["changed_functions"]:
        lines.append("\nNo tracked functions changed.")
        return "\n".join(lines)
    chg = ", ".join(f"`{c['function']}()` ({c['verdict']})" for c in report["changed_functions"])
    lines.append(f"\n**Changed functions:** {chg}")
    aff = report["affected_functions"]
    if aff:
        names = ", ".join(f"`{a['function']}()`" for a in aff[:12])
        lines.append(f"\n**Blast radius  {len(aff)} upstream function(s) may break:** {names}")
    if report["impacted_apis"]:
        routes = ", ".join(f"`{a['method']} {a['route']}`" for a in report["impacted_apis"])
        lines.append(f"\n**Live APIs affected:** {routes}")
    if report["team_rules"]:
        lines.append("\n**Team rules at risk:**")
        for r in report["team_rules"]:
            lines.append(f"- **{r['id']}** ({r['severity']}): {r['rule']}")
    if report["reviewers"]:
        who = ", ".join(f"{r['name']}" for r in report["reviewers"])
        lines.append(f"\n**Suggested reviewers (code owners):** {who}")
    lines.append("\n<sub>Derived from the FalkorDB code graph  ContextAnchor.</sub>")
    return "\n".join(lines)
