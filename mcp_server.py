#!/usr/bin/env python3
import json
import os
import pathlib
import re
import sys
import warnings
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

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


def _parse_query_input(query: str) -> Dict[str, str]:
    q = (query or "").strip()
    out = {"product_query": q, "category_id": "", "source_url": ""}
    if not q.startswith("http://") and not q.startswith("https://"):
        return out

    parsed = urlparse(q)
    path = parsed.path or ""
    qs = parse_qs(parsed.query or "")
    out["source_url"] = q

    # Search root URL with optional query params.
    if path.rstrip("/") == "/search":
        for key in ("q", "query", "text", "term", "search", "searchString", "SearchStr"):
            v = (qs.get(key) or [""])[0].strip()
            if v:
                out["product_query"] = unquote(v)
                return out
        out["product_query"] = ""
        return out

    # Standard search URL: /search/<term>
    m = re.search(r"/search/([^/?#]+)", path)
    if m:
        out["product_query"] = unquote(m.group(1)).replace("-", " ").strip()
        return out

    # Category-like URL: /games/<slug>/<id>/ or similar.
    cat = re.search(r"/([^/]+)/([^/]+)/(\d+)/?$", path)
    if cat:
        slug = unquote(cat.group(2)).replace("-", " ").strip()
        out["product_query"] = slug or out["product_query"]
        out["category_id"] = cat.group(3)
        return out

    # Fallback: use last non-empty path part as query.
    parts = [unquote(p) for p in path.split("/") if p]
    if parts:
        out["product_query"] = parts[-1].replace("-", " ").strip()
    return out


def _split_terms(value: str) -> List[str]:
    if not value:
        return []
    return [t for t in re.split(r"[\s,;|]+", value.lower()) if t]


def _build_offer_search_text(title: str, options: List[Dict[str, Any]]) -> str:
    parts = [title or ""]
    for opt in options:
        parts.append(str(opt.get("name") or ""))
        parts.append(str(opt.get("label") or ""))
        for v in opt.get("variants") or []:
            parts.append(str(v.get("text") or ""))
    return " ".join(parts).lower()


def _sort_lots(items: List[Dict[str, Any]], sort_by: str) -> List[Dict[str, Any]]:
    if sort_by == "price_desc":
        return sorted(items, key=lambda x: (float(x.get("min_option_price", 0.0)), int(x.get("seller_reviews", 0))), reverse=True)
    if sort_by == "seller_reviews_desc":
        return sorted(items, key=lambda x: (int(x.get("seller_reviews", 0)), float(x.get("positive_ratio", 0.0)), -float(x.get("min_option_price", 0.0))), reverse=True)
    if sort_by == "reliability_desc":
        return sorted(items, key=lambda x: (float(x.get("positive_ratio", 0.0)), int(x.get("seller_reviews", 0)), -float(x.get("min_option_price", 0.0))), reverse=True)
    if sort_by == "title_asc":
        return sorted(items, key=lambda x: str(x.get("title", "")).lower())
    if sort_by == "title_desc":
        return sorted(items, key=lambda x: str(x.get("title", "")).lower(), reverse=True)
    # default and "price_asc"
    return sorted(items, key=lambda x: (float(x.get("min_option_price", 0.0)), -int(x.get("seller_reviews", 0))))


