"""Parse product tiles out of a saved Urban Outfitters (PWA) category-page HTML dump.

Usage:
    from urbanoutfitters_parser import parse_products

    with open("markup.html", encoding="utf-8") as f:
        products = parse_products(f.read())

    for p in products:
        print(p.name, p.current_price, p.url)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from bs4.element import Tag

from .normalize import NormalizedProduct, compute_discount_percent, require_field

BASE_URL = "https://www.urbanoutfitters.com/shop/"

_PRICE_RE = re.compile(r"[\d,]+\.\d{2}")
_ID_COLOR_RE = re.compile(r"/([0-9]{5,})_([A-Za-z0-9]+)_")


@dataclass
class ColorSwatch:
    label: str | None
    color_code: str | None
    image_url: str | None


def _clean_text(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    return text or None


def _parse_price(tag: Tag | None) -> float | None:
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    match = _PRICE_RE.search(text)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def _extract_colors(tile: Tag) -> list[ColorSwatch]:
    colors: list[ColorSwatch] = []
    for label in tile.select("label.c-pwa-custom-radio__label"):
        img = label.find("img", attrs={"data-qa-swatch": True})
        if img is None:
            continue
        colors.append(
            ColorSwatch(
                label=img.get("alt"),
                color_code=_extract_color_code(img.get("src")),
                image_url=img.get("src"),
            )
        )
    return colors


def _extract_color_code(url: str | None) -> str | None:
    if not url:
        return None
    match = _ID_COLOR_RE.search(url)
    return match.group(2) if match else None


_IMAGE_QUERY = "$medium$&fit=constrain&fmt=webp&hei=1046&qlt=80&wid=698"


def _build_image_url(raw_src: str | None) -> str | None:
    """Rebuild the scraped image src into a full-size webp URL, e.g.
    https://images.urbndata.com/is/image/UrbanOutfitters/105629968_031_b?$medium$&fit=constrain&fmt=webp&hei=1046&qlt=80&wid=698
    """
    if not raw_src:
        return None
    base_path = raw_src.split("?", 1)[0]
    return f"{base_path}?{_IMAGE_QUERY}"


def _extract_image_url(tile: Tag) -> str | None:
    img = tile.select_one("img.o-pwa-product-tile__media")
    if img is None:
        return None
    return _build_image_url(img.get("src"))


def parse_products(html: str) -> list[NormalizedProduct]:
    """Parse every product tile out of a category/search-results page dump."""
    soup = BeautifulSoup(html, "lxml")
    products: list[NormalizedProduct] = []
    scraped_at = datetime.now(timezone.utc)

    for wrapper in soup.select("div.c-pwa-tile-grid-tile"):
        tile = wrapper.select_one(".o-pwa-product-tile")
        if tile is None:
            continue

        link = tile.select_one("a.o-pwa-product-tile__link")
        heading = tile.select_one("h2.o-pwa-product-tile__heading")
        current_price_tag = tile.select_one(".c-pwa-product-price__current")
        original_price_tag = tile.select_one(".c-pwa-product-price__original")
        promo_tag = tile.select_one(".c-pwa-product-promos")

        href = link.get("href") if link else None
        url = urljoin(BASE_URL, href) if href else None
        image_url = _extract_image_url(tile)
        name = _clean_text(heading) or ""
        current_price = _parse_price(current_price_tag)
        original_price = _parse_price(original_price_tag)

        try:
            products.append(
                NormalizedProduct(
                    source="urban_outfitters",
                    name=name,
                    url=require_field(url, "url", "urban_outfitters", name),
                    scraped_at=scraped_at,
                    # None is legitimate here -- see NormalizedProduct.image_url docstring
                    image_url=image_url,
                    current_price=require_field(
                        current_price, "current_price", "urban_outfitters", name
                    ),
                    original_price=original_price,
                    discount_percent=compute_discount_percent(current_price, original_price),
                    rating=None,
                    badges=[promo] if (promo := _clean_text(promo_tag)) else [],
                    colors=[c.label for c in _extract_colors(wrapper) if c.label],
                )
            )
        except ValueError as e:
            print(f"skipping incomplete product: {e}")

    return products


if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "markup.html"
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    parsed = parse_products(html)
    print(f"Found {len(parsed)} products", file=sys.stderr)
    print(json.dumps([asdict(p) for p in parsed], indent=2, default=str))
