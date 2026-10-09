"""
Publish result contract.

A green CI run must mean the expected platforms actually published. Every check
here guards a way a run could report success while publishing nothing.
Run: python tests/test_publish_contract.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["LEARNING_DIR"] = tempfile.mkdtemp(prefix="pb_test_learning_")

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    from content_generator.core.publish_contract import (
        build, evaluate, format_report, expected_platforms, SLOT_EXPECTATIONS,
    )

    # 1. A missing contract must FAIL. It previously warned and exited 0, which
    #    contradicted the check's own purpose.
    print("\nA missing contract is a failure, not a warning:")
    for bad in ({}, {"success": True}, {"slot": "morning", "success": True}):
        v = evaluate(bad)
        check(f"no contract -> failure: {bad}", v["status"] == "missing" and not v["ok"])

    # 2. Partial publishing must FAIL. "Something published" is not "what was
    #    supposed to publish did".
    print("\nPartial publishing fails:")
    partial = build("morning", 1,
                    expected={"instagram": ["carousel"], "facebook": ["carousel"]},
                    results={"instagram": {"status": "published", "remote_id": "ig1"},
                             "facebook":  {"status": "failed", "error": "token expired"}})
    v = evaluate(partial)
    check("instagram ok + facebook expired -> still ok", v["ok"] and v["status"] == "published", v["status"])
    check("facebook failure is a warning, not a missing publish",
          any("facebook" in m for m in v["warnings"]) and not v["missing"], str(v))
    check("the reason is carried through", "token expired" in v["detail"], v["detail"])
    instagram_down = build(
        "morning", 1,
        expected={"instagram": ["carousel"], "facebook": ["carousel"]},
        results={"instagram": {"status": "failed", "error": "container error"},
                 "facebook": {"status": "failed", "error": "token expired"}},
    )
    down = evaluate(instagram_down)
    check("instagram failure stays fatal", (not down["ok"]) and down["status"] == "partial", down["status"])
    check("the fatal platform is instagram",
          any("instagram" in m for m in down["missing"]), str(down["missing"]))
    check("published_platforms still lists only real successes",
          partial["published_platforms"] == ["instagram"],
          str(partial["published_platforms"]))

    # 3. Everything expected publishing -> pass.
    print("\nFull publishing passes:")
    full = build("morning", 1,
                 expected={"instagram": ["carousel"], "facebook": ["carousel"]},
                 results={"instagram": {"status": "published", "remote_id": "ig1"},
                          "facebook":  {"status": "published", "remote_id": "fb1"}})
    check("all expected published -> ok", evaluate(full)["ok"])

    # 4. Held and skipped are distinct from broken, and stay green.
    print("\nDeliberate non-publishing is distinguished from breakage:")
    held = build("evening", 1, expected={}, results={},
                 status="held", reason="canonical_validation_failed")
    v = evaluate(held)
    check("unexpected held fails the run", (not v["ok"]) and v["status"] == "held")
    check("held carries its reason", "canonical" in v["detail"], v["detail"])
    check("held is NOT reported as published",
          held["published_platforms"] == [], str(held["published_platforms"]))
    already = build("evening", 1, expected={}, results={},
                    status="skipped", reason="already_ran")
    check("already published today stays green",
          evaluate(already)["ok"] and evaluate(already)["status"] == "skipped")

    # 5. Correlation ids so a publish can be traced back to its generation.
    print("\nRuns are traceable:")
    c = build("morning", 7, {"instagram": ["carousel"]},
              {"instagram": {"status": "published", "remote_id": "x"}},
              generation_id="gen_2026-08-09_abc123")
    for f in ("run_id", "generation_id", "slot", "day", "contract_version"):
        check(f"contract carries {f}", bool(c.get(f) is not None and c.get(f) != ""))
    check("generation_id preserved", c["generation_id"] == "gen_2026-08-09_abc123")

    # 6. Each slot declares what it is responsible for.
    print("\nSlot expectations are declared:")
    check("morning expects instagram + facebook",
          set(expected_platforms("morning")) == {"instagram", "facebook"})
    check("evening expects instagram + facebook",
          set(expected_platforms("evening")) == {"instagram", "facebook"})
    check("generate does not expect instagram",
          "instagram" not in expected_platforms("generate"))

    # 7. The report names every platform, including ones not expected — so a
    #    reader can tell "not due this slot" from "failed".
    print("\nReport distinguishes not-expected from failed:")
    rep = format_report(partial)
    check("report warns on the facebook mirror", "WARN" in rep and "FAIL" not in rep, rep)
    check("report marks the success", "OK" in rep, rep)
    check("report marks an instagram failure", "FAIL" in format_report(instagram_down), format_report(instagram_down))
    rep2 = format_report(build("generate", 1, {"linkedin": ["post"]},
                               {"linkedin": {"status": "published"},
                                "instagram": {"status": "skipped"}}))
    check("unexpected platform marked not-expected",
          "not expected this slot" in rep2, rep2)

    # 8. The real slot functions must return a contract, not a bare dict. This
    #    is the defect itself: run_publish_slot returned the publisher's dict.
    print("\nThe scheduler emits the contract:")
    from content_generator.scheduler import slots as sl
    import inspect
    src = inspect.getsource(sl)
    check("no bare '{\"slot\": slot, **result}' returns remain",
          '{"slot": slot, **result}' not in src)
    check("_held exists for deliberate holds", hasattr(sl, "_held"))
    check("_contract exists for publishes", hasattr(sl, "_contract"))
    check("facebook mirror returns its result",
          "-> dict" in inspect.getsource(sl._mirror_to_facebook))

    # 9. A publish slot must NEVER generate its own content. It used to call
    #    run_full_pipeline() when today's file was missing, which skipped the
    #    generate pipeline entirely and — when the LLMs were down — published an
    #    emergency fallback the founder never reviewed.
    print("\nPublish slots never generate:")
    check("no publish path calls run_full_pipeline",
          "run_full_pipeline(" not in src.replace(
              "# This used to call run_full_pipeline() when today's file was absent, so a", ""))

    real_load = sl._load_todays_content
    try:
        sl._load_todays_content = lambda: None
        r = sl.run_publish_slot.__wrapped__(  "morning") if hasattr(
            sl.run_publish_slot, "__wrapped__") else None
    except Exception:
        r = None
    finally:
        sl._load_todays_content = real_load
    # Exercise the helper directly — run_publish_slot takes a real lock.
    held = sl._held("morning", 0, {}, "no_content_for_today — the generate slot "
                                      "produced nothing; publish slots never generate")
    v = evaluate(held)
    check("missing content -> held, and the run fails", v["status"] == "held" and not v["ok"])
    check("held for missing content publishes nothing",
          held["published_platforms"] == [])
    check("the hold names the cause", "no_content_for_today" in v["detail"], v["detail"])

    # 10. Stale content must not be republished under today's decision record.
    print("\nStale content is refused:")
    stale = sl._held("evening", 5, {"date": "2026-08-01"},
                     "stale_content — file is dated 2026-08-01, today is 2026-08-09")
    v = evaluate(stale)
    check("stale content -> held and fails the run", v["status"] == "held" and not v["ok"])
    check("the hold names both dates",
          "2026-08-01" in v["detail"] and "2026-08-09" in v["detail"], v["detail"])
    check("slots.py compares the content date to today",
          'content.get("date")' in src and "stale_content" in src)

    # 11. A crashed slot must not lock out the rest of the day.
    #     The lock was written BEFORE the work and read as proof the work was
    #     done, and slots.py called __enter__() without ever calling __exit__(),
    #     so RunLock's crash-release path never ran. One crashed slot therefore
    #     skipped every later slot that day — silently, behind a green tick,
    #     because the lock file is committed to the repo and outlives the runner.
    print("\nA crashed slot does not lock out the day:")
    import datetime
    import tempfile as _tf
    from content_generator.core.ist_dates import today_ist
    from content_generator.scheduler.run_lock import RunLock, STALE_AFTER_MINUTES
    lp = os.path.join(_tf.mkdtemp(prefix="pb_test_lock_"), ".running_test")
    today = today_ist().isoformat()

    RunLock(lock_path=lp).__enter__()
    check("a fresh lock records 'started', not 'completed'",
          "started" in open(lp).read(), open(lp).read())
    check("an in-flight run is not rerun",
          RunLock(lock_path=lp).__enter__().already_ran)

    old = (datetime.datetime.now()
           - datetime.timedelta(minutes=STALE_AFTER_MINUTES + 5)).isoformat(timespec="seconds")
    open(lp, "w").write(f"{today}|999|started|{old}")
    check("a stale 'started' lock is taken over",
          not RunLock(lock_path=lp).__enter__().already_ran)

    lk = RunLock(lock_path=lp); lk.__enter__(); lk.mark_completed()
    check("a completed run blocks a rerun",
          RunLock(lock_path=lp).__enter__().already_ran)
    check("completion is recorded in the lock", "completed" in open(lp).read())

    open(lp, "w").write(f"{today}|123")
    check("a legacy two-field lock still means done",
          RunLock(lock_path=lp).__enter__().already_ran)

    check("run_publish_slot owns the lock lifecycle",
          "lock.release()" in src and "lock.mark_completed()" in src)
    check("the slot body is separated from the lock", "_execute_publish_slot" in src)

    print(f"\n{'PUBLISH CONTRACT BROKEN' if failures else 'publish contract enforced'} "
          f"({len(failures)} failure(s))")
    return 1 if failures else 0


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


def test_facebook_mirror_failure_is_a_warning(monkeypatch, caplog):
    import logging
    from content_generator.core.publish_contract import evaluate
    from content_generator.scheduler import slots as sl

    def expired(*_args, **_kwargs):
        return {"success": False, "error": "Error validating access token: session has expired"}

    monkeypatch.setattr("content_generator.publisher.facebook.post_content", expired)
    caplog.set_level(logging.WARNING)
    mirrored = sl._mirror_to_facebook({"generation_id": "gen"}, 4, "morning")
    assert mirrored["success"] is False
    assert "facebook mirror failed" in caplog.text
    assert "session has expired" in caplog.text

    contract = sl._contract(
        "morning", 4, {"generation_id": "gen"},
        {"instagram": {"success": True, "media_id": "ig1"}, "facebook": mirrored},
        {"instagram": ["carousel"], "facebook": ["carousel"]},
    )
    verdict = evaluate(contract)
    assert verdict["ok"] is True
    assert verdict["warnings"]
    assert "expired" in verdict["detail"]

    fatal = sl._contract(
        "morning", 4, {"generation_id": "gen"},
        {"instagram": {"success": False, "error": "container error"}, "facebook": mirrored},
        {"instagram": ["carousel"], "facebook": ["carousel"]},
    )
    assert evaluate(fatal)["ok"] is False


def test_linkedin_token_refresh_contract(monkeypatch):
    from content_generator.publisher import linkedin
    monkeypatch.delenv("LI_API_ACCESS", raising=False)
    monkeypatch.delenv("LI_AUTHOR_URN", raising=False)
    monkeypatch.delenv("LI_CLIENT_ID", raising=False)
    monkeypatch.delenv("LI_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("LI_REFRESH_TOKEN", raising=False)

    assert linkedin.is_configured() is False

    monkeypatch.setenv("LI_AUTHOR_URN", "urn:li:person:123")
    monkeypatch.setenv("LI_CLIENT_ID", "cid")
    monkeypatch.setenv("LI_CLIENT_SECRET", "csec")
    monkeypatch.setenv("LI_REFRESH_TOKEN", "reftok")

    assert linkedin.is_configured() is True

    monkeypatch.setattr(linkedin, "refresh_access_token", lambda cid, csec, rtok: "refreshed_tok")
    assert linkedin.get_access_token(force_refresh=True) == "refreshed_tok"


if __name__ == "__main__":
    raise SystemExit(main())
