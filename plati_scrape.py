#!/usr/bin/env python3
import argparse
import html
import json
import re
import sys
from typing import Dict, List, Optional, Tuple, Union
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen


SEARCH_ENDPOINT = "https://api.digiseller.com/api/cataloguer/front/products"
PRODUCT_DATA_ENDPOINT = "https://api.digiseller.com/api/products/{product_id}/data"
REVIEWS_ENDPOINT = "https://api.digiseller.com/api/reviews"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
PRO_RX = re.compile(r"\bpro\b|\bпро\b", flags=re.IGNORECASE)
API_OFFER_RX = re.compile(r"\bapi\b|api[\s_-]*key|token|токен|ключ", flags=re.IGNORECASE)
SUBSCRIPTION_RX = re.compile(
    r"подпис|subscription|месяц|month|год|year|активац|продлен",
    flags=re.IGNORECASE,
)
SERVICE_OPTION_RX = re.compile(r"вариант|услуг|оказани|service|plan|тариф|подпис", flags=re.IGNORECASE)
DURATION_OPTION_RX = re.compile(r"срок|duration|month|year|мес|год", flags=re.IGNORECASE)
ACTIVATION_RX = re.compile(r"активац|продлен|activation|renewal", flags=re.IGNORECASE)
ACCOUNT_CREATE_RX = re.compile(r"нет аккаунта|создайте|new account|выдач", flags=re.IGNORECASE)
PLUS_RX = re.compile(r"\bplus\b|плюс", flags=re.IGNORECASE)
GO_RX = re.compile(r"\bgo\b", flags=re.IGNORECASE)
BUSINESS_RX = re.compile(r"\bbusiness\b|бизнес", flags=re.IGNORECASE)
NOT_PRO_RX = re.compile(
    r"\bне\s+нужн[а-я]*\s+подписк[а-я]*\s+pro\b|\bwithout\s+pro\b|\bno\s+pro\b|\bбез\s+pro\b",
    flags=re.IGNORECASE,
)
SEARCH_SORT_MAP = {
    "popular": "popular",
    "price_asc": "popular",
    "price_desc": "popular",
    "new": "popular",
}


def fetch_json(url: str, timeout: int = 30) -> Dict:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def parse_search_query(search_url: str) -> str:
    parsed = urlparse(search_url)
    m = re.search(r"/search/([^/?#]+)", parsed.path)
    if not m:
        raise ValueError("Expected a search URL like https://plati.market/search/chatgpt")
    return unquote(m.group(1))


def build_search_url(query: str, page: int, count: int, currency: str, lang: str, sort_by: str) -> str:
    params = {
        "categoryId": "",
        "getProductsRecursive": "true",
        "sellerCategoryId": "",
        "productId": "",
        "productName": query,
        "ownerId": "plati",
        "ownerCategoryId": "",
        "sellerId": "",
        "sellerName": "",
        "currency": currency,
        "page": str(page),
        "count": str(count),
        "individual": "false",
        "video": "false",
        "image": "false",
        "sortBy": sort_by,
        "priceFrom": "",
        "priceTo": "",
        "includeAggregations": "true",
        "fuzzy": "false",
        "lang": lang,
    }
    return f"{SEARCH_ENDPOINT}?{urlencode(params)}"


def build_product_data_url(product_id: int, currency: str, lang: str) -> str:
    params = {
        "lang": lang,
        "currency": currency,
        "showHiddenVariants": "1",
    }
    return f"{PRODUCT_DATA_ENDPOINT.format(product_id=product_id)}?{urlencode(params)}"


def build_reviews_url(seller_id: int, lang: str) -> str:
    params = {
        "seller_id": str(seller_id),
        "owner_id": "1",
        "type": "all",
        "page": "1",
        "rows": "1",
        "lang": lang,
    }
    return f"{REVIEWS_ENDPOINT}?{urlencode(params)}"


def normalize_search_sort(sort_by: str) -> str:
    return SEARCH_SORT_MAP.get(sort_by, "popular")


