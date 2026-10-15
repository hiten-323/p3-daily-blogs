"""Retry due, explicitly retryable publishing failures without duplicating prior successes."""
from __future__ import annotations

import datetime
import json
import logging
import os
import sys
from pathlib import Path

from content_generator.core.ist_dates import content_matches_today
from content_generator.publisher.publishing_ledger import due_retry_groups, records_for_today

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _load_content(date_iso: str) -> tuple[dict | None, str]:
    path = Path("output") / f"content_{date_iso}.json"
    if not path.exists():
        return None, f"missing content file {path}"
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, f"content file cannot be parsed: {exc}"
    fresh, why = content_matches_today(content, today=datetime.date.fromisoformat(date_iso))
    if not fresh:
        return None, why
    from content_generator.core.draft_purge import purge_banned_drafts
    purge_banned_drafts(content)
    return content, ""


def main() -> int:
    groups = due_retry_groups()
    if not groups:
        today_records = records_for_today()
        counts = {}
        for record in today_records:
            status = str(record.get("status", "UNKNOWN"))
            counts[status] = counts.get(status, 0) + 1
        log.info("No due retries. Ledger states: %s", counts)
        return 0

    failures = []
    for item in groups:
        slot = item["slot"]
        date = item["content_date"]
        content, why = _load_content(date)
        if content is None:
            log.error("Refusing retry for %s %s: %s", date, slot, why)
            failures.append(f"{date} {slot}: {why}")
            continue
        day = int(content.get("day_number") or 0)
        log.warning("Retrying due failed platform(s) for slot=%s date=%s", slot, date)
        if slot == "generate":
            from content_generator.publisher.dispatcher import publish_all
            result = publish_all(content, day_number=day)
            for platform, outcome in result.items():
                if platform in ("summary", "published_platforms", "timestamp") or not isinstance(outcome, dict):
                    continue
                if not outcome.get("success") and not outcome.get("skipped") and not outcome.get("held"):
                    failures.append(f"{platform}: {outcome.get('error') or 'not published'}")
            log.info("Generate-slot recovery: %s", result.get("summary", "completed"))
        elif slot in ("morning", "evening"):
            from content_generator.scheduler.slots import run_publish_slot
            from content_generator.core.publish_contract import evaluate, format_report
            result = run_publish_slot(slot, force_retry=True, on_date=datetime.date.fromisoformat(date))
            log.info("Slot recovery result:\n%s", format_report(result))
            verdict = evaluate(result)
            if not verdict.get("ok"):
                failures.append(f"{slot}: {verdict.get('detail', verdict.get('status'))}")
        else:
            log.error("Unknown ledger slot %s; skipping", slot)
            failures.append(f"{slot}: unknown slot")

    if failures:
        message = "PURITY BEANS PUBLISH RECOVERY INCOMPLETE\n" + "\n".join(failures)
        log.error("RECOVERY INCOMPLETE: %s", "; ".join(failures))
        try:
            from content_generator.scheduler.watchdog import alert_failure
            alert_failure(message)
        except Exception as exc:
            log.error("Failure alert could not be delivered: %s", exc)
        return 1
    log.info("Due publishing retries completed. Ledger remains authoritative; unverified and ambiguous outcomes are not reported as verified live.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
