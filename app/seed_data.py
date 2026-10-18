"""Seed a realistic microservices codebase graph into FalkorDB.

Runs automatically on web-app boot when the graph is empty, so a judge sees a
live glowing graph the instant they open the UI no manual import step.

The seeded names mirror ./sample_repo so `python -m app.ingest` on that folder
tells the same story the demo scenarios tell.
"""

FILES = [
    {"path": "database.py", "module": "core"},
    {"path": "auth_service.py", "module": "auth"},
    {"path": "billing_service.py", "module": "billing"},
    {"path": "order_service.py", "module": "orders"},
]

FUNCTIONS = [
    # database.py
    {"name": "get_connection", "file": "database.py", "line_no": 4, "is_entrypoint": False},
    {"name": "execute_query", "file": "database.py", "line_no": 9, "is_entrypoint": False},
    {"name": "fetch_user", "file": "database.py", "line_no": 15, "is_entrypoint": False},
    # auth_service.py
    {"name": "issue_token", "file": "auth_service.py", "line_no": 5, "is_entrypoint": False},
    {"name": "validate_token", "file": "auth_service.py", "line_no": 10, "is_entrypoint": False},
    {"name": "login", "file": "auth_service.py", "line_no": 16, "is_entrypoint": False},
    # billing_service.py
    {"name": "calculate_discount", "file": "billing_service.py", "line_no": 5, "is_entrypoint": False},
    {"name": "apply_tax", "file": "billing_service.py", "line_no": 13, "is_entrypoint": False},
    {"name": "create_invoice", "file": "billing_service.py", "line_no": 18, "is_entrypoint": False},
    # order_service.py
    {"name": "checkout", "file": "order_service.py", "line_no": 7, "is_entrypoint": False},
    {"name": "place_order", "file": "order_service.py", "line_no": 16, "is_entrypoint": True},
]

# (caller, callee)
CALLS = [
    ("fetch_user", "execute_query"),
    ("execute_query", "get_connection"),
    ("validate_token", "execute_query"),
    ("login", "fetch_user"),
    ("login", "issue_token"),
    ("create_invoice", "calculate_discount"),
    ("create_invoice", "apply_tax"),
    ("create_invoice", "execute_query"),
    ("checkout", "validate_token"),
    ("checkout", "fetch_user"),
    ("checkout", "calculate_discount"),
    ("checkout", "create_invoice"),
    ("place_order", "checkout"),
]

ENDPOINTS = [
    {"route": "/checkout", "method": "POST", "service": "orders", "fn": "place_order"},
    {"route": "/auth/login", "method": "POST", "service": "auth", "fn": "login"},
    {"route": "/invoices", "method": "GET", "service": "billing", "fn": "create_invoice"},
]

DEVELOPERS = [
    {"name": "Priya Nair", "email": "priya@acme.dev", "role": "Auth Lead",
     "file": "auth_service.py", "commits": 14, "last_touched": "2026-10-09"},
    {"name": "Arjun Rao", "email": "arjun@acme.dev", "role": "Billing Engineer",
     "file": "billing_service.py", "commits": 9, "last_touched": "2026-10-15"},
    {"name": "Meera Iyer", "email": "meera@acme.dev", "role": "Orders Engineer",
     "file": "order_service.py", "commits": 6, "last_touched": "2026-10-11"},
    {"name": "Kunal Shah", "email": "kunal@acme.dev", "role": "Platform / DB",
     "file": "database.py", "commits": 22, "last_touched": "2026-10-03"},
]

TEAM_RULES = [
    {"id": "RULE-4", "rule_text": "Discounts can never exceed 50% (Sprint 18 decision).",
     "severity": "HIGH", "created_at": "2026-09-20", "governs_fn": "calculate_discount"},
    {"id": "RULE-2", "rule_text": "Never mint raw tokens in a service; use the central OAuth2 issuer.",
     "severity": "HIGH", "created_at": "2026-08-30", "governs_fn": "issue_token"},
    {"id": "RULE-9", "rule_text": "No raw SQL in the service layer; all access goes through the ORM.",
     "severity": "MEDIUM", "created_at": "2026-07-14", "governs_file": "database.py"},
]

ADRS = [
    {"id": "ADR-12", "title": "Centralized OAuth2 session tokens",
     "decision": "All services obtain tokens from a single OAuth2 issuer; no local JWT minting.",
     "status": "ACCEPTED", "file": "auth_service.py"},
    {"id": "ADR-07", "title": "Expand-contract for billing changes",
     "decision": "Billing math changes ship behind a dual-write/expand-contract window.",
     "status": "ACCEPTED", "file": "billing_service.py"},
]