def pick_name(name_entries: List[Dict], lang: str) -> str:
    if not name_entries:
        return ""
    for entry in name_entries:
        if entry.get("locale") == lang:
            return clean_text(str(entry.get("value", "")))
    for entry in name_entries:
        if entry.get("locale", "").startswith(lang.split("-")[0]):
            return clean_text(str(entry.get("value", "")))
    return clean_text(str(name_entries[0].get("value", "")))


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def extract_duration(title: str) -> str:
    t = title.lower()
    patterns = [
        (r"(\d+)\s*[-–/]\s*(\d+)\s*(мес|месяц|месяца|месяцев|м|month|months|mo|m)\b", "{0}-{1} months"),
        (r"(\d+)\s*[-–]?\s*(мес|месяц|месяца|месяцев|м|month|months|mo|m)\b", "{0} months"),
        (r"(\d+)\s*(год|года|лет|year|years|yr)\b", "{0} years"),
        (r"(\d+)\s*(дн|день|дня|дней|day|days)\b", "{0} days"),
    ]
    for rx, fmt in patterns:
        m = re.search(rx, t, flags=re.IGNORECASE)
        if not m:
            continue
        if "{1}" in fmt:
            return fmt.format(m.group(1), m.group(2))
        return fmt.format(m.group(1))
    return ""


def format_price(value: Union[float, int], currency: str) -> str:
    if int(value) == float(value):
        num = f"{int(value):,}".replace(",", " ")
    else:
        num = f"{value:,.2f}".replace(",", " ").rstrip("0").rstrip(".")
    symbol = "₽" if currency.upper() == "RUB" else currency.upper()
    return f"{num} {symbol}"


def _build_rate_map(product: Dict) -> Dict[str, float]:
    prices = (product.get("prices") or {}).get("default") or {}
    rates: Dict[str, float] = {}
    for k, v in prices.items():
        try:
            rates[str(k).upper()] = float(v)
        except Exception:
            continue
    return rates


def _modifier_value(variant: Dict, base_price: float, currency: str, rates: Dict[str, float]) -> float:
    modify_value = variant.get("modify_value_default")
    if modify_value is None:
        modify_value = variant.get("modify_value", 0)
    amount = float(modify_value or 0)
    modify_type = str(variant.get("modify_type") or "").upper()

    if modify_type in {"", currency.upper()}:
        return amount
    target = currency.upper()
    if modify_type in rates and target in rates and rates[modify_type] > 0:
        return amount * (rates[target] / rates[modify_type])
    if modify_type in {"%", "PERCENT"}:
        return base_price * amount / 100.0
    return amount


def _default_variant(option: Dict) -> Optional[Dict]:
    variants = option.get("variants") or []
    for variant in variants:
        if int(variant.get("default", 0) or 0) == 1:
            return variant
    return variants[0] if variants else None


def _compute_variant_price(base_price: float, option: Dict, variant: Dict, currency: str, rates: Dict[str, float]) -> float:
    default = _default_variant(option)
    default_delta = _modifier_value(default, base_price, currency, rates) if default else 0.0
    selected_delta = _modifier_value(variant, base_price, currency, rates)
    return max(base_price - default_delta + selected_delta, 0.0)


def _modifier_only_price(base_price: float, variants: List[Dict], currency: str, rates: Dict[str, float]) -> float:
    total = float(base_price)
    for v in variants:
        total += _modifier_value(v, base_price, currency, rates)
    return max(total, 0.0)


def _extract_duration_months(text: str) -> Optional[int]:
    t = (text or "").lower()
    m = re.search(r"(\d+)\s*(месяц|месяца|месяцев|мес|month|months|mo|m)\b", t)
    if m:
        return int(m.group(1))
    y = re.search(r"(\d+)\s*(год|года|лет|year|years|yr)\b", t)
    if y:
        return int(y.group(1)) * 12
    # "1-Month", "12-Month"
    hm = re.search(r"(\d+)\s*[-–]\s*month\b", t)
    if hm:
        return int(hm.group(1))
    return None


