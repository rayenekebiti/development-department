from .config import tax_rate


def apply_discount(amount_cents, percent):
    return amount_cents - amount_cents * percent // 100


def total_with_tax(amount_cents):
    return round(amount_cents * (1 + tax_rate()))