DOCS = {
    "get_connection": "Open a pooled DB connection.",
    "execute_query": "Run a raw SQL query; every service funnels through here.",
    "fetch_user": "Load a user row by id.",
    "issue_token": "Mint a session token for a user.",
    "validate_token": "Validate an incoming session token.",
    "login": "Authenticate credentials and return a token.",
    "calculate_discount": "Compute an order discount (capped at 50%).",
    "apply_tax": "Apply flat tax to an amount.",
    "create_invoice": "Build an invoice from discount and tax.",
    "checkout": "Checkout flow: validate token, load user, build invoice.",
    "place_order": "Public entrypoint hit by POST /checkout.",
}


def seed(client):
    from app.falkor_client import DEFAULT_GRAPH
    client.use(DEFAULT_GRAPH)
    for _fn in FUNCTIONS:
        _fn["doc"] = DOCS.get(_fn["name"], "")
    client.reset()
    g = client

    g.run("UNWIND $rows AS r CREATE (:File {path: r.path, module: r.module})",
          {"rows": FILES})
    g.run("""UNWIND $rows AS r
             CREATE (:Function {fid: r.file + '::' + r.name, name: r.name, file: r.file,
                                line_no: r.line_no, lang: 'python', doc: r.doc, is_entrypoint: r.is_entrypoint})""",
          {"rows": FUNCTIONS})
    g.run("""UNWIND $rows AS r
             CREATE (:Endpoint {route: r.route, method: r.method, service: r.service})""",
          {"rows": ENDPOINTS})
    g.run("""UNWIND $rows AS r
             CREATE (:Developer {name: r.name, email: r.email, role: r.role})""",
          {"rows": DEVELOPERS})
    g.run("""UNWIND $rows AS r
             CREATE (:TeamRule {id: r.id, rule_text: r.rule_text,
                                severity: r.severity, created_at: r.created_at})""",
          {"rows": TEAM_RULES})
    g.run("""UNWIND $rows AS r
             CREATE (:ADR {id: r.id, title: r.title, decision: r.decision, status: r.status})""",
          {"rows": ADRS})

    # File -[:CONTAINS]-> Function
    g.run("""MATCH (f:File), (fn:Function) WHERE fn.file = f.path
             CREATE (f)-[:CONTAINS]->(fn)""")

    # Function -[:CALLS]-> Function
    g.run("""UNWIND $rows AS r
             MATCH (a:Function {name: r[0]}), (b:Function {name: r[1]})
             CREATE (a)-[:CALLS]->(b)""", {"rows": CALLS})

    # Endpoint -[:EXECUTES]-> Function
    g.run("""UNWIND $rows AS r
             MATCH (e:Endpoint {route: r.route}), (fn:Function {name: r.fn})
             CREATE (e)-[:EXECUTES]->(fn)""", {"rows": ENDPOINTS})

    # Developer -[:AUTHORED]-> File
    g.run("""UNWIND $rows AS r
             MATCH (d:Developer {name: r.name}), (f:File {path: r.file})
             CREATE (d)-[:AUTHORED {commits: r.commits, last_touched: r.last_touched}]->(f)""",
          {"rows": DEVELOPERS})

    # TeamRule -[:GOVERNS]-> Function | File
    g.run("""UNWIND $rows AS r
             MATCH (rule:TeamRule {id: r.id}), (fn:Function {name: r.governs_fn})
             CREATE (rule)-[:GOVERNS]->(fn)""",
          {"rows": [r for r in TEAM_RULES if r.get("governs_fn")]})
    g.run("""UNWIND $rows AS r
             MATCH (rule:TeamRule {id: r.id}), (f:File {path: r.governs_file})
             CREATE (rule)-[:GOVERNS]->(f)""",
          {"rows": [r for r in TEAM_RULES if r.get("governs_file")]})

    # ADR -[:APPLIES_TO]-> File
    g.run("""UNWIND $rows AS r
             MATCH (adr:ADR {id: r.id}), (f:File {path: r.file})
             CREATE (adr)-[:APPLIES_TO]->(f)""", {"rows": ADRS})

    client.register_project(DEFAULT_GRAPH, "Sample microservices (demo)", "bundled sample_repo", kind="sample")
    counts = g.run("MATCH (n) RETURN count(n)").result_set[0][0]
    rels = g.run("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    return {"nodes": counts, "relationships": rels}