def _parse_request_preferences(request_text: str) -> Dict:
    t = (request_text or "").lower()
    plans = set()
    if PRO_RX.search(t):
        plans.add("pro")
    if PLUS_RX.search(t):
        plans.add("plus")
    if GO_RX.search(t):
        plans.add("go")
    if BUSINESS_RX.search(t):
        plans.add("business")
    if not plans:
        # By default expose all common subscription plans.
        plans = {"pro", "plus", "go", "business"}

    months = set()
    for m in re.finditer(r"(\d+)\s*(месяц|месяца|месяцев|мес|month|months|mo|m)\b", t):
        months.add(int(m.group(1)))
    for y in re.finditer(r"(\d+)\s*(год|года|лет|year|years|yr)\b", t):
        months.add(int(y.group(1)) * 12)
    if re.search(r"\bгод\b|\byear\b|12\s*(месяц|месяцев|month|months)\b", t):
        months.add(12)
    if re.search(r"\bмесяц\b|\bmonth\b", t):
        months.add(1)

    return {"plans": plans, "months": months}


def _plan_tags(text: str) -> set:
    low = (text or "").lower()
    tags = set()
    if PRO_RX.search(low) and not NOT_PRO_RX.search(low):
        tags.add("pro")
    if PLUS_RX.search(low):
        tags.add("plus")
    if GO_RX.search(low):
        tags.add("go")
    if BUSINESS_RX.search(low):
        tags.add("business")
    return tags


