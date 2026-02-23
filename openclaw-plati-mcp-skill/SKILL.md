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
   - `limit`: requested lots count (default 5)
   - `min_reviews`: optional seller reliability filter (default 0)
   - `min_positive_ratio`: optional seller reliability filter (default 0)
   - `max_pages`: default 6 for broader scan
2. Treat response as raw market data:
   - each lot includes `options[]`
   - each option group includes all visible `variants[]`
   - each variant has computed `price_if_selected`
3. Apply plan/duration/account-type filtering in the agent, not in MCP tool.
4. Include clickable listing links and selected option text in final output.
5. Clearly state filters used by the agent.

## Output format

Return a compact ranked list based on agent-side filtering:

`<rank>. <selected price> | <seller> | <selected duration> | <link>`

Include a one-line summary:

`Returned X lots after agent filtering from Y raw lots`
