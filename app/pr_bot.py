"""GitHub PR Impact Bot.

Runs inside a GitHub Action on every pull request:
  1. ingests the checked-out repo into FalkorDB (real call graph + git owners),
  2. diffs the PR against its base branch,
  3. maps changed lines to functions and computes the combined blast radius,
  4. posts a comment with impact, violated rules, and reviewers to tag.

Env: FALKORDB_HOST, GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_BASE_REF, PR_NUMBER.
Set CA_STRICT=1 to fail the check when the verdict is BLOCK.
"""
import os
import subprocess
import sys

import httpx

from app.falkor_client import FalkorClient
from app.ingest import ingest_repo
from app import diff_analyze


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True).stdout


def get_diff(base):
    subprocess.run(["git", "fetch", "--depth", "200", "origin", base],
                   capture_output=True, text=True)
    out = _run(["git", "diff", f"origin/{base}...HEAD"])
    return out or _run(["git", "diff", "HEAD~1...HEAD"])


def post_comment(repo, pr, token, body):
    r = httpx.post(
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json"},
        json={"body": body}, timeout=30)
    r.raise_for_status()
    return r.json().get("html_url")


def main():
    repo = os.getenv("GITHUB_REPOSITORY", "")
    pr = os.getenv("PR_NUMBER", "")
    token = os.getenv("GITHUB_TOKEN", "")
    base = os.getenv("GITHUB_BASE_REF", "main")

    client = FalkorClient()
    summary = ingest_repo(client, ".")  # current checkout (has .git for owners)
    print("[pr_bot] ingested:", summary)

    diff = get_diff(base)
    report = diff_analyze.analyze_diff(client, diff)
    md = diff_analyze.to_markdown(report, summary.get("project", ""))
    print(md)

    if repo and pr and token:
        try:
            url = post_comment(repo, pr, token, md)
            print("[pr_bot] comment posted:", url)
        except Exception as e:
            print("[pr_bot] could not post comment:", e)
    else:
        print("[pr_bot] no GitHub context  printed report only.")

    if os.getenv("CA_STRICT") == "1" and report["verdict"] == "BLOCK":
        sys.exit(1)


if __name__ == "__main__":
    main()
