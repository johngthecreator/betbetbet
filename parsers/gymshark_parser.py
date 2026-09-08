"""Parse product cards out of a saved Gymshark.com product-grid (PLP) HTML dump.

Note: this listing page does NOT expose sizes or size-level stock. It only
has a "fit" field (e.g. "slim fit", "regular fit"), which is garment cut,
not a size like S/M/L. Verified against both the rendered DOM and the
embedded __NEXT_DATA__ JSON blob.

Usage:
    from gymshark_parser import parse_products

    with open("gymshark.html", encoding="utf-8") as f:
        products = parse_products(f.read())

    for p in products:
        print(p.name, p.current_price, p.url)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from bs4.element import Tag

from .normalize import NormalizedProduct, compute_discount_percent, require_field

_PRICE_RE = re.compile(r"[\d,]+\.?\d*")


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


def _parse_rating(tag: Tag | None) -> float | None:
    if tag is None:
        return None
    text = tag.get_text(" ", strip=True)
    match = re.search(r"\d+(\.\d+)?", text)
    return float(match.group(0)) if match else None


_SRCSET_ENTRY_RE = re.compile(r"(\S+)\s+(\d+)w")


def _extract_image_url(card: Tag) -> str | None:
    img = card.select_one("img")
    if img is None:
        return None
    # prefer the largest entry in srcSet; fall back to src
    srcset = img.get("srcset") or img.get("srcSet")
    if srcset:
        candidates = _SRCSET_ENTRY_RE.findall(srcset)
        if candidates:
            return max(candidates, key=lambda c: int(c[1]))[0]
    return img.get("src")


def parse_products(html: str) -> list[NormalizedProduct]:
    """Parse every product card out of a Gymshark.com product-grid page dump."""
    soup = BeautifulSoup(html, "lxml")
    products: list[NormalizedProduct] = []
    scraped_at = datetime.now(timezone.utc)

    for card in soup.select("article.product-card_product-card__1T7k9"):
        title = card.select_one('[class*="product-card_product-title__"]')
        link = card.select_one('a[class*="product-card_product-title-link__"]')
        colour = card.select_one('[class*="product-card_product-colour__"]')
        rating = card.select_one('[class*="product-card_rating__"]')

        current_price_tag = card.select_one('[class*="product-price_product-price__"]')
        original_price_tag = card.select_one('[class*="product-price_compare-at-price__"]')

        url = link.get("href") if link else None
        name = _clean_text(title) or _clean_text(link) or ""
        current_price = _parse_price(current_price_tag)
        original_price = _parse_price(original_price_tag)
        colour_text = _clean_text(colour)

        try:
            products.append(
                NormalizedProduct(
                    source="gymshark",
                    name=name,
                    url=require_field(url, "url", "gymshark", name),
                    scraped_at=scraped_at,
                    image_url=require_field(
                        _extract_image_url(card), "image_url", "gymshark", name
                    ),
                    current_price=require_field(
                        current_price, "current_price", "gymshark", name
                    ),
                    original_price=original_price,
                    discount_percent=compute_discount_percent(current_price, original_price),
                    rating=_parse_rating(rating),
                    badges=[],
                    colors=[colour_text] if colour_text else [],
                )
            )
        except ValueError as e:
            print(f"skipping incomplete product: {e}")

    return products


if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "gymshark.html"
    with open(path, encoding="utf-8") as fh:
        html = fh.read()

    parsed = parse_products(html)
    print(f"Found {len(parsed)} products", file=sys.stderr)
    print(json.dumps([asdict(p) for p in parsed], indent=2, default=str))