def extract_matching_choices(
    product_payload: Dict,
    base_price: float,
    currency: str,
    request_text: str,
    return_all: bool = False,
) -> List[Tuple[float, str, str]]:
    product = product_payload.get("product") or {}
    options = product.get("options") or []
    rates = _build_rate_map(product)
    prefs = _parse_request_preferences(request_text)
    candidates: List[Tuple[float, str, str, Optional[int]]] = []

    visible_options = []
    for option in options:
        variants = [v for v in (option.get("variants") or []) if int(v.get("visible", 1) or 0) == 1]
        if variants:
            visible_options.append((option, variants))

    def default_variant(option: Dict, variants: List[Dict]) -> Dict:
        d = _default_variant(option)
        if d and int(d.get("visible", 1) or 0) == 1:
            return d
        return variants[0]

    duration_option: Optional[Tuple[Dict, List[Dict]]] = None
    for option, variants in visible_options:
        label_text = f"{option.get('label','')} {option.get('name','')}".lower()
        if DURATION_OPTION_RX.search(label_text):
            duration_option = (option, variants)
            break
    # Fallback: some products encode duration inside activation method option.
    if duration_option is None:
        for option, variants in visible_options:
            if any(_extract_duration_months(clean_text(str(v.get("text", "")))) is not None for v in variants):
                duration_option = (option, variants)
                break

    # Gather plan-capable variants from selectable options.
    target_variants: List[Tuple[Dict, Dict]] = []
    for option, variants in visible_options:
        option_text = f"{option.get('label','')} {option.get('name','')}".lower()
        for variant in variants:
            text = clean_text(str(variant.get("text", "")))
            if not text:
                continue
            is_subscription_context = SUBSCRIPTION_RX.search(text) or SERVICE_OPTION_RX.search(option_text)
            tags = _plan_tags(text.lower())
            # Common pattern: dedicated PRO toggle where "not needed" means base/Plus path.
            if "подписк" in option_text and "pro" in option_text and NOT_PRO_RX.search(text.lower()):
                tags.add("plus")
            if tags & prefs["plans"] and is_subscription_context and not API_OFFER_RX.search(text):
                target_variants.append((option, variant))

    if not target_variants:
        return []

    for target_option, target_variant in target_variants:
        duration_candidates: List[Optional[Dict]] = [None]
        if duration_option:
            d_opt, d_vars = duration_option
            all_duration_vars = [v for v in d_vars if _extract_duration_months(clean_text(str(v.get("text", "")))) is not None]
            if prefs["months"]:
                filtered = [
                    v for v in all_duration_vars
                    if (_extract_duration_months(clean_text(str(v.get("text", "")))) in prefs["months"])
                ]
                duration_candidates = filtered or [default_variant(d_opt, d_vars)]
            else:
                duration_candidates = all_duration_vars or [default_variant(d_opt, d_vars)]

        for duration_variant in duration_candidates:
            selected: Dict[int, Dict] = {}
            duration_text = ""
            for option, variants in visible_options:
                key = int(option.get("id") or 0)
                choice = default_variant(option, variants)
                label_text = f"{option.get('label','')} {option.get('name','')}".lower()
                is_activation_option = ACTIVATION_RX.search(label_text) or "тип подпис" in label_text

                if option is target_option:
                    choice = target_variant
                elif duration_option and option is duration_option[0] and duration_variant is not None:
                    choice = duration_variant
                else:
                    # Prefer "activation/renewal" style option over account-creation variants.
                    if is_activation_option:
                        act = next(
                            (v for v in variants if ACTIVATION_RX.search(clean_text(str(v.get("text", "")).lower()))),
                            None,
                        )
                        if act is not None:
                            choice = act
                    # Avoid explicit account creation variants when alternatives exist.
                    if ACCOUNT_CREATE_RX.search(clean_text(str(choice.get("text", "")).lower())):
                        better = next(
                            (v for v in variants if not ACCOUNT_CREATE_RX.search(clean_text(str(v.get("text", "")).lower()))),
                            None,
                        )
                        if better is not None:
                            choice = better

                if DURATION_OPTION_RX.search(label_text):
                    duration_text = clean_text(str(choice.get("text", "")))

                # For unrelated options choose the least-cost visible variant.
                if (
                    option is not target_option
                    and not DURATION_OPTION_RX.search(label_text)
                    and not is_activation_option
                ):
                    cheapest = min(
                        variants,
                        key=lambda v: _modifier_value(v, base_price, currency, rates),
                    )
                    if _modifier_value(cheapest, base_price, currency, rates) < _modifier_value(choice, base_price, currency, rates):
                        choice = cheapest

                selected[key] = choice

            total = _modifier_only_price(base_price, list(selected.values()), currency, rates)
            choice_text = clean_text(str(target_variant.get("text", "")))
            joined_selection_text = " ".join(clean_text(str(v.get("text", ""))) for v in selected.values())
            duration = extract_duration(duration_text) or extract_duration(choice_text) or extract_duration(joined_selection_text)
            duration_months = _extract_duration_months(duration_text) or _extract_duration_months(choice_text)
            if duration_months is None:
                duration_months = _extract_duration_months(joined_selection_text)
            if API_OFFER_RX.search(choice_text):
                continue
            candidates.append((max(total, 0.0), choice_text, duration, duration_months))

    if not candidates:
        return []

    # Deduplicate and keep cheapest for each text/duration.
    dedup: Dict[Tuple[str, str], Tuple[float, str, str, Optional[int]]] = {}
    for c in candidates:
        key = (c[1], c[2])
        if key not in dedup or c[0] < dedup[key][0]:
            dedup[key] = c
    ordered = sorted(dedup.values(), key=lambda x: x[0])

    if prefs["months"]:
        best_by_month: Dict[int, Tuple[float, str, str, Optional[int]]] = {}
        for c in ordered:
            m = c[3]
            if m is None:
                continue
            if m in prefs["months"] and (m not in best_by_month or c[0] < best_by_month[m][0]):
                best_by_month[m] = c
        if best_by_month:
            return [best_by_month[m][:3] for m in sorted(best_by_month.keys())]

    if return_all:
        return [c[:3] for c in ordered]
    # Default: return cheapest relevant choice.
    return [ordered[0][:3]]


def classify_offer(
    details: Dict,
    fallback_title: str,
    base_price: float,
    currency: str,
    request_text: str,
    return_all_choices: bool = False,
) -> Optional[Dict]:
    if int(details.get("retval", -1)) != 0:
        return None

    product = details.get("product") or {}
    if not product:
        return None

    # Skip suspended/hidden/outdated goods.
    if str(product.get("is_available", 1)).lower() in {"0", "false"}:
        return None

    title = clean_text(str(product.get("name") or fallback_title))
    choices = extract_matching_choices(
        details,
        base_price,
        currency,
        request_text=request_text,
        return_all=return_all_choices,
    )
    if not choices:
        return None
    # Exclude API-key/token goods.
    if API_OFFER_RX.search(title):
        return None
    return {
        "title": title,
        "choices": [{"price_value": float(c[0]), "choice_text": c[1], "duration": c[2]} for c in choices],
    }


