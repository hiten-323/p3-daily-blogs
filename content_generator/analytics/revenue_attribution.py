"""
Shopify Revenue Attribution — the engine learns from money, not just likes.

Every morning (after insights_fetch) this module:
  1. Pulls yesterday's orders from the Shopify Admin API
  2. Splits them into Instagram-attributed vs other
     (referring_site / landing_site containing instagram.com, l.instagram.com,
      or a utm_source=instagram parameter)
  3. Attributes Instagram revenue to the posts published in the attribution
     window (same day + 1) and updates their learning-engine entries
  4. Snapshots daily revenue so the founder can see the trend

Honest attribution note: Instagram captions cannot carry clickable links, so
per-post attribution uses day-level matching (posts published in the window
share the day's Instagram-attributed revenue). It is directional, not exact —
but over months it reliably separates content that sells from content that
doesn't.

Required GitHub Secrets:
    SHOPIFY_STORE_DOMAIN  — e.g. "purity-beans.myshopify.com"
    SHOPIFY_ADMIN_TOKEN   — Admin API access token (read_orders scope)
      Create: Shopify admin -> Settings -> Apps -> Develop apps ->
      Create app -> Configure Admin API scopes -> read_orders -> Install
"""
from __future__ import annotations
import datetime
import json
import logging
import os
import re
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_REV_PATH     = os.path.join(_LEARNING_DIR, "revenue_log.json")
from config.api_versions import SHOPIFY_API_VERSION as _API_VERSION
_TIMEOUT      = 30

_IG_MARKERS = ("instagram.com", "l.instagram.com", "utm_source=instagram", "utm_source=ig")


def is_configured() -> bool:
    return bool(normalize_shopify_domain(os.getenv("SHOPIFY_STORE_DOMAIN"))) and bool(
        os.getenv("SHOPIFY_ADMIN_TOKEN")
    )


def normalize_shopify_domain(raw: str | None) -> str:
    """Host only. Strips scheme, userinfo, port, path, query, and trailing slashes.

    A value like ``https://shop.myshopify.com/admin`` otherwise becomes the
    request host and the sales fetch fails DNS. The admin token is never part
    of the returned host and must not be logged.
    """
    text = str(raw or "").strip()
    text = re.sub(r"^[a-z][a-z0-9+.-]*://", "", text, flags=re.I)
    if "@" in text:
        text = text.split("@", 1)[1]
    text = text.split("?", 1)[0].split("#", 1)[0]
    text = text.split("/", 1)[0]
    if text.startswith("[") and "]" in text:
        text = text[1:text.index("]")]
    elif ":" in text:
        text = text.split(":", 1)[0]
    return text.strip().strip(".").lower()


def shopify_store_host() -> str:
    host = normalize_shopify_domain(os.getenv("SHOPIFY_STORE_DOMAIN"))
    if host:
        logger.info("[shopify] store host: %s", host)
    return host


# ── Shopify API ───────────────────────────────────────────────────────────────

def _shopify_get(path: str, params: dict) -> dict | None:
    domain = shopify_store_host()
    token  = os.getenv("SHOPIFY_ADMIN_TOKEN")
    if not domain or not token:
        return None
    url = f"https://{domain}/admin/api/{_API_VERSION}/{path}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, headers={
            "X-Shopify-Access-Token": token,
            "User-Agent": "PurityBeans/1.0",
        })
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("[revenue] Shopify API failed (%s): %s", path, e)
        return None


def _fetch_orders_since(since: datetime.datetime) -> list[dict]:
    """Fetch paid orders created since the given time (max 250 — plenty daily)."""
    data = _shopify_get("orders.json", {
        "status":          "any",
        "financial_status": "paid",
        "created_at_min":  since.isoformat(),
        "limit":           250,
        "fields":          "id,created_at,total_price,landing_site,referring_site,"
                           "customer,source_name,discount_codes",
    })
    return (data or {}).get("orders", [])


def _is_instagram_order(order: dict) -> bool:
    haystack = " ".join([
        str(order.get("landing_site") or ""),
        str(order.get("referring_site") or ""),
        str(order.get("source_name") or ""),
        str(order.get("_journey_sources") or ""),
    ]).lower()
    return any(m in haystack for m in _IG_MARKERS)


# ── Anonymous -> Identified bridge (Shopify customer journey, first-touch) ────
#
# Shopify already links a customer's anonymous browsing sessions to the order
# at checkout: order.customerJourneySummary carries the FIRST visit's source
# and UTM parameters plus the touchpoint count. Using it means an order that
# started from a reel days ago — but converted via a Google search — is still
# credited to Instagram (first-touch), instead of collapsing to last-click.
# No pixel, no cookie code, no website changes required.

_JOURNEY_QUERY = """
query($q: String!) {
  orders(first: 50, query: $q) {
    edges { node {
      legacyResourceId
      customerJourneySummary {
        momentsCount { count }
        firstVisit  { source referrerUrl utmParameters { source medium } }
        lastVisit   { source referrerUrl utmParameters { source medium } }
      }
    } }
  }
}
"""


