"""FalkorDB access layer for ContextAnchor.

Multi-project: every ingested repo lives in its own FalkorDB graph, and a small
`ca_meta` graph keeps the list of projects. Every product feature is a graph
operation  remove FalkorDB and blast-radius, centrality, rule governance and
ownership all stop working. There is no second store. (Rule #3.)
"""
import os
import re

DEFAULT_GRAPH = os.getenv("GRAPH_NAME", "contextanchor")
META_GRAPH = "ca_meta"

_KEY_PROP = {
    "File": "path", "Function": "fid", "Endpoint": "route",
    "Developer": "name", "TeamRule": "id", "ADR": "id",
}


def _label(node):
    labels = list(node.labels) if node.labels else []
    return labels[0] if labels else "Node"


def node_key(node):
    lbl = _label(node)
    prop = _KEY_PROP.get(lbl, "name")
    val = node.properties.get(prop, str(node.id))
    return f"{lbl}:{val}"


def slug(name):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower()).strip("_")
    return s or "project"


class FalkorClient:
    def __init__(self):
        from falkordb import FalkorDB
        host = os.getenv("FALKORDB_HOST", "localhost")
        port = int(os.getenv("FALKORDB_PORT", "6379"))
        self.db = FalkorDB(host=host, port=port)
        self.active = DEFAULT_GRAPH
        self.graph = self.db.select_graph(self.active)
        self._choke_cache = {}

    # ---- project / graph selection --------------------------------------
    def use(self, graph_name):
        self.active = graph_name
        self.graph = self.db.select_graph(graph_name)
        return self

    def run(self, cypher, params=None):
        return self.graph.query(cypher, params or {})

    def is_empty(self, graph_name=None):
        g = self.db.select_graph(graph_name) if graph_name else self.graph
        try:
            return g.query("MATCH (n) RETURN count(n) AS c").result_set[0][0] == 0
        except Exception:
            return True

    def reset(self):
        try:
            self.graph.delete()
        except Exception:
            pass
        self._choke_cache.pop(self.active, None)
        self.graph = self.db.select_graph(self.active)

    # ---- project registry (stored in its own graph) ---------------------
    def register_project(self, graph_name, label, repo, kind="repo"):
        m = self.db.select_graph(META_GRAPH)
        m.query("""
            MERGE (p:Project {graph: $g})
            SET p.label = $label, p.repo = $repo, p.kind = $kind
        """, {"g": graph_name, "label": label, "repo": repo, "kind": kind})

    def list_projects(self):
        m = self.db.select_graph(META_GRAPH)
        try:
            res = m.query("MATCH (p:Project) RETURN p.graph, p.label, p.repo, p.kind")
        except Exception:
            return []
        return [{"graph": r[0], "label": r[1], "repo": r[2], "kind": r[3]}
                for r in res.result_set]

    def delete_project(self, graph_name):
        try:
            self.db.select_graph(graph_name).delete()
        except Exception:
            pass
        m = self.db.select_graph(META_GRAPH)
        m.query("MATCH (p:Project {graph:$g}) DELETE p", {"g": graph_name})
        if self.active == graph_name:
            self.use(DEFAULT_GRAPH)

    def repo_of(self, graph_name):
        m = self.db.select_graph(META_GRAPH)
        r = m.query("MATCH (p:Project {graph:$g}) RETURN p.repo, p.label, p.kind",
                    {"g": graph_name}).result_set
        return {"repo": r[0][0], "label": r[0][1], "kind": r[0][2]} if r else {}

    def project_counts(self, graph_name):
        g = self.db.select_graph(graph_name)
        def n(q):
            try:
                return g.query(q).result_set[0][0]
            except Exception:
                return 0
        return {"functions": n("MATCH (f:Function) RETURN count(f)"),
                "files": n("MATCH (f:File) RETURN count(f)"),
                "rules": n("MATCH (r:TeamRule) RETURN count(r)"),
                "developers": n("MATCH (d:Developer) RETURN count(d)")}

    # ---- app config (single LLM + GitHub token), stored in ca_meta ------
    _CFG_KEYS = {"github_token", "nvidia_api_key", "nvidia_base_url", "nvidia_model"}

    def get_config(self):
        m = self.db.select_graph(META_GRAPH)
        try:
            r = m.query("MATCH (c:Config {id:'app'}) RETURN c").result_set
            return dict(r[0][0].properties) if r else {}
        except Exception:
            return {}

    def set_config(self, updates):
        upd = {k: v for k, v in updates.items() if k in self._CFG_KEYS and v is not None}
        if upd:
            m = self.db.select_graph(META_GRAPH)
            sets = ", ".join(f"c.{k} = ${k}" for k in upd)
            m.query(f"MERGE (c:Config {{id:'app'}}) SET {sets}", upd)
        return self.get_config()

    def get_llm_config(self):
        cfg = self.get_config()
        return {"api_key": (cfg.get("nvidia_api_key") or os.getenv("NVIDIA_API_KEY", "")).strip(),
                "base_url": cfg.get("nvidia_base_url") or os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                "model": cfg.get("nvidia_model") or os.getenv("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")}

    def get_github_token(self):
        return (self.get_config().get("github_token") or os.getenv("GITHUB_TOKEN", "")).strip()

    def delete_rule(self, rule_id):
        self.run("MATCH (r:TeamRule {id:$id}) DETACH DELETE r", {"id": rule_id})
        return {"deleted": rule_id}

    # ---- schema introspection -------------------------------------------
    def schema(self):
        def names(proc):
            try:
                return [r[0] for r in self.run(proc).result_set]
            except Exception:
                return []
        return {"labels": names("CALL db.labels()"),
                "relationshipTypes": names("CALL db.relationshipTypes()"),
                "propertyKeys": names("CALL db.propertyKeys()")}

    def functions_list(self, limit=500):
        res = self.run("MATCH (f:Function) RETURN f.fid, f.name, f.file ORDER BY f.name LIMIT $l",
                       {"l": limit})
        return [{"fid": r[0], "name": r[1], "file": r[2]} for r in res.result_set]

    def resolve(self, ident):
        """Map a user-supplied identifier (fid or bare name) to a unique fid."""
        if "::" in ident:
            r = self.run("MATCH (f:Function {fid:$x}) RETURN f.fid,f.name,f.file LIMIT 1",
                         {"x": ident}).result_set
            if r:
                return {"fid": r[0][0], "name": r[0][1], "file": r[0][2], "candidates": []}
            return {"fid": None, "candidates": []}
        rows = self.run("MATCH (f:Function {name:$n}) RETURN f.fid,f.name,f.file",
                        {"n": ident}).result_set
        cands = [{"fid": x[0], "name": x[1], "file": x[2]} for x in rows]
        if len(cands) == 1:
            c = cands[0]
            return {"fid": c["fid"], "name": c["name"], "file": c["file"], "candidates": []}
        return {"fid": None, "candidates": cands}

    def func_info(self, fid):
        r = self.run("MATCH (f:Function {fid:$x}) RETURN f.name, f.file, f.doc LIMIT 1",
                     {"x": fid}).result_set
        if r:
            return {"name": r[0][0], "file": r[0][1], "doc": r[0][2] or ""}
        return {"name": fid, "file": "", "doc": ""}

    # ---- Track 1: blast radius ------------------------------------------
    def blast_radius(self, fid):
        q_fn = """
        MATCH (target:Function {fid: $fid})
        MATCH p = (caller:Function)-[:CALLS*1..3]->(target)
        WITH caller, min(length(p)) AS depth
        RETURN caller.fid AS cfid, caller.name AS fn, caller.file AS file, depth
        ORDER BY depth ASC, fn ASC
        """
        res = self.run(q_fn, {"fid": fid})
        affected = [{"fid": r[0], "function": r[1], "file": r[2], "hops": r[3]} for r in res.result_set]
        q_api = """
        MATCH (target:Function {fid: $fid})
        MATCH (caller:Function)-[:CALLS*0..3]->(target)
        MATCH (ep:Endpoint)-[:EXECUTES]->(caller)
        RETURN DISTINCT ep.route AS route, ep.method AS method
        """
        res2 = self.run(q_api, {"fid": fid})
        apis = [{"route": r[0], "method": r[1]} for r in res2.result_set]
        return {"affected_functions": affected, "impacted_apis": apis}

    # ---- Track 1: centrality (native GraphBLAS algorithm) ---------------
    def centrality(self, limit=5):
        q = """
        CALL algo.betweenness({nodeLabels: ['Function'], relationshipTypes: ['CALLS'], samplingSize: 10000, samplingSeed: 7})
        YIELD node, score
        RETURN node.fid AS fid, node.name AS fn, node.file AS file, score
        ORDER BY score DESC
        LIMIT $limit
        """
        try:
            res = self.run(q, {"limit": limit})
            rows = [{"fid": r[0], "function": r[1], "file": r[2], "score": round(float(r[3]), 4),
                     "method": "algo.betweenness"} for r in res.result_set]
            if rows:
                return rows
        except Exception:
            pass
        qf = """
        MATCH (f:Function)
        OPTIONAL MATCH (caller:Function)-[:CALLS*1..2]->(f)
        WITH f, count(DISTINCT caller) AS reach
        RETURN f.fid AS fid, f.name AS fn, f.file AS file, reach
        ORDER BY reach DESC
        LIMIT $limit
        """
        res = self.run(qf, {"limit": limit})
        return [{"fid": r[0], "function": r[1], "file": r[2], "score": int(r[3]),
                 "method": "upstream-reach (fallback)"} for r in res.result_set]

    def top_chokepoint(self):
        if self.active in self._choke_cache:
            return self._choke_cache[self.active]
        rows = self.centrality(limit=1)
        res = rows[0] if rows else None
        self._choke_cache[self.active] = res
        return res

    # ---- Track 2: team rules --------------------------------------------
    def rules_for(self, fid):
        q_direct = """
        MATCH (rule:TeamRule)-[:GOVERNS]->(:Function {fid: $fid})
        RETURN rule.id, rule.rule_text, rule.severity, rule.created_at
        """
        q_file = """
        MATCH (f:File)-[:CONTAINS]->(:Function {fid: $fid})
        MATCH (rule:TeamRule)-[:GOVERNS]->(f)
        RETURN rule.id, rule.rule_text, rule.severity, rule.created_at
        """
        rows = {}
        order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        for q in (q_direct, q_file):
            for r in self.run(q, {"fid": fid}).result_set:
                rows[r[0]] = {"id": r[0], "rule": r[1], "severity": r[2], "created_at": r[3]}
        return sorted(rows.values(), key=lambda x: order.get(x["severity"], 9))

    def add_rule(self, rule_id, text, severity, target_fn=None, target_file=None, created_at=None):
        import datetime
        created_at = created_at or datetime.date.today().isoformat()
        self.run("""MERGE (r:TeamRule {id: $id})
                    SET r.rule_text=$t, r.severity=$s, r.created_at=$c""",
                 {"id": rule_id, "t": text, "s": severity.upper(), "c": created_at})
        if target_fn:
            self.run("""MATCH (r:TeamRule {id:$id}),(f:Function {name:$fn})
                        MERGE (r)-[:GOVERNS]->(f)""", {"id": rule_id, "fn": target_fn})
        if target_file:
            self.run("""MATCH (r:TeamRule {id:$id}),(f:File {path:$fp})
                        MERGE (r)-[:GOVERNS]->(f)""", {"id": rule_id, "fp": target_file})
        return {"id": rule_id}

    def all_rules(self):
        res = self.run("""MATCH (r:TeamRule) OPTIONAL MATCH (r)-[:GOVERNS]->(t)
                          RETURN r.id, r.rule_text, r.severity, r.created_at,
                                 labels(t)[0], coalesce(t.name, t.path)""")
        out = {}
        for r in res.result_set:
            out.setdefault(r[0], {"id": r[0], "rule": r[1], "severity": r[2],
                                  "created_at": r[3], "targets": []})
            if r[4]:
                out[r[0]]["targets"].append({"type": r[4], "name": r[5]})
        return list(out.values())

    # ---- Track 3: ownership + ADR ---------------------------------------
    def ownership(self, fid):
        q = """
        MATCH (target:Function {fid: $fid})<-[:CONTAINS]-(f:File)
        OPTIONAL MATCH (dev:Developer)-[a:AUTHORED]->(f)
        OPTIONAL MATCH (adr:ADR)-[:APPLIES_TO]->(f)
        RETURN f.path, dev.name, dev.email, dev.role,
               a.commits, a.last_touched, adr.id, adr.title, adr.decision
        ORDER BY a.commits DESC
        """
        res = self.run(q, {"fid": fid})
        if not res.result_set:
            return {}
        r = res.result_set[0]
        out = {"file": r[0]}
        if r[1]:
            out["author"] = {"name": r[1], "email": r[2], "role": r[3],
                             "commits": r[4], "last_touched": r[5]}
        if r[6]:
            out["adr"] = {"id": r[6], "title": r[7], "decision": r[8]}
        return out

    # ---- Discovery: keyword / NL search across the graph ----------------
    def search(self, term, limit=10):
        import re as _re
        words = [w for w in _re.split(r"[^a-z0-9]+", (term or "").lower()) if len(w) > 1]
        if not words:
            return {"functions": [], "files": [], "endpoints": [], "rules": [], "adrs": []}
        p = {"words": words, "lim": int(limit)}

        def q(cypher):
            try:
                return self.run(cypher, p).result_set
            except Exception:
                return []

        funcs = q("""MATCH (f:Function)
                     WHERE any(w IN $words WHERE toLower(f.name) CONTAINS w
                               OR toLower(coalesce(f.doc,'')) CONTAINS w)
                     RETURN f.fid, f.name, f.file, coalesce(f.doc,'')
                     ORDER BY f.name LIMIT $lim""")
        files = q("""MATCH (f:File)
                     WHERE any(w IN $words WHERE toLower(f.path) CONTAINS w)
                     RETURN f.path, coalesce(f.module,'') LIMIT $lim""")
        eps = q("""MATCH (e:Endpoint)
                   WHERE any(w IN $words WHERE toLower(e.route) CONTAINS w
                             OR toLower(coalesce(e.service,'')) CONTAINS w)
                   RETURN e.route, e.method, coalesce(e.service,'') LIMIT $lim""")
        rules = q("""MATCH (r:TeamRule)
                     WHERE any(w IN $words WHERE toLower(r.rule_text) CONTAINS w
                               OR toLower(r.id) CONTAINS w)
                     RETURN r.id, r.rule_text, r.severity LIMIT $lim""")
        adrs = q("""MATCH (a:ADR)
                    WHERE any(w IN $words WHERE toLower(coalesce(a.title,'')) CONTAINS w
                              OR toLower(coalesce(a.decision,'')) CONTAINS w
                              OR toLower(a.id) CONTAINS w)
                    RETURN a.id, a.title, coalesce(a.status,'') LIMIT $lim""")
        return {
            "functions": [{"fid": r[0], "name": r[1], "file": r[2], "doc": r[3]} for r in funcs],
            "files": [{"path": r[0], "module": r[1]} for r in files],
            "endpoints": [{"route": r[0], "method": r[1], "service": r[2]} for r in eps],
            "rules": [{"id": r[0], "rule": r[1], "severity": r[2]} for r in rules],
            "adrs": [{"id": r[0], "title": r[1], "status": r[2]} for r in adrs],
        }

    # ---- Visualization payload ------------------------------------------
    def full_graph_viz(self, max_nodes=400):
        res = self.run("MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m LIMIT $l",
                       {"l": max_nodes * 6})
        nodes, edges = {}, {}

        def add_node(n):
            if n is None:
                return
            nid = node_key(n)
            if nid not in nodes:
                lbl = _label(n)
                prop = _KEY_PROP.get(lbl, "name")
                nodes[nid] = {"data": {"id": nid, "label": str(n.properties.get(prop, nid)),
                                       "ntype": lbl,
                                       "props": {k: _san(v) for k, v in n.properties.items()}}}
        for row in res.result_set:
            n, r, m = row[0], row[1], row[2]
            add_node(n)
            if m is not None and r is not None:
                add_node(m)
                src, dst = node_key(n), node_key(m)
                eid = f"{src}|{r.relation}|{dst}"
                edges.setdefault(eid, {"data": {"id": eid, "source": src,
                                                "target": dst, "label": r.relation}})
        return {"nodes": list(nodes.values()), "edges": list(edges.values()),
                "project": self.active}

    def impact_viz(self, fid, max_callers=40):
        """Focused neighborhood subgraph around one function (keyed by fid).
        Stays small/readable no matter how large the repo is."""
        nodes, edges, seen = [], [], set()

        def add_node(ntype, key, label):
            nid = f"{ntype}:{key}"
            if nid in seen:
                return nid
            seen.add(nid)
            nodes.append({"data": {"id": nid, "label": str(label), "ntype": ntype}})
            return nid

        def add_edge(src, dst, rel):
            edges.append({"data": {"id": f"{src}|{rel}|{dst}", "source": src,
                                   "target": dst, "label": rel}})

        trow = self.run("""MATCH (t:Function {fid:$fid})
                           OPTIONAL MATCH (f:File)-[:CONTAINS]->(t)
                           RETURN t.name, t.file, f.path LIMIT 1""",
                        {"fid": fid}).result_set
        if not trow:
            return {"nodes": [], "edges": []}
        tname, tfile = trow[0][0], (trow[0][2] or trow[0][1])
        add_node("Function", fid, tname)

        callers = self.run(
            """MATCH (c:Function)-[:CALLS*1..3]->(:Function {fid:$fid})
               RETURN DISTINCT c.fid, c.name LIMIT $lim""",
            {"fid": fid, "lim": max_callers}).result_set
        callees = self.run(
            """MATCH (:Function {fid:$fid})-[:CALLS]->(b:Function)
               RETURN DISTINCT b.fid, b.name LIMIT 20""", {"fid": fid}).result_set
        fset = {fid}
        for cfid, cname in list(callers) + list(callees):
            fset.add(cfid)
            add_node("Function", cfid, cname)

        for a, b in self.run(
            """MATCH (a:Function)-[:CALLS]->(b:Function)
               WHERE a.fid IN $s AND b.fid IN $s RETURN a.fid, b.fid""",
            {"s": list(fset)}).result_set:
            add_edge(f"Function:{a}", f"Function:{b}", "CALLS")

        if tfile:
            fnode = add_node("File", tfile, tfile)
            add_edge(fnode, f"Function:{fid}", "CONTAINS")

        for route, method, fnfid in self.run(
            """MATCH (ep:Endpoint)-[:EXECUTES]->(fn:Function)
               WHERE fn.fid IN $s RETURN ep.route, ep.method, fn.fid""",
            {"s": list(fset)}).result_set:
            eid = add_node("Endpoint", route, f"{method} {route}")
            add_edge(eid, f"Function:{fnfid}", "EXECUTES")

        for r in self.rules_for(fid):
            rid = add_node("TeamRule", r["id"], r["id"])
            add_edge(rid, f"Function:{fid}", "GOVERNS")

        own = self.ownership(fid)
        if own.get("file"):
            fnode = add_node("File", own["file"], own["file"])
            if own.get("author"):
                did = add_node("Developer", own["author"]["name"], own["author"]["name"])
                add_edge(did, fnode, "AUTHORED")
            if own.get("adr"):
                aid = add_node("ADR", own["adr"]["id"], own["adr"]["id"])
                add_edge(aid, fnode, "APPLIES_TO")
        return {"nodes": nodes, "edges": edges}


def _san(v):
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)