def search_all_products(
    search_url: str,
    lang: str,
    currency: str,
    per_page: int,
    max_items: int,
    sort_by: str,
    max_pages: int,
    request_text: str = "pro",
    return_all_choices: bool = False,
) -> List[Dict]:
    query = parse_search_query(search_url)
    rows = []
    page = 1
    product_cache: Dict[int, Optional[Dict]] = {}
    seller_cache: Dict[int, Dict[str, int]] = {}
    api_sort = normalize_search_sort(sort_by)
    warned_sort_fallback = False

    while len(rows) < max_items and page <= max_pages:
        api_url = build_search_url(query, page, per_page, currency, lang, api_sort)
        try:
            payload = fetch_json(api_url)
        except HTTPError as e:
            if e.code == 400 and api_sort != "popular":
                api_sort = "popular"
                if not warned_sort_fallback:
                    print(
                        f"Warning: API sort '{sort_by}' is unsupported, using 'popular' and local cost sort.",
                        file=sys.stderr,
                    )
                    warned_sort_fallback = True
                continue
            raise
        content = payload.get("content") or {}
        items = content.get("items") or []
        if not items:
            break

        for item in items:
            name = pick_name(item.get("name") or [], lang)
            pid = item.get("product_id")
            seller_id = int(item.get("seller_id") or 0)
            base_price = float(item.get("price", 0))
            seller_reviews = {"total": 0, "good": 0, "bad": 0}

            if pid not in product_cache:
                product_cache[pid] = None
                try:
                    details = fetch_json(build_product_data_url(int(pid), currency, lang), timeout=12)
                    product_cache[pid] = classify_offer(
                        details,
                        name,
                        base_price,
                        currency,
                        request_text=request_text,
                        return_all_choices=return_all_choices,
                    )
                except Exception:
                    product_cache[pid] = None

            offer = product_cache[pid]
            if not offer:
                continue
            name = str(offer["title"])

            if seller_id > 0:
                if seller_id not in seller_cache:
                    seller_cache[seller_id] = {"total": 0, "good": 0, "bad": 0}
                    try:
                        reviews = fetch_json(build_reviews_url(seller_id, lang), timeout=10)
                        seller_cache[seller_id] = {
                            "total": int(reviews.get("totalItems", 0) or 0),
                            "good": int(reviews.get("totalGood", 0) or 0),
                            "bad": int(reviews.get("totalBad", 0) or 0),
                        }
                    except Exception:
                        seller_cache[seller_id] = {"total": 0, "good": 0, "bad": 0}
                seller_reviews = seller_cache[seller_id]

            for choice in offer.get("choices", []):
                displayed_price = float(choice.get("price_value", base_price))
                choice_text = str(choice.get("choice_text", ""))
                duration = str(choice.get("duration", "")) or extract_duration(choice_text) or extract_duration(name) or ""
                row = {
                    "title": name,
                    "price": format_price(displayed_price, currency),
                    "price_value": displayed_price,
                    "duration": duration,
                    "seller": str(item.get("seller_name", "")),
                    "seller_reviews": seller_reviews["total"],
                    "seller_good_bad": f"{seller_reviews['good']}/{seller_reviews['bad']}",
                    "link": f"https://plati.market/itm/i/{pid}",
                    "pro_choice": choice_text,
                }
                rows.append(row)
                if len(rows) >= max_items:
                    break
            if len(rows) >= max_items:
                break

        if not content.get("has_next_page"):
            break
        page += 1

    return rows


