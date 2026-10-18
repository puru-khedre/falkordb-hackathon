"""ContextAnchor FastAPI server (multi-project)."""
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.falkor_client import FalkorClient, DEFAULT_GRAPH
from app import seed_data, agent
from app.ingest import ingest_repo
from app import diff_analyze, genrules
from fastapi.responses import PlainTextResponse

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app = FastAPI(title="ContextAnchor", version="2.0", docs_url="/swagger", redoc_url=None)

SCENARIOS = {
    "1": {"function": "calculate_discount", "title": "Refactor calculate_discount (Billing)",
          "prompt": "I want to change how calculate_discount() works in billing_service.py."},
    "2": {"function": "issue_token", "title": "Architecture rule check: token handling (Auth)",
          "prompt": "I want to mint a raw JWT inside issue_token() directly."},
    "3": {"function": "login", "title": "Ownership & ADR audit (Auth handler)",
          "prompt": "Who owns login() and what architecture decision applies?"},
}

_client = None


def client():
    global _client
    if _client is None:
        _client = FalkorClient()
    return _client


def use(project):
    c = client()
    c.use(project if project else DEFAULT_GRAPH)
    return c


@app.on_event("startup")
def _startup():
    try:
        c = client()
        need = c.is_empty(DEFAULT_GRAPH)
        if not need:
            try:
                row = c.db.select_graph(DEFAULT_GRAPH).query(
                    "MATCH (f:Function) RETURN f.fid, f.doc LIMIT 1").result_set
                if row and (row[0][0] is None or row[0][1] is None):  # pre-fid/pre-doc -> re-seed
                    need = True
            except Exception:
                need = True
        if need:
            print("[ContextAnchor] seeding sample:", seed_data.seed(c))
    except Exception as e:
        print("[ContextAnchor] startup warning:", e)


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/manage")
def manage_page():
    return FileResponse(os.path.join(STATIC_DIR, "manage.html"))


@app.get("/landing")
def landing_page():
    return FileResponse(os.path.join(STATIC_DIR, "landing.html"))


@app.get("/docs")
def docs_page():
    return FileResponse(os.path.join(STATIC_DIR, "docs.html"))


@app.get("/api/health")
def health():
    try:
        c = client()
        return {"status": "ok", "llm": bool(c.get_llm_config()["api_key"]),
                "github": bool(c.get_github_token()),
                "projects": len(c.list_projects())}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "down", "error": str(e)})


@app.get("/api/projects")
def projects(counts: bool = False):
    c = client()
    projs = c.list_projects()
    if counts:
        for p in projs:
            p["counts"] = c.project_counts(p["graph"])
    return {"projects": projs, "active": c.active, "default": DEFAULT_GRAPH}


@app.get("/api/graph")
def graph(project: str = ""):
    return use(project).full_graph_viz()


@app.get("/api/overview")
def overview(project: str = ""):
    c = use(project)
    info = next((p for p in c.list_projects() if p["graph"] == c.active), {})
    return {"project": c.active, "label": info.get("label", c.active),
            "kind": info.get("kind", "repo"),
            "counts": c.project_counts(c.active),
            "chokepoints": c.centrality(limit=5)}


@app.get("/api/schema")
def schema(project: str = ""):
    return use(project).schema()


class AnalyzeIn(BaseModel):
    function: str
    project: str = ""


@app.post("/api/analyze")
def analyze(body: AnalyzeIn):
    c = use(body.project)
    res = c.resolve(body.function)
    if res["candidates"]:
        raise HTTPException(409, {"message": "Multiple functions share that name  pick one.",
                                  "candidates": res["candidates"]})
    if not res["fid"]:
        raise HTTPException(404, f"No function '{body.function}' in project '{c.active}'.")
    fid = res["fid"]
    r = agent.analyze(c, fid)
    r["project"] = c.active
    r["viz"] = c.impact_viz(fid)
    r["narration"] = agent.narrate(r, c.get_llm_config())
    return r


