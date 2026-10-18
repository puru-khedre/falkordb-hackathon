"""ContextAnchor reasoning agent.

For a given function it unifies all three hackathon tracks into ONE answer by
querying FalkorDB:
  Track 1  blast radius + betweenness centrality  (act on connected data)
  Track 2  team rules that govern it              (agent memory)
  Track 3  owner + ADR                            (company brain)

The natural-language narration is produced by an LLM (NVIDIA NIM) when a key is
present, and by a deterministic template otherwise so the product is fully
functional offline. The *decisions* always come from the graph, never the LLM.
"""
import os
import httpx


def analyze(client, fid):
    """Pure graph analysis for a function (by fid). No LLM. The real output."""
    info = client.func_info(fid)
    func_name = info["name"]
    func_doc = info.get("doc", "")
    blast = client.blast_radius(fid)
    rules = client.rules_for(fid)
    owner = client.ownership(fid)
    choke = client.top_chokepoint()

    affected = blast["affected_functions"]
    apis = blast["impacted_apis"]

    # Risk verdict derived from the graph.
    high_sev = [r for r in rules if r.get("severity") == "HIGH"]
    if high_sev:
        verdict, level = "BLOCK", "high"
    elif len(affected) >= 3 or apis:
        verdict, level = "REVIEW", "medium"
    else:
        verdict, level = "SAFE", "low"

    highlights = _highlights(fid, affected, apis, rules, owner)

    return {
        "function": func_name,
        "fid": fid,
        "doc": func_doc,
        "verdict": verdict,
        "risk_level": level,
        "blast_radius": blast,
        "team_rules": rules,
        "ownership": owner,
        "chokepoint": choke,
        "highlights": highlights,
    }


def _highlights(fid, affected, apis, rules, owner):
    red = [f"Function:{fid}"] + [f"Function:{a['fid']}" for a in affected]
    red += [f"Endpoint:{a['route']}" for a in apis]
    amber = [f"TeamRule:{r['id']}" for r in rules]
    green = []
    blue = []
    if owner.get("author"):
        green.append(f"Developer:{owner['author']['name']}")
    if owner.get("file"):
        green.append(f"File:{owner['file']}")
    if owner.get("adr"):
        blue.append(f"ADR:{owner['adr']['id']}")
    return {"red": red, "amber": amber, "green": green, "blue": blue}


def narrate(analysis, cfg=None):
    """Human-readable summary. Tries the LLM, falls back to a template."""
    llm = _llm_narrate(analysis, cfg)
    if llm:
        return {"text": llm, "source": "llm"}
    return {"text": _template_narrate(analysis), "source": "graph-template"}


def _template_narrate(a):
    fn = a["function"]
    affected = a["blast_radius"]["affected_functions"]
    apis = a["blast_radius"]["impacted_apis"]
    lines = []
    verdict_word = {"BLOCK": "⛔ BLOCK", "REVIEW": "⚠️ REVIEW", "SAFE": "✅ SAFE"}[a["verdict"]]
    lines.append(f"{verdict_word}  changing `{fn}()`")
    if affected:
        names = ", ".join(x["function"] + "()" for x in affected[:6])
        lines.append(f"Blast radius: {len(affected)} upstream function(s) depend on it  {names}.")
    else:
        lines.append("Blast radius: no upstream callers found  this is a leaf.")
    if apis:
        routes = ", ".join(f"{x['method']} {x['route']}" for x in apis)
        lines.append(f"Live APIs affected: {routes}.")
    for r in a["team_rules"]:
        lines.append(f"Team rule {r['id']} ({r['severity']}): {r['rule']}")
    own = a["ownership"]
    if own.get("author"):
        au = own["author"]
        lines.append(f"Owner: {au['name']} ({au['role']}), {au['commits']} commits, last touched {au['last_touched']}.")
    if own.get("adr"):
        adr = own["adr"]
        lines.append(f"Architecture decision {adr['id']}  {adr['title']}: {adr['decision']}")
    if a.get("chokepoint"):
        c = a["chokepoint"]
        lines.append(f"Global chokepoint right now: {c['function']}() (score {c['score']}, via {c['method']}).")
    return "\n".join(lines)


def _llm_narrate(a, cfg=None):
    cfg = cfg or {}
    key = (cfg.get("api_key") or os.getenv("NVIDIA_API_KEY", "")).strip()
    if not key:
        return None
    base = (cfg.get("base_url") or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")).rstrip("/")
    model = cfg.get("model") or os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")
    facts = _template_narrate(a)
    prompt = (
        "You are ContextAnchor, a senior staff engineer reviewing a proposed code change. "
        "Using ONLY the graph-derived facts below, write a tight 3-4 sentence impact review "
        "for the developer. Do not invent anything not in the facts.\n\n"
        f"FACTS:\n{facts}\n"
    )
    try:
        r = httpx.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.2, "max_tokens": 300},
            timeout=20.0,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def _llm_call(cfg, prompt, max_tokens=400):
    key = (cfg.get("api_key") or "").strip()
    if not key:
        return None
    base = (cfg.get("base_url") or "https://integrate.api.nvidia.com/v1").rstrip("/")
    model = cfg.get("model") or "meta/llama-3.2-11b-vision-instruct"
    try:
        r = httpx.post(f"{base}/chat/completions",
                       headers={"Authorization": f"Bearer {key}"},
                       json={"model": model, "messages": [{"role": "user", "content": prompt}],
                             "temperature": 0.2, "max_tokens": max_tokens},
                       timeout=25.0)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def answer_question(cfg, question, context):
    """Grounded Q&A: answer ONLY from the graph context (GraphRAG-lite)."""
    if not context.strip():
        return {"answer": "I couldn't find anything related in this project's graph.",
                "source": "graph"}
    prompt = ("You are ContextAnchor, answering a developer's question about a codebase. "
              "Use ONLY the graph facts below. If they don't cover it, say so. Be concise.\n\n"
              f"GRAPH FACTS:\n{context}\n\nQUESTION: {question}\n")
    out = _llm_call(cfg, prompt, max_tokens=450)
    if out:
        return {"answer": out, "source": "llm"}
    return {"answer": "LLM is off. Here are the related graph facts:\n\n" + context,
            "source": "graph"}