def find_cheapest_reliable_options(
    query: str,
    limit: int = 20,
    currency: str = "RUB",
    lang: str = "ru-RU",
    min_reviews: int = 0,
    min_positive_ratio: float = 0.0,
    max_pages: int = 6,
    per_page: int = 30,
    sort_by: str = "price_asc",
    min_price: float = 0.0,
    max_price: float = 0.0,
    include_terms: str = "",
    exclude_terms: str = "",
) -> Dict[str, Any]:
    if plati_scrape is None:
        raise RuntimeError(f"plati_scrape import failed: {_PLATI_IMPORT_ERROR}")

    parsed_q = _parse_query_input(query)
    q = parsed_q["product_query"]
    category_id = parsed_q["category_id"]
    source_url = parsed_q["source_url"]
    if not q and not category_id:
        raise ValueError("Empty search query. Use /search/<term> or pass text query, e.g. 'chatgpt plus'.")
    lots: List[Dict[str, Any]] = []
    seller_cache: Dict[int, Dict[str, Any]] = {}
    page = 1
    include_tokens = _split_terms(include_terms)
    exclude_tokens = _split_terms(exclude_terms)
    sort_norm = (sort_by or "price_asc").strip().lower()
    if sort_norm not in {
        "price_asc",
        "price_desc",
        "seller_reviews_desc",
        "reliability_desc",
        "title_asc",
        "title_desc",
    }:
        sort_norm = "price_asc"
    seen_product_ids: set[int] = set()

    while page <= max_pages:
        has_next_page = False
        source_items: List[Dict[str, Any]] = []
        if category_id:
            block_url = plati_scrape.build_category_block_url(
                category_id=category_id,
                page=page,
                rows=per_page,
                currency=currency,
                lang=lang,
                sort_by=sort_norm,
                subcategory_id=0,
            )
            block_html = plati_scrape.fetch_text(block_url)
            parsed_items = plati_scrape.parse_category_block_items(block_html)
            source_items = [
                {
                    "product_id": int(it.get("product_id") or 0),
                    "seller_id": 0,
                    "seller_name": str(it.get("seller_name") or ""),
                    "price": float(it.get("price") or 0.0),
                    "name": [{"locale": lang, "value": str(it.get("title") or "")}],
                    "link": str(it.get("link") or ""),
                }
                for it in parsed_items
            ]
            has_next_page = bool(parsed_items)
        else:
            search_url = plati_scrape.build_search_url(
                q,
                page,
                per_page,
                currency,
                lang,
                "popular",
                category_id="",
            )
            payload = plati_scrape.fetch_json(search_url)
            content = payload.get("content") or {}
            source_items = content.get("items") or []
            has_next_page = bool(content.get("has_next_page"))

        if not source_items:
            break

        for item in source_items:
            pid = int(item.get("product_id") or 0)
            seller_id = int(item.get("seller_id") or 0)
            if pid <= 0:
                continue

            try:
                details = plati_scrape.fetch_json(plati_scrape.build_product_data_url(pid, currency, lang), timeout=12)
            except Exception:
                continue
            if int(details.get("retval", -1)) != 0:
                continue

            product = details.get("product") or {}
            if not product:
                continue
            if str(product.get("is_available", 1)).lower() in {"0", "false"}:
                continue

            if seller_id <= 0:
                seller_id = int(((product.get("seller") or {}).get("id")) or 0)
            base_price = float(product.get("price") or item.get("price") or 0.0)
            title = plati_scrape.clean_text(str(product.get("name") or plati_scrape.pick_name(item.get("name") or [], lang)))
            link = str(item.get("link") or f"https://plati.market/itm/i/{pid}")
            seller_name = str((product.get("seller") or {}).get("name") or item.get("seller_name") or "")

            if seller_id > 0 and seller_id not in seller_cache:
                seller_cache[seller_id] = {"total": 0, "good": 0, "bad": 0, "positive_ratio": 0.0}
                try:
                    reviews = plati_scrape.fetch_json(plati_scrape.build_reviews_url(seller_id, lang), timeout=10)
                    good = int(reviews.get("totalGood", 0) or 0)
                    bad = int(reviews.get("totalBad", 0) or 0)
                    total = good + bad
                    seller_cache[seller_id] = {
                        "total": int(reviews.get("totalItems", 0) or 0),
                        "good": good,
                        "bad": bad,
                        "positive_ratio": (good / total) if total > 0 else 0.0,
                    }
                except Exception:
                    pass
            seller_info = seller_cache.get(seller_id, {"total": 0, "good": 0, "bad": 0, "positive_ratio": 0.0})
            if int(seller_info.get("total", 0)) < min_reviews:
                continue
            if float(seller_info.get("positive_ratio", 0.0)) < min_positive_ratio:
                continue

            rates = plati_scrape._build_rate_map(product)
            options_payload = []
            min_option_price = base_price
            for opt in (product.get("options") or []):
                variants = [v for v in (opt.get("variants") or []) if int(v.get("visible", 1) or 0) == 1]
                if not variants:
                    continue
                option_variants = []
                for v in variants:
                    delta = plati_scrape._modifier_value(v, base_price, currency, rates)
                    price_if_selected = max(base_price + delta, 0.0)
                    if price_if_selected < min_option_price:
                        min_option_price = price_if_selected
                    option_variants.append(
                        {
                            "value": v.get("value"),
                            "text": plati_scrape.clean_text(str(v.get("text", ""))),
                            "default": int(v.get("default", 0) or 0),
                            "modify": v.get("modify"),
                            "modify_type": v.get("modify_type"),
                            "modify_value": float(v.get("modify_value_default") or v.get("modify_value") or 0.0),
                            "price_if_selected": price_if_selected,
                            "price_if_selected_fmt": plati_scrape.format_price(price_if_selected, currency),
                        }
                    )
                options_payload.append(
                    {
                        "id": opt.get("id"),
                        "name": opt.get("name"),
                        "label": opt.get("label"),
                        "type": opt.get("type"),
                        "required": int(opt.get("required", 0) or 0),
                        "variants": option_variants,
                    }
                )

            lots.append(
                {
                    "product_id": pid,
                    "title": title,
                    "base_price": base_price,
                    "base_price_fmt": plati_scrape.format_price(base_price, currency),
                    "currency": currency,
                    "prices_default": (product.get("prices") or {}).get("default") or {},
                    "min_option_price": min_option_price,
                    "min_option_price_fmt": plati_scrape.format_price(min_option_price, currency),
                    "seller": seller_name,
                    "seller_reviews": seller_info.get("total", 0),
                    "good": seller_info.get("good", 0),
                    "bad": seller_info.get("bad", 0),
                    "positive_ratio": round(float(seller_info.get("positive_ratio", 0.0)), 4),
                    "link": link,
                    "options": options_payload,
                }
            )
            offer_search_text = _build_offer_search_text(title, options_payload)
            if include_tokens and not all(tok in offer_search_text for tok in include_tokens):
                lots.pop()
                continue
            if exclude_tokens and any(tok in offer_search_text for tok in exclude_tokens):
                lots.pop()
                continue
            if min_price > 0 and float(min_option_price) < float(min_price):
                lots.pop()
                continue
            if max_price > 0 and float(min_option_price) > float(max_price):
                lots.pop()
                continue
            if pid in seen_product_ids:
                lots.pop()
                continue
            seen_product_ids.add(pid)
        if not has_next_page:
            break
        page += 1

    lots = _sort_lots(lots, sort_norm)
    top = lots[: max(1, int(limit))]
    return {
        "query": query,
        "normalized_query": parsed_q["product_query"],
        "category_id": category_id,
        "source_url": source_url,
        "applied_filters": {
            "sort_by": sort_norm,
            "min_reviews": int(min_reviews),
            "min_positive_ratio": float(min_positive_ratio),
            "min_price": float(min_price),
            "max_price": float(max_price),
            "include_terms": include_tokens,
            "exclude_terms": exclude_tokens,
            "max_pages": int(max_pages),
            "per_page": int(per_page),
            "currency": currency,
            "lang": lang,
        },
        "total_candidates": len(lots),
        "reliable_candidates": len(lots),
        "returned": len(top),
        "items": top,
    }