@app.get("/api/scenario/{sid}")
def scenario(sid: str):
    if sid not in SCENARIOS:
        raise HTTPException(404, "Unknown scenario")
    s = SCENARIOS[sid]
    c = use(DEFAULT_GRAPH)  # scenarios always demo the sample graph
    fid = c.resolve(s["function"])["fid"]
    r = agent.analyze(c, fid)
    r["scenario"] = s
    r["project"] = c.active
    r["viz"] = c.impact_viz(fid)
    r["narration"] = agent.narrate(r, c.get_llm_config())
    return r


@app.get("/api/scenarios")
def scenarios():
    return SCENARIOS


class IngestIn(BaseModel):
    source: str


@app.post("/api/ingest")
def ingest(body: IngestIn):
    try:
        summary = ingest_repo(client(), body.source, token=client().get_github_token())
    except Exception as e:
        raise HTTPException(500, f"Ingest failed: {e}")
    return {"ingested": summary}


@app.post("/api/reseed")
def reseed():
    return {"seeded": seed_data.seed(client())}


class RuleIn(BaseModel):
    id: str
    text: str
    severity: str = "MEDIUM"
    target_fn: str = ""
    target_file: str = ""
    project: str = ""


@app.post("/api/rule")
def add_rule(body: RuleIn):
    c = use(body.project)
    return c.add_rule(body.id, body.text, body.severity,
                      body.target_fn or None, body.target_file or None)


@app.get("/api/rules")
def rules(project: str = ""):
    return {"rules": use(project).all_rules()}


@app.get("/api/functions")
def functions(project: str = "", q: str = ""):
    rows = use(project).functions_list(limit=5000)
    if q:
        ql = q.lower()
        rows = [x for x in rows if ql in x["name"].lower()]
    # dedup by fid (unique); same name across files stays distinct
    seen, uniq = set(), []
    for x in rows:
        if x["fid"] not in seen:
            seen.add(x["fid"])
            uniq.append(x)
    uniq.sort(key=lambda x: (x["name"].startswith("__"), x["name"].lower(), x["file"]))
    return {"functions": uniq[:120], "count": len(uniq)}


class DiffIn(BaseModel):
    diff: str
    project: str = ""


@app.post("/api/analyze_diff")
def analyze_diff_ep(body: DiffIn):
    if body.project:
        c = use(body.project)
    else:
        c = client()
        hunks = list(diff_analyze.changed_hunks(body.diff))
        if hunks:
            sample_file = hunks[0][0]
            base = os.path.basename(sample_file)
            exists = c.run("""MATCH (f:Function) WHERE f.file = $p OR f.file = $base
                              OR $p ENDS WITH ('/' + f.file) OR f.file ENDS WITH ('/' + $p)
                              RETURN f.name LIMIT 1""", {"p": sample_file, "base": base}).result_set
            if not exists:
                for p in c.list_projects():
                    g = p.get("graph")
                    if g == c.active:
                        continue
                    c.use(g)
                    if c.run("""MATCH (f:Function) WHERE f.file = $p OR f.file = $base
                                OR $p ENDS WITH ('/' + f.file) OR f.file ENDS WITH ('/' + $p)
                                RETURN f.name LIMIT 1""", {"p": sample_file, "base": base}).result_set:
                        break
    report = diff_analyze.analyze_diff(c, body.diff)
    report["project"] = c.active
    report["markdown"] = diff_analyze.to_markdown(report, c.active)
    return report


class FileIn(BaseModel):
    file: str
    project: str = ""


@app.post("/api/analyze_file")
def analyze_file_ep(body: FileIn):
    if body.project:
        c = use(body.project)
    else:
        c = client()
        base = os.path.basename(body.file)
        exists = c.run("""MATCH (f:Function) WHERE f.file = $p OR f.file = $base
                          OR $p ENDS WITH ('/' + f.file) OR f.file ENDS WITH ('/' + $p)
                          RETURN f.name LIMIT 1""", {"p": body.file, "base": base}).result_set
        if not exists:
            for p in c.list_projects():
                g = p.get("graph")
                if g == c.active:
                    continue
                c.use(g)
                if c.run("""MATCH (f:Function) WHERE f.file = $p OR f.file = $base
                            OR $p ENDS WITH ('/' + f.file) OR f.file ENDS WITH ('/' + $p)
                            RETURN f.name LIMIT 1""", {"p": body.file, "base": base}).result_set:
                    break
    return diff_analyze.analyze_file(c, body.file)


