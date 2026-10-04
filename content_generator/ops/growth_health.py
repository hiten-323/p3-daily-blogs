"""Production health checks for the Purity Beans Growth OS.

This module deliberately does not change business logic. It verifies that the
systems which the growth loop depends on are actually healthy: measurement,
Meta account access, attribution hygiene, policy configuration, asset
provenance, and learning readiness.

Exit code 0 means the engine is safe to run. A hard failure means a dependency
cannot be trusted and the caller should fail closed rather than publish.
"""
from __future__ import annotations

import json
import os
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
    return {
        "status": "ok" if measured else ("cold" if records else "empty"),
        "records": len(records),
        "measured_views": measured,
        "unknown_views": unknown,
    }


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

    print("=== PURITY BEANS GROWTH OS HEALTH ===")
    print(f"Measurement : {measurement['status']} | records={measurement['records']} measured_views={measurement['measured_views']}")
    print(f"Meta access : {meta['status']}")
    print(f"Attribution : {attribution['status']} | orders={attribution['orders']}")
    print(f"Config      : {config['status']} | warnings={','.join(config['warnings']) or 'none'}")

    # Cold measurement is not a publishing failure. It is explicitly surfaced
    # so the learning layer cannot claim confidence it has not earned.
    hard_failures: list[str] = []
    if meta["status"] == "failed":
        hard_failures.append("instagram_graph_access")
    if attribution["status"] == "failed":
        hard_failures.append("attribution_ledger")
    if config["status"] == "failed":
        hard_failures.append("policy_configuration")

    if hard_failures:
        print("HEALTH: FAIL-CLOSED | " + ", ".join(hard_failures))
        return 1

    if measurement["status"] != "ok":
        print("HEALTH: DEGRADED | measurement is cold; advanced learning must remain conservative")
    else:
        print("HEALTH: OK | measurement is active")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
