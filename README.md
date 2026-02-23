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
- `limit` (default `5`)
- `currency` (default `RUB`)
- `lang` (default `ru-RU`)
- `min_reviews` (default `500`)
- `min_positive_ratio` (default `0.98`)
- `max_pages` (default `6`)
- `per_page` (default `30`)

## Local development

```bash
python3 -m py_compile plati_scrape.py mcp_server.py
python3 plati_scrape.py "https://plati.market/search/chatgpt" --format html --out report.html
```

## Repository docs

- `AGENTS.md`: agent and automation instructions
- `CONTRIBUTING.md`: contribution flow, testing, release process
- `MCP_USAGE.md`: quick usage examples
