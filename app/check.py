"""ContextAnchor pre-commit / CI gate.

Blocks a risky change from the terminal  real workflow integration, not a demo.
Exit code 1 on BLOCK so it fails a git pre-commit hook or CI step.

    python -m app.check calculate_discount
    python -m app.check issue_token --project proj_myrepo
"""
import argparse
import sys
from app.falkor_client import FalkorClient, DEFAULT_GRAPH, slug
from app import agent

RESET = "\033[0m"; RED = "\033[91m"; YLW = "\033[93m"; GRN = "\033[92m"; BOLD = "\033[1m"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("function")
    ap.add_argument("--project", default="")
    args = ap.parse_args()

    c = FalkorClient()
    projects = c.list_projects()
    all_graphs = [p["graph"] for p in projects]

    if args.project:
        if args.project in all_graphs:
            c.use(args.project)
        elif ("proj_" + slug(args.project)) in all_graphs:
            c.use("proj_" + slug(args.project))
        else:
            c.use(args.project if (args.project.startswith("proj_") or args.project == DEFAULT_GRAPH) else "proj_" + slug(args.project))
        exists = c.run("MATCH (f:Function {name:$n}) RETURN f LIMIT 1", {"n": args.function}).result_set
        if not exists:
            print(f"{YLW}? No function '{args.function}' in project '{c.active}'.{RESET}")
            return 0
    else:
        # Search candidate graphs: ingested repos first, then DEFAULT_GRAPH
        non_sample = [p["graph"] for p in reversed(projects) if p.get("kind") != "sample"]
        search_order = non_sample + [DEFAULT_GRAPH]
        seen = set()
        ordered = [g for g in search_order if not (g in seen or seen.add(g))]

        found = False
        for g in ordered:
            c.use(g)
            if c.run("MATCH (f:Function {name:$n}) RETURN f LIMIT 1", {"n": args.function}).result_set:
                found = True
                break
        if not found:
            # Fallback to any other remaining graphs
            for g in all_graphs:
                if g not in seen:
                    c.use(g)
                    if c.run("MATCH (f:Function {name:$n}) RETURN f LIMIT 1", {"n": args.function}).result_set:
                        found = True
                        break
        if not found:
            print(f"{YLW}? No function '{args.function}' found in any project ({', '.join(all_graphs)}).{RESET}")
            return 0

    rr = c.resolve(args.function)
    if rr["candidates"]:
        print(f"{YLW}? '{args.function}' is ambiguous in '{c.active}':{RESET}")
        for cand in rr["candidates"]:
            print(f"   - {cand['fid']}")
        print("Re-run with the full fid (file::name).")
        return 0
    if not rr["fid"]:
        print(f"{YLW}? No function '{args.function}' in '{c.active}'.{RESET}")
        return 0
    a = agent.analyze(c, rr["fid"])
    color = {"BLOCK": RED, "REVIEW": YLW, "SAFE": GRN}[a["verdict"]]
    print(f"\n{BOLD}{color}ContextAnchor: {a['verdict']}{RESET}  changing {BOLD}{args.function}(){RESET}  [{c.active}]")
    print(agent.narrate(a)["text"])
    print()
    return 1 if a["verdict"] == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
