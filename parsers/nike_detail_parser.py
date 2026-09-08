"""Parse a saved Nike.com product-detail page (PDP) HTML dump.

Unlike the listing page, Nike's PDP embeds a full `__NEXT_DATA__` JSON blob
with per-size stock status and every other colorway's price/availability --
the on-page `#size-selector` div itself is an empty placeholder hydrated
client-side, so this parser reads the JSON payload rather than the DOM.

Usage:
    from parsers.nike_detail_parser import parse_product_detail

    with open("nike-pdp.html", encoding="utf-8") as f:
        product = parse_product_detail(f.read())

    for size in product.sizes:
        print(size.label, size.available)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup

_NEXT_DATA_ID = "__NEXT_DATA__"


@dataclass
class SizeOption:
    label: str | None
    localized_label: str | None
    status: str | None
    available: bool
    merch_sku_id: str | None


@dataclass
class ColorwayOption:
    style_color: str | None
    color_description: str | None
    price: float | None
    url: str | None
    image_url: str | None
    in_stock: bool


@dataclass
class ProductDetail:
    style_code: str | None
    style_color: str | None
    name: str
    subtitle: str | None
    color_description: str | None
    url: str | None
    image_url: str | None
    current_price: float | None
    original_price: float | None
    discount_percent: float | None
    sizes: list[SizeOption] = field(default_factory=list)
    colorways: list[ColorwayOption] = field(default_factory=list)


def _load_next_data(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", id=_NEXT_DATA_ID)
    if script is None or not script.string:
        return {}
    return json.loads(script.string)


def _extract_sizes(selected_product: dict) -> list[SizeOption]:
    sizes = []
    for s in selected_product.get("sizes", []):
        status = s.get("status")
        sizes.append(
            SizeOption(
                label=s.get("label"),
                localized_label=s.get("localizedLabel"),
                status=status,
                available=status == "ACTIVE",
                merch_sku_id=s.get("merchSkuId"),
            )
        )
    return sizes


def _extract_colorways(page_props: dict) -> list[ColorwayOption]:
    colorways = []
    for c in page_props.get("colorwayImages", []) or []:
        colorways.append(
            ColorwayOption(
                style_color=c.get("styleColor"),
                color_description=c.get("colorDescription"),
                price=None,
                url=c.get("pdpUrl"),
                image_url=c.get("squarishImg"),
                in_stock=c.get("statusModifier") not in ("BUYABLE_NOTIFY_ME", "UNBUYABLE"),
            )
        )

    # backfill price per colorway from productGroups, matched by styleColor
    products_by_style: dict[str, dict] = {}
    for group in page_props.get("productGroups", []) or []:
        products_by_style.update(group.get("products", {}))

    for colorway in colorways:
        prod = products_by_style.get(colorway.style_color)
        if prod:
            colorway.price = prod.get("prices", {}).get("currentPrice")

    return colorways


def parse_product_detail(html: str) -> ProductDetail | None:
    """Parse a single Nike.com product-detail page dump."""
    data = _load_next_data(html)
    page_props = data.get("props", {}).get("pageProps", {})
    sp = page_props.get("selectedProduct")
    if sp is None:
        return None

    prices = sp.get("prices", {})
    info = sp.get("productInfo", {})
    pdp_url = sp.get("pdpUrl", {}) or {}

    image_url = None
    for c in page_props.get("colorwayImages", []) or []:
        if c.get("styleColor") == sp.get("styleColor"):
            image_url = c.get("squarishImg")
            break

    return ProductDetail(
        style_code=sp.get("styleCode"),
        style_color=sp.get("styleColor"),
        name=info.get("title") or "",
        subtitle=info.get("subtitle"),
        color_description=sp.get("colorDescription"),
        url=pdp_url.get("url") or info.get("url"),
        image_url=image_url,
        current_price=prices.get("currentPrice"),
        original_price=prices.get("initialPrice"),
        discount_percent=prices.get("discountPercentage"),
        sizes=_extract_sizes(sp),
        colorways=_extract_colorways(page_props),
    )


if __name__ == "__main__":
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "nike-pdp.html"
    with open(path, encoding="utf-8") as fh:
        page_html = fh.read()

    parsed = parse_product_detail(page_html)
    if parsed is None:
        print("No product found", file=sys.stderr)
    else:
        print(json.dumps(asdict(parsed), indent=2))
