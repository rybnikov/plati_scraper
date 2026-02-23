# AGENTS.md

This file is for automated agents and maintainers working in this repository.

## Project scope

- `plati_scrape.py`: core scraping/parsing/filtering engine.
- `mcp_server.py`: MCP stdio server exposing search tool(s).
- `bin/plati-mcp-server.js`: npm CLI wrapper that launches Python MCP server.
- `openclaw-plati-mcp-skill/SKILL.md`: OpenClaw marketplace skill definition.

## Primary expectations

1. Keep MCP behavior stable:
   - Tool name: `find_cheapest_reliable_options`
   - Response shape: keep `structuredContent` backward compatible.
2. Preserve parsing quality:
   - Use ad-local pricing fields for conversion.
   - Parse multi-option combinations for subscription plans.
   - Filter API-key/token-like offers out.
3. Avoid machine-specific paths in any published artifacts.

## Local commands

```bash
python3 -m py_compile plati_scrape.py mcp_server.py
python3 plati_scrape.py "https://plati.market/search/chatgpt" --format html --out report.html
node bin/plati-mcp-server.js
```

## Validation checklist before release

1. Compile check passes.
2. MCP handshake works (`initialize`, `tools/list`, `tools/call`).
3. At least one known product ID case still parses correctly (for example complex multi-option case).
4. Package dry-run passes:
   - `npm_config_cache=/tmp/npm-cache npm pack --dry-run`

## Security and privacy

- Never commit personal auth tokens.
- Never hardcode private local paths.
- Keep external calls limited to required public endpoints.

## Publishing targets

- npm package: `plati-mcp-server`
- OpenClaw skill slug: `plati-mcp-search`

