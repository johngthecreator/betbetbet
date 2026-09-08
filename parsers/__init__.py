"""Product parsers for saved retailer HTML dumps.

Two kinds of parser per retailer:

- Listing/category page (PLP) parsers -- `parse_products(html) -> list[NormalizedProduct]`.
  Each site's parser normalizes directly into the common `NormalizedProduct`
  shape (source, name, url, image_url, current_price, original_price,
  discount_percent, rating, badges, colors) -- see `normalize.py` for the
  full field docs and nullability notes.
- Product-detail page (PDP) parsers -- `parse_product_detail(html) -> ProductDetail | None`,
  which carry per-size stock/availability info the listing pages don't expose.
  These remain site-specific (not normalized) since size/stock shapes differ
  too much across retailers to usefully collapse into one schema.

Import either the submodule directly:

    from parsers import nike_parser, nike_detail_parser
    products = nike_parser.parse_products(listing_html)      # list[NormalizedProduct]
    detail = nike_detail_parser.parse_product_detail(pdp_html)

or the re-exported names below, disambiguated by retailer prefix:

    from parsers import parse_nike_products, parse_nike_product_detail

Note on size/stock data per retailer's PDP parser:
- Nike: full per-size stock status, read from embedded `__NEXT_DATA__` JSON.
- Gymshark: full per-size stock + inventory quantity, read from embedded
  `__NEXT_DATA__` JSON.
- Urban Outfitters: full per-size availability, read directly from the
  rendered DOM (`data-qa-is-available` on each size radio).
- Patagonia: NOT available. Patagonia's PDP hydrates size buttons
  client-side with no embedded JSON fallback, so `sizes` is always `[]` --
  see `patagonia_detail_parser`'s module docstring for details.
"""

from . import (
    gymshark_detail_parser,
    gymshark_parser,
    nike_detail_parser,
    nike_parser,
    normalize,
    patagonia_detail_parser,
    patagonia_parser,
    urbanoutfitters_detail_parser,
    urbanoutfitters_parser,
)
from .gymshark_detail_parser import ProductDetail as GymsharkProductDetail
from .gymshark_detail_parser import SizeOption as GymsharkSizeOption
from .gymshark_detail_parser import parse_product_detail as parse_gymshark_product_detail
from .gymshark_parser import parse_products as parse_gymshark_products
from .nike_detail_parser import ColorwayOption as NikeColorwayOption
from .nike_detail_parser import ProductDetail as NikeProductDetail
from .nike_detail_parser import SizeOption as NikeSizeOption
from .nike_detail_parser import parse_product_detail as parse_nike_product_detail
from .nike_parser import Colorway as NikeColorway
from .nike_parser import parse_products as parse_nike_products
from .normalize import NormalizedProduct
from .patagonia_detail_parser import ColorwayOption as PatagoniaColorwayOption
from .patagonia_detail_parser import ProductDetail as PatagoniaProductDetail
from .patagonia_detail_parser import parse_product_detail as parse_patagonia_product_detail
from .patagonia_parser import ColorOption as PatagoniaColorOption
from .patagonia_parser import parse_products as parse_patagonia_products
from .urbanoutfitters_detail_parser import ColorSwatch as UrbanOutfittersDetailColorSwatch
from .urbanoutfitters_detail_parser import FitOption as UrbanOutfittersFitOption
from .urbanoutfitters_detail_parser import ProductDetail as UrbanOutfittersProductDetail
from .urbanoutfitters_detail_parser import SizeOption as UrbanOutfittersSizeOption
from .urbanoutfitters_detail_parser import (
    parse_product_detail as parse_urbanoutfitters_product_detail,
)
from .urbanoutfitters_parser import ColorSwatch as UrbanOutfittersColorSwatch
from .urbanoutfitters_parser import parse_products as parse_urbanoutfitters_products

__all__ = [
    "gymshark_parser",
    "gymshark_detail_parser",
    "nike_parser",
    "nike_detail_parser",
    "normalize",
    "patagonia_parser",
    "patagonia_detail_parser",
    "urbanoutfitters_parser",
    "urbanoutfitters_detail_parser",
    # normalized (cross-retailer common shape, returned by every parse_*_products)
    "NormalizedProduct",
    # listing (PLP)
    "parse_gymshark_products",
    "NikeColorway",
    "parse_nike_products",
    "PatagoniaColorOption",
    "parse_patagonia_products",
    "UrbanOutfittersColorSwatch",
    "parse_urbanoutfitters_products",
    # detail (PDP)
    "GymsharkProductDetail",
    "GymsharkSizeOption",
    "parse_gymshark_product_detail",
    "NikeColorwayOption",
    "NikeProductDetail",
    "NikeSizeOption",
    "parse_nike_product_detail",
    "PatagoniaColorwayOption",
    "PatagoniaProductDetail",
    "parse_patagonia_product_detail",
    "UrbanOutfittersDetailColorSwatch",
    "UrbanOutfittersFitOption",
    "UrbanOutfittersProductDetail",
    "UrbanOutfittersSizeOption",
    "parse_urbanoutfitters_product_detail",
]