def _shopify_graphql(query: str, variables: dict) -> dict | None:
    domain = shopify_store_host()
    token  = os.getenv("SHOPIFY_ADMIN_TOKEN")
    if not domain or not token:
        return None
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"https://{domain}/admin/api/{_API_VERSION}/graphql.json",
            data=body,
            headers={"X-Shopify-Access-Token": token,
                     "Content-Type": "application/json",
                     "User-Agent": "PurityBeans/1.0"},
            method="POST",
        )
        resp = urllib.request.urlopen(req, timeout=_TIMEOUT)
        return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        logger.warning("[revenue] Shopify GraphQL failed: %s", e)
        return None


def _enrich_with_journeys(orders: list[dict], since: datetime.datetime) -> None:
    """
    Attach first-touch journey sources to each order (in place) so
    _is_instagram_order sees the FULL journey, not just the last click.
    Degrades silently to last-click attribution if GraphQL is unavailable.
    """
    q = f"created_at:>={since.date().isoformat()} financial_status:paid"
    data = _shopify_graphql(_JOURNEY_QUERY, {"q": q})
    if not data:
        return
    journeys: dict[str, str] = {}
    try:
        for edge in data["data"]["orders"]["edges"]:
            node = edge["node"]
            js   = node.get("customerJourneySummary") or {}
            parts = []
            for visit_key in ("firstVisit", "lastVisit"):
                v = js.get(visit_key) or {}
                utm = v.get("utmParameters") or {}
                parts += [str(v.get("source") or ""), str(v.get("referrerUrl") or ""),
                          str(utm.get("source") or "")]
            journeys[str(node.get("legacyResourceId"))] = " ".join(p for p in parts if p)
    except Exception as e:
        logger.debug("[revenue] journey parse failed: %s", e)
        return
    matched = 0
    for o in orders:
        j = journeys.get(str(o.get("id")))
        if j:
            o["_journey_sources"] = j
            matched += 1
    if matched:
        logger.info("[revenue] First-touch journeys attached to %d/%d orders", matched, len(orders))


# ── Attribution ───────────────────────────────────────────────────────────────

def run_revenue_attribution(window_hours: int = 48) -> dict:
    """
    Main entry point — called by the daily pipeline.

    Returns {"orders": n, "revenue": x, "ig_orders": n, "ig_revenue": x,
             "attributed_posts": n} or a skip marker when not configured.
    """
    if not is_configured():
        logger.info("[revenue] Shopify not configured — skipping "
                    "(set SHOPIFY_STORE_DOMAIN + SHOPIFY_ADMIN_TOKEN)")
        return {"skipped": True}

    now    = datetime.datetime.now()
    since  = now - datetime.timedelta(hours=window_hours)
    orders = _fetch_orders_since(since)
    _enrich_with_journeys(orders, since)   # first-touch, not just last-click

    total_rev = sum(float(o.get("total_price") or 0) for o in orders)
    ig_orders = [o for o in orders if _is_instagram_order(o)]
    ig_rev    = sum(float(o.get("total_price") or 0) for o in ig_orders)
    returning = sum(
        1 for o in orders
        if (o.get("customer") or {}).get("orders_count", 1) and
           int((o.get("customer") or {}).get("orders_count", 1)) > 1
    )

    # Daily revenue snapshot (last 365 kept)
    snapshot = {
        "date":       now.date().isoformat(),
        "orders":     len(orders),
        "revenue":    round(total_rev, 2),
        "ig_orders":  len(ig_orders),
        "ig_revenue": round(ig_rev, 2),
        "aov":        round(total_rev / len(orders), 2) if orders else 0.0,
        "returning_customers": returning,
    }
    _append_snapshot(snapshot)

    # Deduplicate by order ID so we don't attribute the same order multiple times
    attributed_orders_path = os.path.join(_LEARNING_DIR, "attributed_orders.json")
    attributed_ledger = []
    if os.path.exists(attributed_orders_path):
        try:
            with open(attributed_orders_path, "r", encoding="utf-8") as f:
                attributed_ledger = json.load(f)
        except Exception:
            pass
            
    ledger_set = set(attributed_ledger)
    new_ig_orders = [o for o in ig_orders if str(o.get("id")) not in ledger_set]
    new_ig_rev = sum(float(o.get("total_price") or 0) for o in new_ig_orders)

    # Attribute Instagram revenue to posts in the window FIRST. Pass the order
    # objects, not (total, count) — the ledger must be written from the actual
    # ids that were attributed, never inferred from a post tally.
    result = _attribute_to_posts(new_ig_orders, since)
    attributed_ids = result["attributed_order_ids"]

    # Only orders genuinely attributed enter the ledger. Anything left in
    # unattributed_order_ids stays pending and is retried on a later run,
    # instead of being marked done because *some* post was updated.
    if attributed_ids:
        attributed_ledger_dict = {}
        if isinstance(attributed_ledger, dict):
            attributed_ledger_dict = attributed_ledger
        elif isinstance(attributed_ledger, list):
            for i in attributed_ledger:
                attributed_ledger_dict[str(i)] = {"attributed_at": now.isoformat()}

        for oid in attributed_ids:
            attributed_ledger_dict[oid] = {"attributed_at": now.isoformat(),
                                           "attribution_version": 3,
                                           "basis": "day_level_split"}

        with open(attributed_orders_path, "w", encoding="utf-8") as f:
            json.dump(attributed_ledger_dict, f, indent=2)

    if result["unattributed_order_ids"]:
        logger.info("[revenue] %d order(s) left pending attribution: %s",
                    len(result["unattributed_order_ids"]),
                    result["unattributed_order_ids"][:5])
    attributed = result["posts_updated"]

    logger.info(
        "[revenue] %d orders / Rs %.0f total | Instagram: %d orders / Rs %.0f "
        "-> attributed to %d post(s)",
        len(orders), total_rev, len(new_ig_orders), new_ig_rev, attributed,
    )
    return {**snapshot, "attributed_posts": attributed}