TOOL_SCHEMA = {
    "name": "find_cheapest_reliable_options",
    "description": "Find Plati offers by text query or Plati URL, returning lots with links and full option variants.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Text query (e.g. 'claude code') or Plati URL (/search/<term>, /games/.../<id>/, /cat/.../<id>/)."},
            "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 100},
            "currency": {"type": "string", "default": "RUB"},
            "lang": {"type": "string", "default": "ru-RU"},
            "min_reviews": {"type": "integer", "default": 0, "minimum": 0},
            "min_positive_ratio": {"type": "number", "default": 0.0, "minimum": 0, "maximum": 1},
            "max_pages": {"type": "integer", "default": 6, "minimum": 1, "maximum": 30},
            "per_page": {"type": "integer", "default": 30, "minimum": 5, "maximum": 100},
            "sort_by": {
                "type": "string",
                "default": "price_asc",
                "enum": ["price_asc", "price_desc", "seller_reviews_desc", "reliability_desc", "title_asc", "title_desc"],
            },
            "min_price": {"type": "number", "default": 0},
            "max_price": {"type": "number", "default": 0},
            "include_terms": {"type": "string", "default": "", "description": "Space/comma-separated terms that must appear in lot title/options."},
            "exclude_terms": {"type": "string", "default": "", "description": "Space/comma-separated terms to exclude from lot title/options."},
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
                limit=int(args.get("limit", 20)),
                currency=str(args.get("currency", "RUB")),
                lang=str(args.get("lang", "ru-RU")),
                min_reviews=int(args.get("min_reviews", 0)),
                min_positive_ratio=float(args.get("min_positive_ratio", 0.0)),
                max_pages=int(args.get("max_pages", 6)),
                per_page=int(args.get("per_page", 30)),
                sort_by=str(args.get("sort_by", "price_asc")),
                min_price=float(args.get("min_price", 0.0)),
                max_price=float(args.get("max_price", 0.0)),
                include_terms=str(args.get("include_terms", "")),
                exclude_terms=str(args.get("exclude_terms", "")),
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
