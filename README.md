# Plati MCP Server

MCP stdio server and scraper for Plati offers with strong filtering for subscription-type offers and seller reliability.

## What this project provides

- MCP server (`mcp_server.py`) exposing:
  - `find_cheapest_reliable_options`
- Offer parsing engine (`plati_scrape.py`) that:
  - Filters non-subscription/API-key offers
  - Parses multi-option variants (PRO/Plus/etc.)
  - Computes option-adjusted prices using ad-specific `prices` fields
  - Collects seller review quality signals
- HTML reporting mode for manual review

## Install (global CLI)

```bash
npm i -g plati-mcp-server
```

## Run MCP server

```bash
plati-mcp-server
```

## MCP config (OpenClaw / Claude Desktop style)

```json
{
  "mcpServers": {
    "plati-scraper": {
      "command": "plati-mcp-server",
      "args": []
    }
  }
}
```

## Tool: `find_cheapest_reliable_options`

Input arguments:

- `query` (required): Search phrase (for example `claude code`)
- `limit` (default `20`)
- `currency` (default `RUB`)
- `lang` (default `ru-RU`)
- `min_reviews` (default `0`)
- `min_positive_ratio` (default `0.0`)
- `max_pages` (default `6`)
- `per_page` (default `30`)
- `sort_by` (default `price_asc`): one of `price_asc`, `price_desc`, `seller_reviews_desc`, `reliability_desc`, `title_asc`, `title_desc`
- `min_price` / `max_price` (optional numeric range)
- `include_terms` / `exclude_terms` (optional space/comma-separated token filters applied to title/options text)

## Local development

```bash
python3 -m py_compile plati_scrape.py mcp_server.py
python3 plati_scrape.py "https://plati.market/search/chatgpt" --format html --out report.html
```

## Repository docs

- `AGENTS.md`: agent and automation instructions
- `CONTRIBUTING.md`: contribution flow, testing, release process
- `MCP_USAGE.md`: quick usage examples
