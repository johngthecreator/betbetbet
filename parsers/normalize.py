"""The common product shape every `<retailer>_parser.parse_products()` returns.

Each site's markup exposes different fields (`colors` vs `colorways`,
`badge` vs `badges`, `rating` present on some sites and not others), but
`parse_products()` now normalizes into this one shape directly rather than
returning a site-specific shape that needs a separate normalization pass.

`sizes` is intentionally not part of this shape -- it's inconsistent across
sites (real size/stock data only exists in the *detail* parsers, not these
listing parsers) so it's left out entirely.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NormalizedProduct:
    source: str  # "nike" | "gymshark" | "patagonia" | "urban_outfitters"
    name: str
    url: str
    scraped_at: datetime  # UTC; when this parse_products() call ran, not per-product
    # None is legitimate for Urban Outfitters specifically: its listing page
    # lazy-loads product images, so any tile below the initial viewport at
    # capture time has no <img> in the HTML at all (confirmed: 68/72 tiles
    # in a real saved page) -- nothing for the parser to recover. Nike,
    # Gymshark, and Patagonia don't have this gap (0 missing, verified).
    image_url: str | None
    current_price: float
    # None is legitimate here (not a parsing gap): a product simply may not
    # be on sale, so there's no struck-through "original" price to show --
    # confirmed against real markup where only 67/72 UO tiles even had an
    # original-price element.
    original_price: float | None
    discount_percent: float | None
    rating: float | None
    badges: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)


class IncompleteProductError(ValueError):
    """Raised when a source tile is missing a field every real listed
    product should have (url/current_price, or image_url on sites other
    than UO) -- signals an actual parsing bug rather than a legitimately
    absent value."""


def require_field(value, field_name: str, source: str, name: str):
    if value is None:
        raise IncompleteProductError(
            f"{source} product {name!r} is missing required field {field_name!r}"
        )
    return value


def compute_discount_percent(current: float | None, original: float | None) -> float | None:
    if current is None or original is None or original <= 0 or current >= original:
        return None
    return round((original - current) / original * 100, 1)
