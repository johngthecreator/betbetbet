"""Integration tests that hit the real Bright Data scraping API for each
retailer's live sale/outlet page and run the response through the matching
listing parser.

These are slow, external, and burn Bright Data credits, so they're skipped
entirely unless BRIGHTDATA_API_KEY is set. Requests are staggered
STAGGER_SECONDS apart (rather than fired concurrently) so a full run doesn't
trip rate limits on the shared "deal_unlocker" zone.

Run explicitly with:
    uv run pytest tests/test_parsers_integration.py -v -s
"""

from __future__ import annotations

import os
import time

import pytest

from parsers import (
    parse_allsaints_products,
    parse_gymshark_products,
    parse_nike_products,
    parse_patagonia_products,
    parse_urbanoutfitters_products,
)
from utils import brightdata_scraper

STAGGER_SECONDS = 15

pytestmark = pytest.mark.skipif(
    not os.getenv("BRIGHTDATA_API_KEY"),
    reason="requires BRIGHTDATA_API_KEY to hit the live Bright Data API",
)

SELLERS = [
    {
        "source": "urban_outfitters",
        "url": "https://www.urbanoutfitters.com/mens-clothing-sale",
        "parser": parse_urbanoutfitters_products,
    },
    {
        "source": "nike",
        "url": "https://www.nike.com/w/mens-sale-3yaepznik1",
        "parser": parse_nike_products,
    },
    {
        "source": "gymshark",
        "url": "https://www.gymshark.com/collections/last-chance/mens",
        "parser": parse_gymshark_products,
    },
    {
        "source": "patagonia",
        "url": "https://www.patagonia.com/shop/web-specials/mens",
        "parser": parse_patagonia_products,
    },
    {
        "source": "allsaints",
        "url": "https://www.allsaints.com/us/men/sale",
        "parser": parse_allsaints_products,
    },
]

# Shared across the whole parametrized run (module scope) so the pause lands
# *between* tests rather than once per test-plus-fixture-teardown ordering
# surprise.
_calls_made = 0


@pytest.fixture
def stagger():
    """Sleep before every call after the first, to spread requests out."""
    global _calls_made
    if _calls_made > 0:
        time.sleep(STAGGER_SECONDS)
    _calls_made += 1


@pytest.mark.parametrize("seller", SELLERS, ids=[s["source"] for s in SELLERS])
def test_parser_against_live_page(seller, stagger):
    response = brightdata_scraper(seller["url"])
    assert response.status_code == 200, (
        f"{seller['source']}: bright data returned {response.status_code} "
        f"for {seller['url']}"
    )

    products = seller["parser"](response.text)

    assert products, f"{seller['source']}: parser found 0 products on {seller['url']}"
    for p in products:
        assert p.name, f"{seller['source']}: product with empty name"
        assert p.url.startswith("http"), f"{seller['source']}: bad url {p.url!r}"
        assert p.current_price > 0, f"{seller['source']}: bad price on {p.name!r}"
