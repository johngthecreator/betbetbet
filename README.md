# betbetbet

Scrapes retailer sale pages, parses discounted products, and posts them to Discord.

## Parsers

Each retailer has a listing (PLP) parser that normalizes into a common `NormalizedProduct`
shape (`parsers/normalize.py`), plus a detail (PDP) parser where per-size stock data is
needed. Live pages are fetched through Bright Data (see below) and handed to these:

| Retailer | Listing parser | Detail parser |
|---|---|---|
| Nike | `nike_parser` | `nike_detail_parser` |
| Gymshark | `gymshark_parser` | `gymshark_detail_parser` |
| Patagonia | `patagonia_parser` | `patagonia_detail_parser` |
| Urban Outfitters | `urbanoutfitters_parser` | `urbanoutfitters_detail_parser` |
| ALLSAINTS | `allsaints_parser` | — (not yet implemented) |

## Tech stack

- **Scraping**: [Bright Data](https://brightdata.com) Web Unlocker API (`utils.brightdata_scraper`)
- **Parsing**: BeautifulSoup + lxml
- **Data**: SQLModel / Postgres (Railway), scheduled with APScheduler (cron, `America/Denver`)
- **Agent**: LangGraph + LangChain, Google Gemini (`langchain-google-genai`)
- **Delivery**: Discord bot (`discord.py`)
- **Package/env management**: `uv`

## Running tests

The only test suite today is `tests/test_parsers_integration.py`, which hits the real
Bright Data API against each retailer's live sale page and runs the response through its
parser. It's slow, costs API credits, and is skipped automatically unless
`BRIGHTDATA_API_KEY` is set. Requests are staggered to avoid rate limits. Run explicitly:

```bash
uv run pytest tests/test_parsers_integration.py -v
```

Tests are parametrized by retailer, so you can rerun just one with `-k` (valid ids:
`urban_outfitters`, `nike`, `gymshark`, `patagonia`, `allsaints`):

```bash
uv run pytest tests/test_parsers_integration.py -k allsaints -v
```

## Known limitations

- **Duplicate replies**: the Discord bot sends the agent's whole response as one embed
  (`discord_bot.py`), so if the model repeats itself in a single generation, the user sees
  that duplicate inline in one message. Current mitigation is a prompt-level instruction
  telling the model not to repeat itself (`prompts.py`'s `_DEDUPE_NOTE`) -- it's a stopgap,
  not a guarantee. A real fix (detecting/stripping duplicate content before sending) is
  planned.
- **No guardrails yet** on the agent (prompt-injection resistance, output validation,
  rate limiting, etc.) -- planned, not yet implemented.
