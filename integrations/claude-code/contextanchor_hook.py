#!/usr/bin/env python3
"""Claude Code PreToolUse hook: warn/block before the agent edits risky code.

Install: copy integrations/claude-code/settings.json into your repo's
.claude/settings.json (merge if it exists), with ContextAnchor running on :8000.

On an Edit/Write, it asks ContextAnchor for the file's impact. If any function in
that file is a BLOCK, it exits 2 so Claude Code blocks the edit and feeds the
reason back to the model. Otherwise it prints an advisory and allows the edit.
Fails open (exit 0) if ContextAnchor is unreachable  never breaks your workflow.
"""
import json
import os
import sys
import urllib.request

CA_URL = os.getenv("CA_URL", "http://localhost:8000")
PROJECT = os.getenv("CA_PROJECT", "")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0
    ti = data.get("tool_input", {}) or {}
    path = ti.get("file_path") or ti.get("path")
    if not path or not path.endswith(".py"):
        return 0
    rel = os.path.relpath(path, os.getcwd())
    try:
        req = urllib.request.Request(
            f"{CA_URL}/api/analyze_file",
            data=json.dumps({"file": rel, "project": PROJECT}).encode(),
            headers={"Content-Type": "application/json"})
        res = json.load(urllib.request.urlopen(req, timeout=5))
    except Exception:
        return 0  # fail open

    verdict = res.get("verdict", "SAFE")
    hot = [f for f in res.get("functions", []) if f["verdict"] in ("BLOCK", "REVIEW")]
    if not hot:
        return 0
    msg = [f"ContextAnchor: editing {rel} ({verdict})."]
    for f in hot[:6]:
        rules = (" rules " + ",".join(f["rules"])) if f["rules"] else ""
        msg.append(f"  - {f['function']}(): {f['verdict']}, {f['affected']} upstream callers{rules}")
    msg.append("Check `analyze_change` before refactoring these.")
    sys.stderr.write("\n".join(msg) + "\n")
    return 2 if verdict == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
