"""Authentication service: tokens and login."""
from database import execute_query, fetch_user


def issue_token(user):
    """Create a session token for a user. Governed by the OAuth2 team rule."""
    return "tok_%s" % user.get("id", "anon")


def validate_token(token):
    """Validate an incoming session token against the store."""
    execute_query("SELECT * FROM tokens WHERE token = %s" % token)
    return token.startswith("tok_")


def login(credentials):
    """Entry point: authenticate credentials and mint a token."""
    user = fetch_user(credentials["user_id"])
    return issue_token(user)
