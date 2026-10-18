"""Ingest ANY real codebase into FalkorDB.

Languages: Python (via stdlib `ast`, precise) and JavaScript/TypeScript/Go/Java
(via lightweight regex extractors). Each function gets a unique id `file::name`
(fid), so two functions with the same name in different files never get merged.
Ownership comes from real `git log`.

    python -m app.ingest --repo https://github.com/user/repo
    python -m app.ingest --repo ./sample_repo
"""
import argparse
import ast
import os
import re
import subprocess
import tempfile
from collections import Counter

PY_EXT = {".py"}
JS_EXT = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}
GO_EXT = {".go"}
JAVA_EXT = {".java"}
SUPPORTED = PY_EXT | JS_EXT | GO_EXT | JAVA_EXT
HTTP_METHODS = {"get", "post", "put", "delete", "patch"}

_KW = {"if", "for", "while", "switch", "catch", "return", "function", "new",
       "typeof", "await", "async", "class", "else", "do", "super", "try",
       "throw", "const", "let", "var", "import", "export", "default", "case",
       "break", "continue", "in", "of", "void", "yield", "with", "func"}


def is_git_url(src):
    return src.startswith(("http://", "https://", "git@", "ssh://")) or src.endswith(".git")


def _clone(url, token=""):
    tmp = tempfile.mkdtemp(prefix="ca_repo_")
    clone_url = url
    if token and url.startswith("https://github.com/"):
        clone_url = url.replace("https://github.com/",
                                f"https://x-access-token:{token}@github.com/")
    subprocess.run(["git", "clone", "--depth", "100", clone_url, tmp],
                   check=True, capture_output=True, text=True, timeout=240)
    return tmp


def _lang(ext):
    if ext in PY_EXT: return "python"
    if ext in JS_EXT: return "js"
    if ext in GO_EXT: return "go"
    if ext in JAVA_EXT: return "java"
    return None


def _iter_files(repo_path):
    skip = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache",
            "site-packages", ".tox", "build", "dist", "vendor", ".next", "target",
            "test", "tests", "__tests__", "spec"}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d.lower() not in skip]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED:
                yield os.path.join(root, f), ext


# ---- Python (ast) ---------------------------------------------------------
def _py_defs_calls(rel, tree):
    defs, callsites, docmap = [], [], {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            defs.append((node.name, node.lineno))
            doc = (ast.get_docstring(node) or "").strip().split("\n")[0][:200]
            if doc:
                docmap.setdefault(node.name, doc)
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    c = None
                    if isinstance(sub.func, ast.Name): c = sub.func.id
                    elif isinstance(sub.func, ast.Attribute): c = sub.func.attr
                    if c:
                        callsites.append((node.name, node.lineno, c))
    return defs, callsites, docmap


def _comment_before(lines, line):
    """Grab a contiguous comment block immediately above a def line (any lang)."""
    out = []
    i = line - 2
    while i >= 0 and not lines[i].strip():
        i -= 1
    while i >= 0:
        t = lines[i].strip()
        if t.startswith("//"): out.append(t[2:].strip())
        elif t.startswith("#"): out.append(t[1:].strip())
        elif t.startswith("*/"): out.append(t[:-2].strip())
        elif t.startswith("/**"): out.append(t[3:].strip())
        elif t.startswith("/*"): out.append(t[2:].strip())
        elif t.startswith("*"): out.append(t[1:].strip())
        else: break
        i -= 1
    out = [x for x in reversed(out) if x]
    return " ".join(out)[:200]


def _py_endpoints(rel, module, tree):
    eps = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    attr = dec.func.attr.lower()
                    route = None
                    if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                        route = dec.args[0].value
                    if route and route.startswith("/"):
                        if attr in HTTP_METHODS:
                            eps.append((route, attr.upper(), module, node.name, node.lineno))
                        elif attr == "route":
                            eps.append((route, "ANY", module, node.name, node.lineno))
    return eps


# ---- Regex extractors (JS/TS/Go/Java) -------------------------------------
_JS_DEF = [
    re.compile(r"\bfunction\s+([A-Za-z_$][\w$]*)"),
    re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:function\b|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)"),
    re.compile(r"^\s*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^;{]*\)\s*\{", re.M),  # class methods
]
_GO_DEF = [re.compile(r"\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)\s*\(")]
_JAVA_DEF = [re.compile(r"(?:public|private|protected|static|final|synchronized|\s)+[\w<>\[\],\s]+\s+([A-Za-z_]\w*)\s*\([^;)]*\)\s*(?:throws[\w,\s.]*)?\{")]
_CALL = re.compile(r"\b([A-Za-z_$][\w$]*)\s*\(")
_JS_ROUTE = re.compile(r"\b(?:app|router|api|server)\.(get|post|put|delete|patch)\s*\(\s*['\"]([^'\"]+)['\"]")


