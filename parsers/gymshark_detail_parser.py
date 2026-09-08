"""Parse a saved Gymshark.com product-detail page (PDP) HTML dump.

Gymshark's PDP embeds a full `__NEXT_DATA__` JSON blob
(`props.pageProps.productData.product`) with per-size stock quantities --
much more reliable than the rendered size buttons, which only expose stock
state via a CSS modifier class (`size_size--out-of-stock__...`).

Usage:
    from parsers.gymshark_detail_parser import parse_product_detail

    with open("gymshark-pdp.html", encoding="utf-8") as f:
        product = parse_product_detail(f.read())

    for size in product.sizes:
        print(size.size, size.in_stock, size.inventory_quantity)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

_NEXT_DATA_ID = "__NEXT_DATA__"
BASE_URL = "https://www.gymshark.com"


@dataclass
class SizeOption:
    size: str
    sku: str | None
    in_stock: bool
    inventory_quantity: int | None
    price: float | None


@dataclass
class ProductDetail:
    product_id: int | str | None
    sku: str | None
    name: str
    colour: str | None
    fit: str | None
    url: str | None
    image_url: str | None
    current_price: float | None
    original_price: float | None
    discount_percent: float | None
    in_stock: bool
    rating: float | None
    sizes: list[SizeOption] = field(default_factory=list)
    sizes_in_stock: list[str] = field(default_factory=list)


def _load_next_data(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id=_NEXT_DATA_ID)
    if script is None or not script.string:
        return {}
    return json.loads(script.string)


def _extract_sizes(product: dict) -> list[SizeOption]:
    return [
        SizeOption(
            size=s.get("size"),
            sku=s.get("sku"),
            in_stock=bool(s.get("inStock")),
            inventory_quantity=s.get("inventoryQuantity"),
            price=s.get("price"),
        )
        for s in product.get("availableSizes", [])
    ]


def parse_product_detail(html: str) -> ProductDetail | None:
    """Parse a single Gymshark.com product-detail page dump."""
    data = _load_next_data(html)
    product_data = data.get("props", {}).get("pageProps", {}).get("productData")
    if not product_data:
        return None
    product = product_data.get("product")
    if not product:
        return None

    handle = product.get("handle")
    image_url = None
    featured = product.get("featuredMedia") or (product.get("media") or [{}])[0]
    if featured:
        image_url = featured.get("url") or featured.get("src")

    rating = None
    rating_data = product.get("rating")
    if isinstance(rating_data, dict):
        rating = rating_data.get("value") or rating_data.get("average")
    elif isinstance(rating_data, (int, float)):
        rating = rating_data

    return ProductDetail(
        product_id=product.get("id"),
        sku=product.get("sku"),
        name=product.get("title") or "",
        colour=product.get("colour"),
        fit=product.get("fit"),
        url=f"{BASE_URL}/products/{handle}" if handle else None,
        image_url=image_url,
        current_price=product.get("price"),
        original_price=product.get("compareAtPrice"),
        discount_percent=product.get("discountPercentage"),
        in_stock=bool(product.get("inStock")),
        rating=rating,
        sizes=_extract_sizes(product),
        sizes_in_stock=list(product.get("sizesInStock") or []),
    )


if __name__ == "__main__":
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "gymshark-pdp.html"
    with open(path, encoding="utf-8") as fh:
        page_html = fh.read()

    parsed = parse_product_detail(page_html)
    if parsed is None:
        print("No product found", file=sys.stderr)
    else:
        print(json.dumps(asdict(parsed), indent=2))
