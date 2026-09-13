"""Parse product tiles out of a saved ALLSAINTS (SFCC) category-page HTML dump.

Usage:
    from allsaints_parser import parse_products

    with open("allsaints-men.html", encoding="utf-8") as f:
        products = parse_products(f.read())

    for p in products:
        print(p.name, p.current_price, p.url)

ALLSAINTS' PLP markup is unusual in two ways that shape this parser:

- Product images never appear as a rendered `<img src>` -- the tile ships a
  Mustache template (`<script type="template/mustache">`) that's hydrated
  client-side, and the *only* real image URL in the static HTML lives in a
  `data-src` JSON blob (`{"url": "...", "absURL": "...", ...}`) on the
  `[data-id="tileImage"]` div. So `image_url` is read out of that JSON
  rather than off an `<img>` tag.
- Every tile carries a rich `data-analytics` JSON attribute (on both the
  image link and the title link) with authoritative price/sale/color data
  -- `price`, `original_price`, `is_on_sale`, `variant` (the tile's single
  displayed color). That's used in preference to scraping the visually
  rendered price spans, which are split across several conditionally
  rendered `<span>`s and easy to get wrong.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from .normalize import NormalizedProduct, compute_discount_percent, require_field

BASE_URL = "https://www.allsaints.com"


@dataclass
class TileAnalytics:
    product_id: str | None
    name: str | None
    current_price: float | None
    original_price: float | None
    is_on_sale: bool | None
    color: str | None


def _clean_text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    return text or None


def _parse_analytics(tag: Tag | None) -> TileAnalytics:
    if tag is None:
        return TileAnalytics(None, None, None, None, None, None)
    raw = tag.get("data-analytics")
    if not raw:
        return TileAnalytics(None, None, None, None, None, None)
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return TileAnalytics(None, None, None, None, None, None)

    def _to_float(value) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    return TileAnalytics(
        product_id=data.get("id"),
        name=data.get("name"),
        current_price=_to_float(data.get("price")),
        original_price=_to_float(data.get("original_price")),
        is_on_sale=data.get("is_on_sale") == "Yes",
        color=data.get("variant") or None,
    )


def _extract_image_url(tile: Tag) -> str | None:
    image_div = tile.select_one('div.b-product_tile-image[data-id="tileImage"]')
    if image_div is None:
        return None
    raw = image_div.get("data-src")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data.get("url") or data.get("absURL")


def _extract_badges(tile: Tag) -> list[str]:
    badges = []
    for item in tile.select(".b-product_tile-meta_item"):
        text = _clean_text(item)
        if text and "colour" not in text.lower():
            badges.append(text)
    return badges


def parse_products(html: str) -> list[NormalizedProduct]:
    """Parse every product tile out of a category/sale-page dump."""
    soup = BeautifulSoup(html, "lxml")
    products: list[NormalizedProduct] = []
    scraped_at = datetime.now(timezone.utc)

    for tile in soup.select('section.b-product_tile[data-widget="productTile"]'):
        title_link = tile.select_one("a.b-product_tile-link")
        analytics = _parse_analytics(title_link)

        href = title_link.get("href") if title_link else None
        url = urljoin(BASE_URL, href) if href else None
        name = _clean_text(title_link) or analytics.name or tile.get("data-product-name") or ""
        image_url = _extract_image_url(tile)

        current_price = analytics.current_price
        original_price = analytics.original_price if analytics.is_on_sale else None

        try:
            products.append(
                NormalizedProduct(
                    source="allsaints",
                    name=name,
                    url=require_field(url, "url", "allsaints", name),
                    scraped_at=scraped_at,
                    image_url=require_field(image_url, "image_url", "allsaints", name),
                    current_price=require_field(
                        current_price, "current_price", "allsaints", name
                    ),
                    original_price=original_price,
                    discount_percent=compute_discount_percent(current_price, original_price),
                    rating=None,
                    badges=_extract_badges(tile),
                    colors=[analytics.color] if analytics.color else [],
                )
            )
        except ValueError as e:
            print(f"skipping incomplete product: {e}")

    return products


if __name__ == "__main__":
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "markup.html"
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    parsed = parse_products(html)
    print(f"Found {len(parsed)} products", file=sys.stderr)
    print(json.dumps([asdict(p) for p in parsed], indent=2, default=str))