@app.get("/api/export/rules", response_class=PlainTextResponse)
def export_rules(project: str = "", format: str = "claude"):
    return genrules.build(use(project), format)


class GraphIn(BaseModel):
    graph: str


@app.post("/api/project/delete")
def project_delete(body: GraphIn):
    client().delete_project(body.graph)
    return {"deleted": body.graph}


@app.post("/api/project/refresh")
def project_refresh(body: GraphIn):
    c = client()
    if body.graph == DEFAULT_GRAPH:
        return {"refreshed": body.graph, "seeded": seed_data.seed(c)}
    info = c.repo_of(body.graph)
    if not info.get("repo"):
        raise HTTPException(404, "Unknown project")
    try:
        summary = ingest_repo(c, info["repo"], token=c.get_github_token())
    except Exception as e:
        raise HTTPException(500, f"Refresh failed: {e}")
    return {"refreshed": body.graph, "ingested": summary}


class RuleDelIn(BaseModel):
    id: str
    project: str = ""


@app.post("/api/rule/delete")
def rule_delete(body: RuleDelIn):
    return use(body.project).delete_rule(body.id)


def _mask(v):
    if not v:
        return ""
    return ("*" * max(0, len(v) - 4)) + v[-4:]


@app.get("/api/settings")
def settings_get():
    c = client()
    llm = c.get_llm_config()
    return {"llm": {"base_url": llm["base_url"], "model": llm["model"],
                    "key_set": bool(llm["api_key"]), "key_masked": _mask(llm["api_key"])},
            "github": {"connected": bool(c.get_github_token()),
                       "token_masked": _mask(c.get_github_token())}}


class SettingsIn(BaseModel):
    github_token: str = ""
    nvidia_api_key: str = ""
    nvidia_base_url: str = ""
    nvidia_model: str = ""


@app.post("/api/settings")
def settings_set(body: SettingsIn):
    upd = {k: v for k, v in body.dict().items() if v.strip()}
    client().set_config(upd)
    return settings_get()


def _ask_context(c, question):
    import re as _re
    toks = [t for t in _re.findall(r"[A-Za-z_]{3,}", question.lower())]
    lines = []
    seen = set()
    for t in toks[:6]:
        rows = c.run("""MATCH (f:Function) WHERE toLower(f.name) CONTAINS $t
                        RETURN f.name, f.file, f.doc LIMIT 8""", {"t": t}).result_set
        for name, file, doc in rows:
            key = name + file
            if key not in seen:
                seen.add(key)
                d = f"  {doc}" if doc else ""
                lines.append(f"- function {name}() in {file}{d}")
    fn_ctx = "\n".join(lines[:15])
    rules = c.all_rules()
    rule_ctx = "\n".join(f"- rule {r['id']} ({r['severity']}): {r['rule']}" for r in rules[:12])
    chokes = c.centrality(limit=5)
    ch_ctx = "\n".join(f"- chokepoint {x['function']}() score {x['score']}" for x in chokes)
    parts = []
    if fn_ctx: parts.append("Matching functions:\n" + fn_ctx)
    if rule_ctx: parts.append("Team rules:\n" + rule_ctx)
    if ch_ctx: parts.append("Chokepoints:\n" + ch_ctx)
    return "\n\n".join(parts)


class AskIn(BaseModel):
    question: str
    project: str = ""


@app.post("/api/ask")
def ask(body: AskIn):
    c = use(body.project)
    ctx = _ask_context(c, body.question)
    res = agent.answer_question(c.get_llm_config(), body.question, ctx)
    res["project"] = c.active
    return res


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
