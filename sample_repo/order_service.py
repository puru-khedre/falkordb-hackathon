"""Order service: checkout and order placement (top of the call tree)."""
from billing_service import create_invoice, calculate_discount
from database import fetch_user
from auth_service import validate_token


def checkout(cart, token):
    """Checkout flow: validates token, loads user, builds invoice."""
    validate_token(token)
    user = fetch_user(cart["user_id"])
    preview = calculate_discount(user, cart["amount"])
    invoice = create_invoice({"user": user, "amount": cart["amount"]})
    return {"preview_discount": preview, "invoice": invoice}


def place_order(cart, token):
    """Public entrypoint hit by the /checkout API endpoint."""
    return checkout(cart, token)