def _line_of(text, idx):
    return text.count("\n", 0, idx) + 1


def _regex_defs_calls(text, lang):
    patterns = {"js": _JS_DEF, "go": _GO_DEF, "java": _JAVA_DEF}[lang]
    defs = []  # (name, line)
    for pat in patterns:
        for m in pat.finditer(text):
            name = m.group(1)
            if name and name not in _KW:
                defs.append((name, _line_of(text, m.start(1))))
    # dedup defs by (name,line)
    defs = sorted(set(defs), key=lambda x: x[1])
    # call sites: (callee, line)
    calls = [(m.group(1), _line_of(text, m.start(1)))
             for m in _CALL.finditer(text) if m.group(1) not in _KW]
    return defs, calls


def _regex_endpoints(text, module):
    eps = []
    for m in _JS_ROUTE.finditer(text):
        eps.append((m.group(2), m.group(1).upper(), module, None, _line_of(text, m.start())))
    return eps


# ---- unify ----------------------------------------------------------------
def parse_repo(repo_path):
    repo_path = os.path.abspath(repo_path)
    files = []
    func_rows = []            # {fid,name,file,line_no,lang,is_entrypoint}
    used_fids = set()
    name_to_fids = {}         # name -> [fid]
    filename_to_fid = {}      # (file,name) -> fid (first)
    per_file = []             # (rel, lang, text_or_tree, defs, callsites, endpoints_raw)

    def mk_fid(rel, name, line):
        base = f"{rel}::{name}"
        fid = base if base not in used_fids else f"{base}#{line}"
        while fid in used_fids:
            fid += "_"
        used_fids.add(fid)
        return fid

    for path, ext in _iter_files(repo_path):
        rel = os.path.relpath(path, repo_path)
        lang = _lang(ext)
        try:
            text = open(path, encoding="utf-8").read()
        except (UnicodeDecodeError, OSError):
            continue
        module = rel.replace(os.sep, ".").rsplit(".", 1)[0]
        if lang == "python":
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            defs, callsites, docmap = _py_defs_calls(rel, tree)
            eps = _py_endpoints(rel, module, tree)
        else:
            defs, calls = _regex_defs_calls(text, lang)
            _lines = text.split("\n")
            docmap = {n: _comment_before(_lines, l) for n, l in defs}
            # attribute each call to nearest preceding def in same file
            dsorted = sorted(defs, key=lambda x: x[1])
            callsites = []
            for callee, cline in calls:
                caller = None
                for dname, dline in dsorted:
                    if dline <= cline:
                        caller = (dname, dline)
                    else:
                        break
                if caller:
                    callsites.append((caller[0], caller[1], callee))
            eps = _regex_endpoints(text, module)
        if not defs:
            continue
        files.append({"path": rel, "module": module})
        for name, line in defs:
            fid = mk_fid(rel, name, line)
            func_rows.append({"fid": fid, "name": name, "file": rel, "line_no": line,
                              "lang": lang, "doc": docmap.get(name, ""),
                              "is_entrypoint": name in ("main", "handler")})
            name_to_fids.setdefault(name, []).append(fid)
            filename_to_fid.setdefault((rel, name), fid)
        per_file.append((rel, lang, defs, callsites, eps))

    # resolve CALLS to fids
    def resolve_callee(rel, callee):
        if (rel, callee) in filename_to_fid:
            return filename_to_fid[(rel, callee)]
        fids = name_to_fids.get(callee, [])
        return fids[0] if len(fids) == 1 else None

    calls = set()
    endpoints = []
    for rel, lang, defs, callsites, eps in per_file:
        for caller_name, caller_line, callee in callsites:
            cfid = filename_to_fid.get((rel, caller_name))
            if not cfid:
                continue
            tfid = resolve_callee(rel, callee)
            if tfid and tfid != cfid:
                calls.add((cfid, tfid))
        for route, method, service, fn_name, line in eps:
            fn_fid = filename_to_fid.get((rel, fn_name)) if fn_name else None
            endpoints.append({"route": route, "method": method, "service": service,
                              "fn_fid": fn_fid})
    return files, func_rows, [list(c) for c in calls], endpoints


