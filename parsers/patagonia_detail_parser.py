"""Parse a saved Patagonia.com product-detail page (PDP) HTML dump.

Note on sizes: unlike Nike/Gymshark/UO, Patagonia's PDP does NOT expose
per-size stock anywhere in the static HTML. The size buttons
(`button.pdp-size-select`) are skeleton placeholders with no text/value,
hydrated client-side after page load via an async call -- same async
pattern as the listing page's quickadd-sizes. There's also no embedded
JSON (no `__NEXT_DATA__`-equivalent) carrying per-size availability; the
one `<script id="product-schema">` ld+json block only carries color-level
`offers.availability` (in stock / out of stock for the whole color, not
broken out by size). `sizes` is kept on the dataclass and always comes
back `[]` for that reason; getting real per-size stock would require
hitting Patagonia's variation/availability endpoint separately.

Usage:
    from parsers.patagonia_detail_parser import parse_product_detail

    with open("patagonia-pdp.html", encoding="utf-8") as f:
        product = parse_product_detail(f.read())

    print(product.name, product.in_stock)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from bs4 import BeautifulSoup


@dataclass
class ColorwayOption:
    color_code: str | None
    color_name: str | None
    name: str | None
    price: float | None
    url: str | None
    image_url: str | None
    in_stock: bool


@dataclass
class ProductDetail:
    product_id: str | None
    name: str
    url: str | None
    image_url: str | None
    color_code: str | None
    current_price: float | None
    brand: str | None
    rating: float | None
    review_count: int | None
    in_stock: bool
    colorways: list[ColorwayOption] = field(default_factory=list)
    sizes: list = field(default_factory=list)  # always empty, see module docstring


def _load_product_schema(soup: BeautifulSoup) -> list[dict]:
    script = soup.find("script", id="product-schema")
    if script is None or not script.string:
        return []
    try:
        data = json.loads(script.string)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


def parse_product_detail(html: str) -> ProductDetail | None:
    """Parse a single Patagonia.com product-detail page dump."""
    soup = BeautifulSoup(html, "lxml")
    schema_items = _load_product_schema(soup)

    group = next((i for i in schema_items if i.get("@type") == "ProductGroup"), None)
    variants = [i for i in schema_items if i.get("@type") == "Product"]
    if group is None or not variants:
        return None

    pid_tag = soup.select_one("[data-pid]")
    product_id = pid_tag.get("data-pid") if pid_tag else group.get("productGroupID")

    rating = None
    review_count = None
    agg = group.get("aggregateRating")
    if agg:
        rating = agg.get("ratingValue")
        review_count = agg.get("reviewCount")

    colorways = []
    for v in variants:
        offer = v.get("offers", {})
        colorways.append(
            ColorwayOption(
                color_code=(v.get("sku") or "").split("-")[-1] or None,
                color_name=v.get("color"),
                name=v.get("name"),
                price=offer.get("price"),
                url=offer.get("url"),
                image_url=v.get("image"),
                in_stock="InStock" in (offer.get("availability") or ""),
            )
        )

    # the selected/primary variant -- matches the color in the page URL
    primary = variants[0]
    primary_offer = primary.get("offers", {})

    return ProductDetail(
        product_id=product_id,
        name=primary.get("name") or group.get("name") or "",
        url=primary_offer.get("url") or group.get("url"),
        image_url=primary.get("image") or group.get("image"),
        color_code=colorways[0].color_code if colorways else None,
        current_price=primary_offer.get("price"),
        brand=(group.get("brand") or {}).get("name"),
        rating=rating,
        review_count=review_count,
        in_stock="InStock" in (primary_offer.get("availability") or ""),
        colorways=colorways,
        sizes=[],
    )


if __name__ == "__main__":
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "patagonia-pdp.html"
    with open(path, encoding="utf-8") as fh:
        page_html = fh.read()

    parsed = parse_product_detail(page_html)
    if parsed is None:
        print("No product found", file=sys.stderr)
    else:
        print(json.dumps(asdict(parsed), indent=2))
