"""Parse product tiles out of a saved Patagonia.com category-page HTML dump.

Note on sizes: the tile markup includes a `<div class="product-tile__quickadd-sizes">`
placeholder per product, but it is always empty in a static page dump -- Patagonia
loads the actual size buttons asynchronously (via a
`?id=productQuickAddSizes&pid=...` endpoint) after the page renders. Sizes
aren't part of `NormalizedProduct` at all for this reason; if you need real
sizes you'd have to hit that endpoint per product_id/color separately.

Usage:
    from patagonia_parser import parse_products

    with open("patagonia.html", encoding="utf-8") as f:
        products = parse_products(f.read())

    for p in products:
        print(p.name, p.current_price, p.url)
"""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from .normalize import NormalizedProduct, compute_discount_percent, require_field

BASE_URL = "https://www.patagonia.com"

_WIDTH_RE = re.compile(r"width:\s*([\d.]+)%")


@dataclass
class ColorOption:
    code: str | None
    hex_color: str | None
    label: str | None
    sale_price: float | None
    list_price: float | None


def _clean_text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    return text or None


def _to_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _parse_gtm(tile: Tag) -> dict:
    raw = tile.get("data-gtm")
    if not raw:
        return {}
    try:
        payload = json.loads(html_lib.unescape(raw))
    except (json.JSONDecodeError, TypeError):
        return {}
    try:
        return payload[0]["ecommerce"]["items"][0]
    except (KeyError, IndexError, TypeError):
        return {}


def _extract_rating(container: Tag) -> float | None:
    rating_block = container.select_one(".product-tile__rating")
    if rating_block is None:
        return None
    filled = rating_block.select_one(".product-tile__rating__stars--filled")
    if filled is None:
        return None
    widths = _WIDTH_RE.findall(str(filled))
    if not widths:
        return None
    return round(sum(float(w) for w in widths) / 100, 2)


def _extract_colors(container: Tag) -> list[ColorOption]:
    colors: list[ColorOption] = []
    for btn in container.select("button.product-tile__colors"):
        colors.append(
            ColorOption(
                code=btn.get("data-color"),
                hex_color=btn.get("data-hex-color"),
                label=btn.get("title"),
                sale_price=_to_float(btn.get("data-sale-price")),
                list_price=_to_float(btn.get("data-list-price")),
            )
        )
    return colors


def _extract_badges(container: Tag) -> list[str]:
    return [text for badge in container.select(".badge") if (text := _clean_text(badge))]


_IMAGE_QUERY = "sw=1920&sh=1920&sfrm=png&q=90&bgcolor=f3f4ef"


def _build_image_url(raw_src: str | None) -> str | None:
    """Rebuild the scraped image src into the largest available size, e.g.
    https://www.patagonia.com/dw/image/.../27611_BLK.jpg?sw=1920&sh=1920&sfrm=png&q=90&bgcolor=f3f4ef
    (1920px is the largest variant Patagonia serves in this page's srcset.)
    """
    if not raw_src:
        return None
    base_path = raw_src.split("?", 1)[0]
    return f"{base_path}?{_IMAGE_QUERY}"


def _extract_image_url(container: Tag) -> str | None:
    meta = container.select_one('meta[itemprop="image"]')
    raw_src = meta["content"] if meta is not None and meta.get("content") else None
    if raw_src is None:
        img = container.select_one("product-tile-image")
        raw_src = img.get("base") if img else None
    return _build_image_url(raw_src)


def parse_products(html: str) -> list[NormalizedProduct]:
    """Parse every product tile out of a Patagonia.com category page dump."""
    soup = BeautifulSoup(html, "lxml")
    products: list[NormalizedProduct] = []
    scraped_at = datetime.now(timezone.utc)

    for tile in soup.select("product-tile"):
        container = tile.find_parent("div", class_="product") or tile

        gtm = _parse_gtm(tile)
        name_tag = container.select_one(".product-tile__name")
        # prefer the image-wrap link: it carries the selected color variant
        # (?dwvar_<pid>_color=<code>), matching the real PDP URL shape
        link = container.select_one('a[itemprop="url"]') or container.select_one(
            ".product-tile__content a.link"
        )
        pricing = container.select_one("product-tile-pricing")

        current_price = _to_float(pricing.get("sale-price")) if pricing else gtm.get("price")
        original_price = _to_float(pricing.get("list-price")) if pricing else None
        href = link.get("href") if link else None
        url = urljoin(BASE_URL, href) if href else None
        name = _clean_text(name_tag) or gtm.get("item_name") or ""
        # Patagonia's own data-discount-percent attribute is authoritative;
        # only fall back to computing it if that wasn't present.
        discount_percent = _to_float(tile.get("data-discount-percent")) or compute_discount_percent(
            current_price, original_price
        )

        try:
            products.append(
                NormalizedProduct(
                    source="patagonia",
                    name=name,
                    url=require_field(url, "url", "patagonia", name),
                    scraped_at=scraped_at,
                    image_url=require_field(
                        _extract_image_url(container), "image_url", "patagonia", name
                    ),
                    current_price=require_field(
                        current_price, "current_price", "patagonia", name
                    ),
                    original_price=original_price,
                    discount_percent=discount_percent,
                    rating=_extract_rating(container),
                    badges=_extract_badges(container),
                    colors=[c.label for c in _extract_colors(container) if c.label],
                )
            )
        except ValueError as e:
            print(f"skipping incomplete product: {e}")

    return products


if __name__ == "__main__":
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "patagonia.html"
    with open(path, encoding="utf-8") as fh:
        page_html = fh.read()

    parsed = parse_products(page_html)
    print(f"Found {len(parsed)} products", file=sys.stderr)
    print(json.dumps([asdict(p) for p in parsed], indent=2, default=str))