def git_owners(repo_path, files):
    owners = []
    if not os.path.isdir(os.path.join(repo_path, ".git")):
        return owners
    for f in files:
        rel = f["path"]
        try:
            out = subprocess.run(["git", "-C", repo_path, "log", "-n", "400",
                                  "--format=%an\t%ae", "--", rel],
                                 capture_output=True, text=True, timeout=30).stdout.strip()
        except Exception:
            continue
        rows = [ln.split("\t") for ln in out.splitlines() if "\t" in ln]
        if not rows:
            continue
        names = Counter(r[0] for r in rows)
        top, commits = names.most_common(1)[0]
        email = next((r[1] for r in rows if r[0] == top), "")
        try:
            last = subprocess.run(["git", "-C", repo_path, "log", "-n", "1",
                                   "--format=%ad", "--date=short", "--", rel],
                                  capture_output=True, text=True, timeout=15).stdout.strip()
        except Exception:
            last = ""
        owners.append({"name": top, "email": email, "role": "Contributor",
                       "file": rel, "commits": commits, "last_touched": last})
    return owners


def ingest_repo(client, source, token=""):
    cleanup = None
    if is_git_url(source):
        repo_path = _clone(source, token); cleanup = repo_path
        label = re.sub(r"\.git$", "", source.rstrip("/").split("/")[-1]) or "repo"
        repo_ref = source
    else:
        repo_path = os.path.abspath(source)
        if not os.path.isdir(repo_path):
            raise FileNotFoundError(f"Not a directory: {source}")
        label = os.path.basename(repo_path.rstrip("/")) or "repo"
        repo_ref = repo_path
    try:
        files, funcs, calls, endpoints = parse_repo(repo_path)
        owners = git_owners(repo_path, files)
        from app.falkor_client import slug
        graph_name = "proj_" + slug(label)
        client.use(graph_name); client.reset()

        client.run("UNWIND $r AS x CREATE (:File {path:x.path, module:x.module})", {"r": files})
        client.run("""UNWIND $r AS x CREATE (:Function {fid:x.fid, name:x.name, file:x.file,
                      line_no:x.line_no, lang:x.lang, doc:x.doc, is_entrypoint:x.is_entrypoint})""", {"r": funcs})
        client.run("MATCH (f:File),(fn:Function) WHERE fn.file=f.path CREATE (f)-[:CONTAINS]->(fn)")
        if calls:
            client.run("""UNWIND $r AS x MATCH (a:Function {fid:x[0]}),(b:Function {fid:x[1]})
                          CREATE (a)-[:CALLS]->(b)""", {"r": calls})
        eps = [e for e in endpoints if e["fn_fid"]]
        if eps:
            client.run("""UNWIND $r AS x CREATE (:Endpoint {route:x.route, method:x.method, service:x.service, fn_fid:x.fn_fid})""", {"r": eps})
            client.run("""UNWIND $r AS x MATCH (e:Endpoint {route:x.route, method:x.method}),(fn:Function {fid:x.fn_fid})
                          CREATE (e)-[:EXECUTES]->(fn)""", {"r": eps})
        if owners:
            client.run("""UNWIND $r AS x MERGE (d:Developer {name:x.name}) SET d.email=x.email, d.role=x.role""", {"r": owners})
            client.run("""UNWIND $r AS x MATCH (d:Developer {name:x.name}),(f:File {path:x.file})
                          CREATE (d)-[:AUTHORED {commits:x.commits, last_touched:x.last_touched}]->(f)""", {"r": owners})

        client.register_project(graph_name, label, repo_ref)
        langs = sorted({f["lang"] for f in funcs})
        return {"project": label, "graph": graph_name, "repo": repo_ref,
                "files": len(files), "functions": len(funcs), "calls": len(calls),
                "endpoints": len(eps), "developers": len({o["name"] for o in owners}),
                "languages": langs}
    finally:
        if cleanup:
            subprocess.run(["rm", "-rf", cleanup], capture_output=True)


if __name__ == "__main__":
    from app.falkor_client import FalkorClient
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    args = ap.parse_args()
    print("Ingested:", ingest_repo(FalkorClient(), args.repo))