def render_tui(rows: List[Dict], title: str) -> None:
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        raise RuntimeError("rich is not installed. Install with: pip install rich")

    table = Table(title=title, show_lines=False)
    table.add_column("#", justify="right")
    table.add_column("Cost", no_wrap=True)
    table.add_column("Pro Length", no_wrap=True)
    table.add_column("Seller", no_wrap=True)
    table.add_column("Seller Reviews", justify="right", no_wrap=True)
    table.add_column("Good/Bad", justify="right", no_wrap=True)
    table.add_column("Ad", overflow="fold")
    table.add_column("Link", no_wrap=True)

    for idx, row in enumerate(rows, start=1):
        ad_title = row["title"]
        if row.get("pro_choice"):
            ad_title = f"{ad_title} | PRO: {row['pro_choice']}"
        ad_text = ad_title
        link_text = f"[link={row['link']}]open[/link]"
        table.add_row(
            str(idx),
            row["price"],
            row["duration"] or "-",
            row["seller"],
            str(row["seller_reviews"]),
            row["seller_good_bad"],
            ad_text,
            link_text,
        )

    Console().print(table)


def render_html_report(rows: List[Dict], title: str, output_path: str) -> None:
    style = """
    :root {
      --bg: #0b1020;
      --panel: #101a33;
      --line: #25345d;
      --text: #e8edf9;
      --muted: #9eb0da;
      --accent: #5ca8ff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      background: radial-gradient(circle at top, #14254a 0%, var(--bg) 45%);
      color: var(--text);
    }
    .wrap { max-width: 1400px; margin: 28px auto; padding: 0 16px; }
    .card {
      background: linear-gradient(180deg, #132247 0%, var(--panel) 100%);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
    }
    h1 { margin: 0 0 6px; font-size: 22px; }
    .meta { color: var(--muted); margin-bottom: 14px; }
    .controls {
      display: flex;
      gap: 12px;
      align-items: center;
      margin-bottom: 12px;
      color: var(--muted);
      flex-wrap: wrap;
    }
    select {
      background: #0f1b38;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px 10px;
    }
    table { width: 100%; border-collapse: collapse; }
    th, td {
      padding: 10px 8px;
      border-bottom: 1px solid #223056;
      vertical-align: top;
    }
    th {
      color: #c9d7f5;
      text-align: left;
      position: sticky;
      top: 0;
      background: #122042;
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }
    tr:hover td { background: rgba(92, 168, 255, 0.08); }
    .num { text-align: right; white-space: nowrap; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .small { color: var(--muted); font-size: 12px; }
    """

    rows_html = []
    for idx, row in enumerate(rows, start=1):
        ad_title = row["title"]
        if row.get("pro_choice"):
            ad_title = f"{ad_title} | PRO: {row['pro_choice']}"
        rows_html.append(
            (
                f"<tr data-cost='{float(row.get('price_value', 0.0))}' "
                f"data-reviews='{int(row.get('seller_reviews', 0))}' "
                f"data-seller='{html.escape(str(row.get('seller', ''))).lower()}'>"
                f"<td class='num'>{idx}</td>"
                f"<td class='num'>{html.escape(str(row['price']))}</td>"
                f"<td>{html.escape(str(row['duration'] or '-'))}</td>"
                f"<td>{html.escape(str(row['seller']))}</td>"
                f"<td class='num'>{int(row.get('seller_reviews', 0)):,}</td>"
                f"<td class='num'>{html.escape(str(row['seller_good_bad']))}</td>"
                f"<td><a href='{html.escape(str(row['link']))}' target='_blank' rel='noreferrer'>{html.escape(ad_title)}</a></td>"
                f"<td><a href='{html.escape(str(row['link']))}' target='_blank' rel='noreferrer'>open</a></td>"
                "</tr>"
            )
        )

    html_doc = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  <style>{style}</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>{html.escape(title)}</h1>
      <div class="meta">Rows: {len(rows)} · Click headers to sort</div>
      <div class="controls">
        <label for="sort">Sort:</label>
        <select id="sort">
          <option value="cost:asc">Cost (cheap → expensive)</option>
          <option value="cost:desc">Cost (expensive → cheap)</option>
          <option value="reviews:desc">Seller reviews (high → low)</option>
          <option value="seller:asc">Seller (A → Z)</option>
        </select>
      </div>
      <table id="report">
        <thead>
          <tr>
            <th data-key="idx">#</th>
            <th data-key="cost">Cost</th>
            <th data-key="duration">Pro Length</th>
            <th data-key="seller">Seller</th>
            <th data-key="reviews">Seller Reviews</th>
            <th data-key="goodbad">Good/Bad</th>
            <th data-key="ad">Ad</th>
            <th data-key="link">Link</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows_html)}
        </tbody>
      </table>
      <p class="small">All links open in a new tab.</p>
    </div>
  </div>
  <script>
    (() => {{
      const table = document.getElementById('report');
      const body = table.querySelector('tbody');
      const sortSelect = document.getElementById('sort');
      const getText = (row, i) => row.children[i]?.innerText?.toLowerCase() ?? '';
      const keyToIdx = {{ idx: 0, cost: 1, duration: 2, seller: 3, reviews: 4, goodbad: 5, ad: 6, link: 7 }};

      function sortRows(key, dir) {{
        const rows = Array.from(body.querySelectorAll('tr'));
        rows.sort((a, b) => {{
          if (key === 'cost') {{
            const av = Number(a.dataset.cost || 0);
            const bv = Number(b.dataset.cost || 0);
            return dir === 'asc' ? av - bv : bv - av;
          }}
          if (key === 'reviews') {{
            const av = Number(a.dataset.reviews || 0);
            const bv = Number(b.dataset.reviews || 0);
            return dir === 'asc' ? av - bv : bv - av;
          }}
          if (key === 'idx') {{
            const av = Number(getText(a, 0));
            const bv = Number(getText(b, 0));
            return dir === 'asc' ? av - bv : bv - av;
          }}
          const i = keyToIdx[key] ?? 0;
          const av = getText(a, i);
          const bv = getText(b, i);
          return dir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
        }});
        rows.forEach((r, i) => {{
          r.children[0].innerText = String(i + 1);
          body.appendChild(r);
        }});
      }}

      sortSelect.addEventListener('change', () => {{
        const [key, dir] = sortSelect.value.split(':');
        sortRows(key, dir);
      }});

      let state = {{ key: 'cost', dir: 'asc' }};
      table.querySelectorAll('th').forEach((th) => {{
        th.addEventListener('click', () => {{
          const key = th.dataset.key;
          const dir = state.key === key && state.dir === 'asc' ? 'desc' : 'asc';
          state = {{ key, dir }};
          sortRows(key, dir);
        }});
      }});

      sortRows('cost', 'asc');
    }})();
  </script>
