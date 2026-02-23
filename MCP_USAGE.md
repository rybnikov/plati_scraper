# Plati Scraper MCP Server

## Run

```bash
python3 /Users/rbnkv/Projects/plati_scraper/mcp_server.py
```

This server speaks MCP over stdio and exposes one tool:

- `find_cheapest_reliable_options`

## Tool Example

```json
{
  "name": "find_cheapest_reliable_options",
  "arguments": {
    "query": "claude code",
    "limit": 5,
    "min_reviews": 500,
    "min_positive_ratio": 0.98
  }
}
```

## Claude Desktop Config Example

```json
{
  "mcpServers": {
    "plati-scraper": {
      "command": "python3",
      "args": ["/Users/rbnkv/Projects/plati_scraper/mcp_server.py"]
    }
  }
}
```
