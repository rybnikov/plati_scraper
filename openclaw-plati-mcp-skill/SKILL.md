---
name: plati-mcp-search
description: Find cheapest reliable subscription offers from Plati using the local MCP server. Use when users ask for best price options, reliable sellers, PRO/Plus subscription comparisons, or top-N cheapest offers for a product keyword like "claude code" or "chatgpt plus".
---

# Plati MCP Search Skill

Prerequisite: install the MCP server package:

`npm i -g plati-mcp-server`

Configure an MCP server named `plati-scraper` in your local OpenClaw/Claude config:

`command: plati-mcp-server`

If your MCP client hangs on initialize, run server with debug stderr enabled:

`PLATI_MCP_STDERR=1 plati-mcp-server`

## Workflow

1. Call MCP tool `find_cheapest_reliable_options` with:
   - `query`: user search intent
   - `limit`: requested count (default 5)
   - `min_reviews`: default 500 unless user asks for looser filter
   - `min_positive_ratio`: default 0.98 unless user asks for looser filter
   - `max_pages`: default 6 for broader scan
2. Return results sorted by lowest `price_value` first.
3. Include clickable listing links in final output.
4. If no results, relax reliability thresholds once:
   - `min_reviews`: 200
   - `min_positive_ratio`: 0.95
5. Clearly state filters used.

## Output format

Return a compact ranked list:

`<rank>. <price> | <seller> | <duration> | <link>`

Include a one-line summary:

`Returned X reliable offers from Y candidates`
