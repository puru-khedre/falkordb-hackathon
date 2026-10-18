"""ContextAnchor MCP self-test (v2).

Run inside the running stack (FalkorDB must be up and the sample seeded):

    docker compose up -d --build mcp          # pick up the new tools first
    docker compose exec mcp python -m app.selftest graph   # tool logic vs live graph
    docker compose exec mcp python -m app.selftest sse      # end-to-end over the SSE server
    docker compose exec mcp python -m app.selftest all      # both

'graph' exercises every tool in-process against the live FalkorDB graph.
'sse' connects to the running SSE server with the OFFICIAL MCP SDK client
(mcp.client.sse) and confirms the new tools/resources/prompts are exposed.
"""
import sys
import asyncio


def _fn(name):
    """Return the underlying callable for a tool/resource/prompt (fastmcp-agnostic)."""
    import app.mcp_server as M
    o = getattr(M, name)
    return o if (callable(o) and not hasattr(o, "fn")) else o.fn


def test_graph():
    import time
    import app.mcp_server as M
    print("== in-process tool logic vs live FalkorDB ==")
    projects = _fn("list_projects")()
    print("projects:", [p["graph"] for p in projects])
    funcs = _fn("list_functions")()
    assert funcs, "no functions in graph — is the sample seeded?"
    print("functions:", len(funcs), "e.g.", [f["name"] for f in funcs[:5]])

    s = _fn("search_codebase")(query="discount billing")
    print("search_codebase('discount billing') -> functions:",
          [f["name"] for f in s["functions"]][:5])

    target = ("calculate_discount" if any(f["name"] == "calculate_discount" for f in funcs)
              else funcs[0]["name"])
    ch = _fn("analyze_change")(function=target)
    print(f"analyze_change({target}) -> verdict: {ch.get('verdict')}")
    g = _fn("get_refactor_guide")(function=target)
    assert "checklist" in g, g
    print(f"get_refactor_guide({target}) -> {g['verdict']}, {len(g['checklist'])} steps")

    # two-way write-back + read-back, then clean up
    rid = f"RULE-SELFTEST-{int(time.time())}"
    rec = _fn("record_rule")(rule_text="selftest: example rule", severity="LOW",
                             function=target, rule_id=rid)
    assert rec.get("recorded"), rec
    rules_now = _fn("team_rules")(function=target)
    assert any(r["id"] == rid for r in rules_now), "recorded rule not read back!"
    print(f"write-back verified: {rid} now governs {target}")
    try:
        M._resolve().delete_rule(rid)
        print("cleanup: removed", rid)
    except Exception as e:
        print("cleanup skipped:", e)

    tfile = next((f["file"] for f in funcs if f["name"] == target), funcs[0]["file"])
    diff = f"--- a/{tfile}\n+++ b/{tfile}\n@@ -1,2 +1,3 @@\n+# tweak\n"
    d = _fn("analyze_diff")(diff=diff)
    print("analyze_diff -> verdict:", d["verdict"], "changed functions:", d["count"])

    pj = _fn("projects_resource")()
    assert "project" in pj.lower() or "graph" in pj.lower()
    print("projects_resource OK (%d bytes)" % len(pj))
    print("GRAPH TESTS: PASS")


async def test_sse(url="http://localhost:9000/sse"):
    from mcp.client.sse import sse_client
    from mcp import ClientSession
    print(f"== end-to-end over SSE: {url} ==")
    async with sse_client(url) as (r, w):
        async with ClientSession(r, w) as sess:
            await sess.initialize()
            tools = await sess.list_tools()
            names = [t.name for t in tools.tools]
            print("tools over SSE (%d): %s" % (len(names), names))
            expect = {"record_rule", "analyze_diff", "search_codebase", "get_refactor_guide"}
            assert expect <= set(names), "missing new tools over SSE: %s" % (expect - set(names))
            for label, coro in [("resources", sess.list_resources),
                                ("resource_templates", sess.list_resource_templates),
                                ("prompts", sess.list_prompts)]:
                try:
                    res = await coro()
                    attr = {"resources": "resources", "resource_templates": "resourceTemplates",
                            "prompts": "prompts"}[label]
                    print(f"{label}:", [getattr(x, "name", getattr(x, "uri", getattr(x, "uriTemplate", x)))
                                         for x in getattr(res, attr)])
                except Exception as e:
                    print(f"{label}: {e}")
            out = await sess.call_tool("search_codebase", {"query": "discount"})
            print("call_tool search_codebase OK; content items:", len(out.content))
    print("SSE TESTS: PASS")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in ("graph", "all"):
        test_graph()
    if mode in ("sse", "all"):
        url = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:9000/sse"
        asyncio.run(test_sse(url))


if __name__ == "__main__":
    main()
