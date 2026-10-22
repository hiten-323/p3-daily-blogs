"""
Measurement integrity — the learning loop is only as honest as its inputs.

Every check here exists because the failure it guards silently emptied the
learning log for 50 consecutive posts. Run: python tests/test_measurement_integrity.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Redirect every learning-data write to a throwaway directory BEFORE importing
# anything from content_generator — those modules read LEARNING_DIR at import
# time. Without this, calling _track() below appends a fake row to the real
# output/learning/content_balance.json, CI commits it in the persist step, and
# the 80/20 cap starts rating the account on posts that were never published.
_REAL_LEARNING_DIR = os.path.join("output", "learning")
os.environ["LEARNING_DIR"] = tempfile.mkdtemp(prefix="pb_test_learning_")

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    from content_generator.analytics import insights_fetcher as ins
    from content_generator.scheduler.slots import _track, _first

    original = ins._graph_get

    # 1. A failed insights call must record NOTHING. Returning zeros here is what
    #    wrote "reached nobody" onto 50 posts that were never actually measured.
    print("\nFailed fetch is never recorded as zero:")
    try:
        ins._graph_get = lambda path, params: (
            {"like_count": 3, "comments_count": 1, "media_product_type": "FEED"}
            if "insights" not in path else None)
        check("insights failure -> None", ins._fetch_media_insights("m1") is None)

        # 2. ...but a genuine zero, reported by the API, must be preserved.
        def _genuine_zero(path, params):
            if "insights" not in path:
                return {"like_count": 0, "comments_count": 0, "media_product_type": "FEED"}
            return {"data": [{"name": "reach", "values": [{"value": 0}]},
                             {"name": "saved", "values": [{"value": 0}]}]}
        ins._graph_get = _genuine_zero
        m = ins._fetch_media_insights("m2")
        check("measured zero -> recorded", m is not None and m.get("reach") == 0, str(m))

        # 3. Real numbers survive intact.
        def _real(path, params):
            if "insights" not in path:
                return {"like_count": 12, "comments_count": 4, "media_product_type": "FEED"}
            return {"data": [{"name": "reach", "values": [{"value": 840}]},
                             {"name": "saved", "values": [{"value": 19}]},
                             {"name": "shares", "values": [{"value": 7}]}]}
        ins._graph_get = _real
        m = ins._fetch_media_insights("m3")
        check("real metrics preserved",
              m and m["reach"] == 840 and m["saves"] == 19 and m["shares"] == 7 and m["likes"] == 12,
              str(m))
    finally:
        ins._graph_get = original

    # 4. The tracked hook must come off the real schema field. `hook_text` and
    #    `title` exist on neither carousels nor reels — reading them is what made
    #    every record's hook an empty string.
    print("\nHook and format are read from the real schema:")
    carousel = {"type": "carousel", "hook": "3 signs your coffee is not pure",
                "objective": "DISCOVERY", "slides": [], "caption": "..."}
    reel = {"type": "reel", "hook": "Read the label before you buy",
            "angle": "contrarian", "caption": "..."}
    check("carousel hook found", _first(carousel, "hook", "hook_text", "headline", "title")
          == "3 signs your coffee is not pure")
    check("reel hook found", _first(reel, "hook", "hook_text", "headline", "title")
          == "Read the label before you buy")
    check("carousel format is 'carousel'", (_first(carousel, "type") or "morning") == "carousel")
    check("reel format is 'reel'", (_first(reel, "type") or "evening") == "reel")
    check("empty piece falls back to slot", (_first({}, "type") or "morning") == "morning")

    captured = {}

    def _fake_track(**kw):
        captured.update(kw)

    tracker = sys.modules["content_generator.analytics.insights_fetcher"]
    original_track = tracker.track_published_post
    tracker.track_published_post = _fake_track
    try:
        _track({"success": True, "media_id": "abc"}, {"day_number": 7}, "morning", carousel)
        check("_track passes real hook", captured.get("hook") == "3 signs your coffee is not pure",
              str(captured.get("hook")))
        check("_track passes real format", captured.get("format_used") == "carousel",
              str(captured.get("format_used")))
    finally:
        tracker.track_published_post = original_track

    # 5. The live log, REPORTED not asserted.
    #
    #    This suite runs in the CI pre-publish gate, so anything it fails blocks
    #    the whole pipeline from publishing. That is right for code defects and
    #    wrong for observations about production data, which drifts by nature.
    #
    #    The concrete hazard: a post that genuinely reached zero people is a
    #    real measurement, but `reach or views` reads falsy, so it would have
    #    been counted as an unmeasured row — failing the gate and stopping the
    #    account from publishing because one post did badly. A data-quality
    #    warning must never become an outage.
    #
    #    The behavioural guarantees above (a failed fetch records nothing, a
    #    measured zero is preserved) are the code contract and stay blocking.
    print("\nLive performance log — reported, not gating:")
    path = os.path.join(_REAL_LEARNING_DIR, "performance_log.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        unmeasured = [r for r in rows
                      if (r.get("metrics") or {}).get("reach") is None
                      and (r.get("metrics") or {}).get("views") is None]
        hookless = [r for r in rows if not str(r.get("hook", "")).strip()]
        print(f"  INFO  {len(rows)} row(s); {len(unmeasured)} with no reach/views "
              f"key at all; {len(hookless)} with no hook")
        if unmeasured or hookless:
            print("  INFO  these weaken learning but are not a code defect — "
                  "not failing the publish gate over them")

    print(f"\n{'MEASUREMENT INTEGRITY BROKEN' if failures else 'measurement integrity OK'} "
          f"({len(failures)} failure(s))")
    return 1 if failures else 0


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


if __name__ == "__main__":
    raise SystemExit(main())
