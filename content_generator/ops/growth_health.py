"""Production health checks for the Purity Beans Growth OS.

This module deliberately does not change business logic. It verifies that the
systems which the growth loop depends on are actually healthy: measurement,
Meta account access, attribution hygiene, policy configuration, asset
provenance, and learning readiness.

Exit code 0 means the engine is safe to run. A hard failure means a dependency
cannot be trusted and the caller should fail closed rather than publish.
"""
from __future__ import annotations

import datetime
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
LEARNING = ROOT / "output" / "learning"
POLICY = ROOT / "founder_policies.yaml"
WORKFLOW = ROOT / ".github" / "workflows" / "daily.yml"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_learning_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not LEARNING.exists():
        return records
    for path in LEARNING.rglob("*.json"):
        if "quarantine" in path.name.lower() or "archive" in path.parts:
            continue
        data = _load_json(path)
        if isinstance(data, list):
            records.extend(x for x in data if isinstance(x, dict))
        elif isinstance(data, dict):
            for key in ("posts", "entries", "records", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    records.extend(x for x in value if isinstance(x, dict))
    return records


def _metric_state(record: dict[str, Any], name: str) -> str:
    metrics = record.get("metrics")
    if not isinstance(metrics, dict):
        metrics = record
    if name not in metrics:
        return "unknown"
    value = metrics.get(name)
    if value is None:
        return "unknown"
    return "measured"


def measurement_health() -> dict[str, Any]:
    records = _iter_learning_records()
    measured = 0
    unknown = 0
    for record in records:
        state = _metric_state(record, "views")
        if state == "measured":
            measured += 1
        else:
            unknown += 1

    status = "ok" if measured else ("cold" if records else "empty")
    res: dict[str, Any] = {
        "status": status,
        "records": len(records),
        "measured_views": measured,
        "unknown_views": unknown,
    }

    # Explicit permission diagnostic: surface missing instagram_manage_insights
    # scope rather than misrepresenting it as an ordinary cold start.
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if token:
        try:
            from content_generator.ops.meta_token_health import inspect_token
            info = inspect_token(token)
            scopes = set(info.get("scopes") or [])
            if "instagram_manage_insights" not in scopes:
                res["status"] = "permission_missing"
                res["missing_permission"] = "instagram_manage_insights"
                res["detail"] = "instagram_manage_insights scope required for media insights"
        except Exception:
            pass

    return res


def meta_preflight() -> dict[str, Any]:
    account = os.getenv("INSTAGRAM_ACCOUNT_ID")
    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    if not account or not token:
        return {"status": "not_configured"}
    from urllib.parse import quote
    url = f"https://graph.facebook.com/v24.0/{quote(str(account), safe='')}?fields=id,username"
    try:
        req = Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "PurityBeans/1.0",
            },
        )
        with urlopen(req, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if payload.get("id"):
            return {"status": "ok", "account_id": str(payload["id"])}
        return {"status": "failed", "detail": "missing_id_in_response"}
    except Exception as exc:
        detail = str(exc).replace(token, "***")
        res = {"status": "failed", "error_type": type(exc).__name__, "error_detail": detail}
        if hasattr(exc, "code"):
            res["status_code"] = exc.code
        return res


def config_health() -> dict[str, Any]:
    result: dict[str, Any] = {"status": "ok", "warnings": []}
    text = WORKFLOW.read_text(encoding="utf-8") if WORKFLOW.exists() else ""

    # Extended content must come from founder policy, not a workflow hardcode.
    if 'ENABLE_EXTENDED_CONTENT: "true"' in text:
        result["warnings"].append("workflow_hardcodes_extended_content")

    try:
        from content_generator.core.founder_policy import policy
        if policy().get("enable_extended_content"):
            result["warnings"].append("extended_content_enabled_via_policy")
    except Exception:
        if POLICY.exists() and "enable_extended_content: true" in POLICY.read_text(encoding="utf-8"):
            result["warnings"].append("extended_content_enabled_via_policy")

    brand_guard = ROOT / "content_generator" / "core" / "brand_guard.py"
    if brand_guard.exists() and "EDITORIAL_THRESHOLD" in brand_guard.read_text(encoding="utf-8"):
        result["warnings"].append("legacy_editorial_threshold_symbol_present")

    if not POLICY.exists():
        result["status"] = "failed"
        result["warnings"].append("founder_policy_missing")
    return result


def shopify_access_health() -> dict[str, Any]:
    """Verify read_orders access without logging or persisting order details."""
    try:
        from content_generator.analytics import revenue_attribution
        if not revenue_attribution.is_configured():
            return {"status": "not_configured", "recent_orders": 0, "instagram_marked_orders": 0}
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)
        params = {
            "status": "any",
            "created_at_min": since.isoformat().replace("+00:00", "Z"),
            "limit": 250,
            "fields": "id,created_at,landing_site,referring_site,source_name",
        }
        data = None
        for attempt in range(3):
            data = revenue_attribution._shopify_get("orders.json", params)
            if isinstance(data, dict) and isinstance(data.get("orders"), list):
                break
            if attempt < 2:
                time.sleep(2 ** attempt)
        if not isinstance(data, dict) or not isinstance(data.get("orders"), list):
            return {"status": "failed", "recent_orders": 0, "instagram_marked_orders": 0}
        orders = [row for row in data["orders"] if isinstance(row, dict)]
        marked = sum(1 for row in orders if revenue_attribution._is_instagram_order(row))
        return {"status": "ok", "recent_orders": len(orders), "instagram_marked_orders": marked}
    except Exception as exc:
        return {"status": "failed", "recent_orders": 0, "instagram_marked_orders": 0,
                "error_type": type(exc).__name__}


