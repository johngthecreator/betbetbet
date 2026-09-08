"""Parse a saved Urban Outfitters (PWA) product-detail page (PDP) HTML dump.

Unlike the listing page, UO's PDP renders size/fit availability directly in
the DOM (`data-qa-is-available="true"/"false"` on each size radio input),
so this parser reads the rendered form fields rather than any embedded JSON.

Usage:
    from parsers.urbanoutfitters_detail_parser import parse_product_detail

    with open("uo-pdp.html", encoding="utf-8") as f:
        product = parse_product_detail(f.read())

    for size in product.sizes:
        print(size.label, size.available)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup
from bs4.element import Tag

_PRICE_RE = re.compile(r"[\d,]+\.\d{2}")
_ID_COLOR_RE = re.compile(r"/([0-9]{5,})_([A-Za-z0-9]+)")
_IMAGE_QUERY = "$medium$&fit=constrain&fmt=webp&hei=1046&qlt=80&wid=698"


@dataclass
class SizeOption:
    label: str
    value: str | None
    available: bool


@dataclass
class FitOption:
    label: str
    value: str | None
    available: bool


@dataclass
class ColorSwatch:
    label: str | None
    color_code: str | None
    available: bool


@dataclass
class ProductDetail:
    product_id: str | None
    name: str
    url: str | None
    image_url: str | None
    current_price: float | None
    original_price: float | None
    promo_text: str | None
    selected_color: str | None
    sizes: list[SizeOption] = field(default_factory=list)
    fits: list[FitOption] = field(default_factory=list)
    colors: list[ColorSwatch] = field(default_factory=list)


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
    return float(match.group(0).replace(",", "")) if match else None


def _build_image_url(raw_src: str | None) -> str | None:
    if not raw_src:
        return None
    base_path = raw_src.split("?", 1)[0]
    return f"{base_path}?{_IMAGE_QUERY}"


def _extract_options(soup: BeautifulSoup, fieldset_selector: str, input_name: str) -> list[tuple]:
    fieldset = soup.select_one(fieldset_selector)
    if fieldset is None:
        return []
    options = []
    for li in fieldset.select("li"):
        radio = li.select_one(f'input[name="{input_name}"]')
        label = li.select_one("label")
        if radio is None or label is None:
            continue
        available = radio.get("data-qa-is-available") == "true"
        # drop the screen-reader-only "Out of Stock" span before extracting text,
        # since get_text() would otherwise fold it into the visible label
        label_copy = BeautifulSoup(str(label), "lxml")
        for sr_only in label_copy.select(".u-pwa-screen-reader-only"):
            sr_only.decompose()
        label_text = label_copy.get_text(" ", strip=True)
        options.append((label_text, radio.get("value"), available))
    return options


def parse_product_detail(html: str) -> ProductDetail | None:
    """Parse a single Urban Outfitters product-detail page dump."""
    soup = BeautifulSoup(html, "lxml")

    title_meta = soup.select_one('meta[property="og:title"]')
    url_meta = soup.select_one('meta[property="og:url"]')
    image_meta = soup.select_one('meta[property="og:image"]')

    if title_meta is None:
        return None

    price_block = soup.select_one(".c-pwa-product-price")
    current_price_tag = (
        price_block.select_one(".c-pwa-product-price__current") if price_block else None
    )
    original_price_tag = (
        price_block.select_one(".c-pwa-product-price__original") if price_block else None
    )
    promo_tag = price_block.select_one(".c-pwa-product-promos") if price_block else None

    color_value = soup.select_one(".c-pwa-sku-selection__color-value")

    product_id = None
    color_code = None
    raw_image = image_meta.get("content") if image_meta else None
    id_match = _ID_COLOR_RE.search(raw_image or "")
    if id_match:
        product_id, color_code = id_match.group(1), id_match.group(2)

    sizes = [
        SizeOption(label=label, value=value, available=available)
        for label, value, available in _extract_options(
            soup, "fieldset[data-qa-size]", "selectedSize"
        )
    ]
    fits = [
        FitOption(label=label, value=value, available=available)
        for label, value, available in _extract_options(
            soup, "fieldset.c-pwa-sku-selection__fits-outer", "selectedFit"
        )
    ]

    colors = []
    color_fieldset = soup.select_one("fieldset[data-qa-color]")
    if color_fieldset is not None:
        for label_tag in color_fieldset.select("label.c-pwa-custom-radio__label"):
            img = label_tag.select_one("img[data-qa-swatch]")
            if img is None:
                continue
            colors.append(
                ColorSwatch(
                    label=img.get("alt"),
                    color_code=None,
                    available=img.get("isoutofstock") != "true",
                )
            )

    return ProductDetail(
        product_id=product_id,
        name=title_meta["content"],
        url=url_meta["content"] if url_meta else None,
        image_url=_build_image_url(raw_image),
        current_price=_parse_price(current_price_tag),
        original_price=_parse_price(original_price_tag),
        promo_text=_clean_text(promo_tag),
        selected_color=_clean_text(color_value),
        sizes=sizes,
        fits=fits,
        colors=colors,
    )


if __name__ == "__main__":
    import json
    import sys
    from dataclasses import asdict

    path = sys.argv[1] if len(sys.argv) > 1 else "uo-pdp.html"
    with open(path, encoding="utf-8") as fh:
        page_html = fh.read()

    parsed = parse_product_detail(page_html)
    if parsed is None:
        print("No product found", file=sys.stderr)
    else:
        print(json.dumps(asdict(parsed), indent=2))
