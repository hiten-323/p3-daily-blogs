"""
Psychology governance + claim verification.

Each check guards a path by which governed generation could silently become
ungoverned, or an unverifiable claim could reach a live post.
Run: python tests/test_psychology_governance.py
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
    from content_generator.core.editorial_engine import (
        resolve_psychology_governance, get_valid_assets, EditorialRejectException,
    )
    from content_generator.core.brand_validator import validate_asset
    from content_generator.core.claim_verifier import verify_claims, verify_piece
    from content_generator.scheduler.daily import _strip_unsupported_stats as strip
    from content_generator.core.coffee_psychology import get_frame

    # 1. "default" is not a frame. get_frame returns None for it, so treating it
    #    as a fallback silently removed governance.
    print("\nPlaceholder frames are rejected, not defaulted:")
    check("get_frame('default') is None", get_frame("default") is None)
    for bad in ("default", "none", "unknown", "bogus_frame"):
        try:
            resolve_psychology_governance({"psychology_frame": bad})
            check(f"{bad!r} rejected", False, "did not raise")
        except EditorialRejectException:
            check(f"{bad!r} rejected", True)

    # 2. A bogus frame makes NOTHING publishable — governance failure must not
    #    degrade to ungoverned publishing.
    print("\nUngoverned content is unpublishable:")
    check("bad frame -> no valid assets",
          get_valid_assets({"psychology_frame": "default",
                            "carousel": {"title": "x"}}) == [])
    check("real frame resolves governance",
          isinstance(resolve_psychology_governance({"psychology_frame": "revelation"}), dict))
    check("no frame at all -> None (legacy assets)",
          resolve_psychology_governance({}) is None)

    # 3. require_claim_verification must actually verify. It was `pass`.
    print("\nrequire_claim_verification enforces:")
    dirty = {"caption": "Most big brands add up to 50 percent chicory root filler.",
             "hook": "Read the label"}
    clean = {"caption": "Purity Beans is pure coffee, zero chicory. Shop at p3online.in",
             "hook": "Read the label before you buy"}
    ok_dirty, errs = validate_asset("carousel", dirty,
                                    {"require_claim_verification": True})
    check("unverified claim rejected", ok_dirty is False, str(errs)[:80])
    check("rejection names the claim", any("statistic" in e or "competitor" in e
                                           for e in (errs or [])), str(errs)[:80])
    # Governance must not be the thing that rejects clean copy: with the same
    # piece, the failure reason (if any) must come from ordinary brand rules,
    # never from claim verification.
    _, clean_errs = validate_asset("carousel", clean, {"require_claim_verification": True})
    check("clean copy not rejected BY claim verification",
          not any("unverified" in e for e in (clean_errs or [])), str(clean_errs)[:90])

    # 4. High risk still blocks outright.
    blocked, errs = validate_asset("carousel", clean, {"require_manual_review": True})
    check("require_manual_review blocks", blocked is False)

    # 5. The claim classes that actually reached production.
    print("\nClaim verifier catches the live-incident classes:")
    for text, kind in (
        ("Most big brands add up to 50 percent chicory root filler.", "competitor_claim"),
        ("Many popular brands add up to fifty percent chicory root fillers.", "competitor_claim"),
        ("Most people don't know their coffee has 40% chicory.", "statistic"),
        ("Try your first cup free today.", "offer"),
        ("Our coffee lowers cholesterol.", "health_claim"),
        ("India's cleanest coffee.", "superlative"),
    ):
        found = verify_claims(text)
        check(f"flags {kind}: {text[:40]!r}",
              any(f["type"] == kind for f in found),
              str([f["type"] for f in found]))

    # 6. ...and does not flag legitimate brand copy.
    print("\nVerified brand facts are not flagged:")
    for text in ("Purity Beans is pure coffee, zero chicory.",
                 "Read the label before you buy your next jar.",
                 "Freeze dried for a richer aroma.",
                 "Shop now at p3online.in"):
        check(f"clean: {text[:42]!r}", verify_claims(text) == [],
              str(verify_claims(text)))

    # 7. The scrubber must catch word-form percentages. It required the % symbol,
    #    so "50 percent" and "fifty percent" both survived — the same claim class
    #    that published as "40% CHICORY FILLER".
    print("\nScrubber catches word-form and competitor claims:")
    for text in ("Most big brands add up to 50 percent chicory root filler.",
                 "Many popular brands add up to fifty percent chicory root fillers.",
                 "Competitors cut their blends with nearly half chicory.",
                 "Other brands hide chicory in their blends."):
        check(f"stripped: {text[:44]!r}", strip(text).strip() == "", repr(strip(text)))
    for text in ("Purity Beans is pure coffee, zero chicory.",
                 "Purity Beans - 100 percent coffee, nothing added."):
        check(f"kept: {text[:44]!r}", strip(text).strip() == text.strip(), repr(strip(text)))

    # 8. Whole-asset verification reaches nested slide copy.
    print("\nVerification reaches nested slide copy:")
    piece = {"caption": "clean", "slides": [
        {"heading": "Read the label", "body": "Most brands add fifty percent chicory."}]}
    check("nested slide claim found", any(f["type"] in ("statistic", "competitor_claim")
                                          for f in verify_piece(piece)),
          str(verify_piece(piece)))

    print(f"\n{'GOVERNANCE BROKEN' if failures else 'psychology governance enforced'} "
          f"({len(failures)} failure(s))")
    return 1 if failures else 0


def test_main():
    """Let pytest collect this suite too — one runner sees both styles."""
    rc = main()
    assert rc in (0, None), f"suite reported failures (rc={rc})"


if __name__ == "__main__":
    raise SystemExit(main())
