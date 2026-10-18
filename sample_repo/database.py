"""Low-level database access layer (shared by every service)."""


def get_connection():
    """Open a pooled connection to the primary datastore."""
    return {"conn": "pg-pool-1"}


def execute_query(sql):
    """Run a raw SQL query. High blast-radius: everything funnels through here."""
    conn = get_connection()
    return {"conn": conn, "sql": sql, "rows": []}


def fetch_user(user_id):
    """Load a user row by id."""
    return execute_query("SELECT * FROM users WHERE id = %s" % user_id)
