import os


def tax_rate():
    return float(os.environ.get("SHOP_TAX_RATE", "0.2"))


def currency():
    return os.environ.get("SHOP_CURRENCY", "EUR")