def attribution_health() -> dict[str, Any]:
    path = LEARNING / "attributed_orders.json"
    if not path.exists():
        return {"status": "empty", "orders": 0}
    data = _load_json(path)
    if isinstance(data, dict):
        ids = list(data.keys())
        duplicate_ids = len(ids) != len(set(ids))
    elif isinstance(data, list):
        ids = [str(x) for x in data]
        duplicate_ids = len(ids) != len(set(ids))
    else:
        return {"status": "failed", "orders": 0}
    return {"status": "failed" if duplicate_ids else "ok", "orders": len(ids)}


def run() -> int:
    measurement = measurement_health()
    meta = meta_preflight()
    config = config_health()
    attribution = attribution_health()
    shopify = shopify_access_health()

    print("=== PURITY BEANS GROWTH OS HEALTH ===")
    print(f"Measurement : {measurement['status']} | records={measurement['records']} measured_views={measurement['measured_views']}" + (f" | missing={measurement.get('missing_permission')}" if measurement.get("missing_permission") else ""))
    print(f"Meta access : {meta['status']}")
    print(f"Attribution : {attribution['status']} | orders={attribution['orders']}")
    print(f"Shopify API : {shopify['status']} | recent_orders={shopify['recent_orders']} instagram_marked={shopify['instagram_marked_orders']}")
    print(f"Config      : {config['status']} | warnings={','.join(config['warnings']) or 'none'}")

    # Cold measurement is not a publishing failure. It is explicitly surfaced
    # so the learning layer cannot claim confidence it has not earned.
    hard_failures: list[str] = []
    if meta["status"] == "failed":
        hard_failures.append("instagram_graph_access")
    if measurement["status"] == "permission_missing":
        hard_failures.append("instagram_insights_permission")
    if attribution["status"] == "failed":
        hard_failures.append("attribution_ledger")
    if shopify["status"] != "ok":
        hard_failures.append("shopify_read_orders")
    if config["status"] == "failed":
        hard_failures.append("policy_configuration")

    if hard_failures:
        print("HEALTH: FAIL-CLOSED | " + ", ".join(hard_failures))
        return 1

    if measurement["status"] == "permission_missing":
        print(f"HEALTH: DEGRADED | permission missing: {measurement.get('missing_permission', 'instagram_manage_insights')} required for media insights")
    elif measurement["status"] != "ok":
        print("HEALTH: DEGRADED | measurement is cold; advanced learning must remain conservative")
    else:
        print("HEALTH: OK | measurement is active")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
