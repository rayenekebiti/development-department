from .events import emit, on
from .pricing import apply_discount, total_with_tax


def create_order(cart, coupon_percent=0):
    subtotal = sum(item["price_cents"] * item["qty"] for item in cart)
    if coupon_percent:
        subtotal = apply_discount(subtotal, coupon_percent)
    order = {"total_cents": total_with_tax(subtotal), "status": "new"}
    emit("order.created", order)
    return order


@on("order.paid")
def mark_paid(order):
    order["status"] = "paid"


@on("order.paid")
def send_receipt(order):
    order["receipt_sent"] = True
