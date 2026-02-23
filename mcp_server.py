#!/usr/bin/env python3
import json
import os
import pathlib
import sys
import warnings
from typing import Any, Dict, List
from urllib.parse import quote

# Ensure local imports work even when launcher does not pass PYTHONPATH/cwd.
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

_PLATI_IMPORT_ERROR = ""
try:
    import plati_scrape
except Exception as e:  # pragma: no cover - defensive path
    plati_scrape = None  # type: ignore[assignment]
    _PLATI_IMPORT_ERROR = str(e)


def _read_message() -> Dict[str, Any]:
    # Dual framing support:
    # 1) MCP/LSP-style Content-Length headers + JSON body
    # 2) NDJSON (one JSON message per line)
    #
    # We auto-detect by first line and keep response framing symmetrical.
    first = sys.stdin.buffer.readline()
    if not first:
        raise EOFError

    # NDJSON path.
    stripped = first.strip()
    if stripped.startswith(b"{"):
        _STATE["framing"] = "ndjson"
        return json.loads(stripped.decode("utf-8"))

    # Content-Length path.
    headers: Dict[str, str] = {}
    line = first
    while True:
        if line in (b"\r\n", b"\n"):
            break
        decoded = line.decode("utf-8")
        if ":" not in decoded:
            raise ValueError("Invalid header line")
        key, value = decoded.split(":", 1)
        headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError
    content_length = int(headers.get("content-length", "0"))
    payload = sys.stdin.buffer.read(content_length)
    _STATE["framing"] = "content-length"
    return json.loads(payload.decode("utf-8"))


def _write_message(msg: Dict[str, Any]) -> None:
    if _STATE.get("framing") == "ndjson":
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        return
    data = json.dumps(msg, ensure_ascii=False).encode("utf-8")
    header = f"Content-Length: {len(data)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(header)
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _ok(req_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _parse_good_bad(value: str) -> Dict[str, int]:
    try:
        good_s, bad_s = value.split("/", 1)
        return {"good": int(good_s), "bad": int(bad_s)}
    except Exception:
        return {"good": 0, "bad": 0}


def find_cheapest_reliable_options(
    query: str,
    limit: int = 5,
    currency: str = "RUB",
    lang: str = "ru-RU",
    min_reviews: int = 500,
    min_positive_ratio: float = 0.98,
    max_pages: int = 6,
    per_page: int = 30,
) -> Dict[str, Any]:
    if plati_scrape is None:
        raise RuntimeError(f"plati_scrape import failed: {_PLATI_IMPORT_ERROR}")
    search_url = f"https://plati.market/search/{quote(query, safe='')}"
    rows = plati_scrape.search_all_products(
        search_url=search_url,
        lang=lang,
        currency=currency,
        per_page=per_page,
        max_items=per_page * max_pages,
        sort_by="popular",
        max_pages=max_pages,
    )

    filtered: List[Dict[str, Any]] = []
    for row in rows:
        reviews = int(row.get("seller_reviews", 0) or 0)
        gb = _parse_good_bad(str(row.get("seller_good_bad", "0/0")))
        total = gb["good"] + gb["bad"]
        ratio = (gb["good"] / total) if total > 0 else 0.0
        if reviews < min_reviews:
            continue
        if ratio < min_positive_ratio:
            continue
        filtered.append(
            {
                "title": row.get("title", ""),
                "price": row.get("price", ""),
                "price_value": float(row.get("price_value", 0.0) or 0.0),
                "duration": row.get("duration", ""),
                "seller": row.get("seller", ""),
                "seller_reviews": reviews,
                "good": gb["good"],
                "bad": gb["bad"],
                "positive_ratio": round(ratio, 4),
                "link": row.get("link", ""),
                "pro_option": row.get("pro_choice", ""),
            }
        )

    filtered.sort(key=lambda r: (r["price_value"], -r["seller_reviews"]))
    top = filtered[: max(1, int(limit))]
    return {
        "query": query,
        "total_candidates": len(rows),
        "reliable_candidates": len(filtered),
        "returned": len(top),
        "items": top,
    }


TOOL_SCHEMA = {
    "name": "find_cheapest_reliable_options",
    "description": "Find cheapest reliable Plati offers for PRO subscriptions.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search term, e.g. 'claude code'"},
            "limit": {"type": "integer", "default": 5, "minimum": 1, "maximum": 50},
            "currency": {"type": "string", "default": "RUB"},
            "lang": {"type": "string", "default": "ru-RU"},
            "min_reviews": {"type": "integer", "default": 500, "minimum": 0},
            "min_positive_ratio": {"type": "number", "default": 0.98, "minimum": 0, "maximum": 1},
            "max_pages": {"type": "integer", "default": 6, "minimum": 1, "maximum": 30},
            "per_page": {"type": "integer", "default": 30, "minimum": 5, "maximum": 100},
        },
        "required": ["query"],
    },
}

_STATE: Dict[str, str] = {"framing": "content-length"}


def _handle_request(msg: Dict[str, Any]) -> Dict[str, Any]:
    method = msg.get("method")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        return _ok(
            req_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "plati-scraper-mcp", "version": "0.1.0"},
            },
        )
    if method == "ping":
        return _ok(req_id, {})
    if method == "tools/list":
        return _ok(req_id, {"tools": [TOOL_SCHEMA]})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name != "find_cheapest_reliable_options":
            return _err(req_id, -32602, f"Unknown tool: {name}")
        try:
            result = find_cheapest_reliable_options(
                query=str(args["query"]),
                limit=int(args.get("limit", 5)),
                currency=str(args.get("currency", "RUB")),
                lang=str(args.get("lang", "ru-RU")),
                min_reviews=int(args.get("min_reviews", 500)),
                min_positive_ratio=float(args.get("min_positive_ratio", 0.98)),
                max_pages=int(args.get("max_pages", 6)),
                per_page=int(args.get("per_page", 30)),
            )
            return _ok(
                req_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                    "structuredContent": result,
                },
            )
        except KeyError:
            return _err(req_id, -32602, "Missing required argument: query")
        except Exception as e:
            return _ok(req_id, {"isError": True, "content": [{"type": "text", "text": f"Error: {e}"}]})

    return _err(req_id, -32601, f"Method not found: {method}")


def main() -> int:
    # Some MCP clients incorrectly merge stderr/stdout. Keep stderr quiet by default.
    # Set PLATI_MCP_STDERR=1 to keep stderr for debugging.
    if os.environ.get("PLATI_MCP_STDERR", "0") != "1":
        try:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
        except Exception:
            pass
    warnings.filterwarnings("ignore")

    while True:
        try:
            msg = _read_message()
        except EOFError:
            return 0
        except Exception:
            continue

        if "id" not in msg:
            # Notifications (e.g. notifications/initialized) are allowed and require no response.
            continue
        response = _handle_request(msg)
        _write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
