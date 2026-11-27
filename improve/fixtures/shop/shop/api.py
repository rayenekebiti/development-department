from . import orders
from .pricing import apply_discount


def handle_create(request):
    return orders.create_order(request["cart"], request.get("coupon", 0))


def handle_quote(request):
    return {"quote_cents": apply_discount(request["amount_cents"], request.get("coupon", 0))}


ROUTES = {
    ("POST", "/orders"): handle_create,
    ("POST", "/quote"): handle_quote,
}


def dispatch(method, path, request):
    return ROUTES[(method, path)](request)