def _append_snapshot(snapshot: dict) -> None:
    os.makedirs(_LEARNING_DIR, exist_ok=True)
    entries = []
    if os.path.exists(_REV_PATH):
        try:
            with open(_REV_PATH, "r", encoding="utf-8") as f:
                entries = json.load(f)
        except Exception:
            entries = []
    # One snapshot per date — replace same-day reruns
    entries = [e for e in entries if e.get("date") != snapshot["date"]]
    entries.append(snapshot)
    with open(_REV_PATH, "w", encoding="utf-8") as f:
        json.dump(entries[-365:], f, indent=2)


def _attribute_to_posts(orders: list[dict], since: datetime.datetime) -> dict:
    """
    Spread Instagram-attributed revenue across the posts published in the window.

    ATTRIBUTION IS DAY-LEVEL, NOT ORDER-TO-POST DETERMINISTIC.
      Shopify tells us an order came from Instagram; it does not tell us which
      post. So the window's revenue is split evenly across the window's posts.
      A post credited with Rs 400 did not necessarily earn Rs 400 — it is one of
      N posts that were live when Rs 400*N arrived. Directionally useful over
      many days, never precise for a single post. True per-post attribution
      needs distinct per-post landing URLs (a link-in-bio router).

    Returns an explicit result rather than a bare count. The previous version
    returned len(posts_updated), and the caller treated "any posts updated" as
    "every order attributed" — two different quantities, so the ledger could be
    written on the strength of a number that never referred to orders at all:

        {"attributed_order_ids": [...],   # safe to write to the ledger
         "unattributed_order_ids": [...], # stay pending, retried next run
         "attributed_revenue": float,
         "posts_updated": int}
    """
    order_ids = [str(o.get("id")) for o in (orders or []) if o.get("id")]
    empty = {"attributed_order_ids": [], "unattributed_order_ids": order_ids,
             "attributed_revenue": 0.0, "posts_updated": 0}
    if not orders:
        return {**empty, "unattributed_order_ids": []}
    try:
        from content_generator.core import learning_engine as le
    except Exception as e:
        logger.warning("[revenue] learning engine unavailable: %s", e)
        return empty

    entries = le._load_log()
    in_window = []
    for e in entries:
        try:
            when = datetime.datetime.fromisoformat(str(e.get("posted_at", ""))[:19])
        except Exception:
            continue
        if when >= since:
            in_window.append(e)

    # No posts in the window means nothing to attribute TO. The orders stay
    # pending so a later run — once those posts are recorded — can attribute
    # them, instead of being silently marked done against nothing.
    if not in_window:
        logger.info("[revenue] %d Instagram order(s) but no posts in window — "
                    "left unattributed for a later run", len(order_ids))
        return empty

    revenue = sum(float(o.get("total_price") or 0) for o in orders)
    per_post_rev    = revenue / len(in_window)
    per_post_orders = len(orders) / len(in_window)
    for e in in_window:
        m = e.setdefault("metrics", {})
        m["revenue"] = round(m.get("revenue", 0) + per_post_rev, 2)
        m["orders"]  = round(m.get("orders", 0) + per_post_orders, 2)
    le._save_log(entries)
    return {"attributed_order_ids": order_ids, "unattributed_order_ids": [],
            "attributed_revenue": round(revenue, 2), "posts_updated": len(in_window)}


def get_revenue_trend(days: int = 30) -> dict:
    """Revenue summary for founder report."""
    if not os.path.exists(_REV_PATH):
        return {}
    try:
        with open(_REV_PATH, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except Exception:
        return {}
    recent = entries[-days:]
    if not recent:
        return {}
    return {
        "days":            len(recent),
        "total_revenue":   round(sum(e.get("revenue", 0) for e in recent), 2),
        "total_orders":    sum(e.get("orders", 0) for e in recent),
        "ig_revenue":      round(sum(e.get("ig_revenue", 0) for e in recent), 2),
        "ig_orders":       sum(e.get("ig_orders", 0) for e in recent),
        "avg_aov":         round(sum(e.get("aov", 0) for e in recent) / len(recent), 2),
    }
