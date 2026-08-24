from product_parser import parse_product

def parse_birmarket_product(url: str) -> dict:
    """Совместимый псевдоним старого API Birmarket-парсера."""
    return parse_product(url)
