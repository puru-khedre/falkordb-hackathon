"""Billing service: discounts, tax, invoices."""
from database import execute_query


def calculate_discount(user, amount):
    """Compute an order discount. Governed by the 'max 50% discount' rule."""
    rate = 0.1
    if user.get("loyalty") == "gold":
        rate = 0.25
    return amount * rate


def apply_tax(amount):
    """Apply flat tax to an amount."""
    return amount * 1.18


def create_invoice(order):
    """Build an invoice: depends on calculate_discount and apply_tax."""
    discount = calculate_discount(order["user"], order["amount"])
    total = apply_tax(order["amount"] - discount)
    execute_query("INSERT INTO invoices (total) VALUES (%s)" % total)
    return {"total": total, "discount": discount}