</body>
</html>"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Scrape Plati search results and render a TUI table."
    )
    p.add_argument("url", help="Search URL, e.g. https://plati.market/search/chatgpt")
    p.add_argument("--lang", default="ru-RU", help="Locale for names and API query")
    p.add_argument("--curr", default="RUB", help="Currency (RUB, USD, EUR, ...)")
    p.add_argument("--per-page", type=int, default=30, help="Items per API page")
    p.add_argument("--max-items", type=int, default=120, help="Maximum rows to load")
    p.add_argument("--max-pages", type=int, default=12, help="Maximum search pages to scan")
    p.add_argument(
        "--sort-by",
        default="popular",
        choices=["popular", "price_asc", "price_desc", "new"],
        help="Search sort order",
    )
    p.add_argument(
        "--cost-sort",
        default="asc",
        choices=["asc", "desc", "none"],
        help="Local sorting by rendered cost (asc = cheap to expensive)",
    )
    p.add_argument(
        "--format",
        default="html",
        choices=["html", "tui"],
        help="Output format",
    )
    p.add_argument(
        "--out",
        default="plati_report.html",
        help="HTML output file path (used when --format html)",
    )
    args = p.parse_args()

    try:
        rows = search_all_products(
            search_url=args.url,
            lang=args.lang,
            currency=args.curr,
            per_page=args.per_page,
            max_items=args.max_items,
            sort_by=args.sort_by,
            max_pages=args.max_pages,
            request_text=parse_search_query(args.url),
        )
        if args.cost_sort == "asc":
            rows.sort(key=lambda r: float(r.get("price_value", 0.0)))
        elif args.cost_sort == "desc":
            rows.sort(key=lambda r: float(r.get("price_value", 0.0)), reverse=True)
        title = f"Plati search: {args.url}"
        if args.format == "html":
            render_html_report(rows, title=title, output_path=args.out)
            print(f"HTML report saved to: {args.out}")
        else:
            render_tui(rows, title=title)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
