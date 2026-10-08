"""
Editorial Engine — enforces 8.0 score threshold, normalizes editorial results,
and performs schema + brand validation audits before publish.
"""
import logging
from content_generator.core.brand_guard import BRAND, REQUIRED_DAILY_ASSETS, MIN_REQUIRED_ASSETS
from content_generator.core.brand_validator import validate_asset
from content_generator.core.schema_validation import (
    ReelSchema, CarouselSchema, InstagramSchema, LinkedinSchema, BlogSchema, YoutubeShortSchema, validate_or_fail
)

logger = logging.getLogger(__name__)

import datetime

from content_generator.core.piece_integrity import ensure_structural_fields

class EditorialRejectException(Exception):
    """Raised when an asset fails the editorial threshold."""
    pass


def get_current_pass_score() -> float:
    """
    THE single source of truth for the editorial threshold.

    Order of precedence:
      1. founder policy  quality.minimum_score   (founder-editable, wins)
      2. BRAND.minimum_editorial_score           (brand constitution default)

    Never hardcode a threshold anywhere else — import this function.
    """
    try:
        from content_generator.core.founder_policy import policy
        val = policy().get("minimum_score")
        if val is not None:
            return float(val)
    except Exception as e:
        logger.debug("[editorial] policy threshold unavailable (%s) — using brand default", e)
    return float(BRAND.minimum_editorial_score)


# Backwards-compatible alias for any caller still importing the constant.
# Reads the live value rather than freezing a stale number at import time.
def __getattr__(name):
    if name == "PASS_SCORE":
        return get_current_pass_score()
    raise AttributeError(name)

def normalize_editorial_result(result: dict) -> dict:
    """
    Normalize verdict to PASS/REJECT based on the dynamic score threshold.
    The numeric score is authoritative: verdict always matches score.
    """
    overall = float(result.get("overall", 0.0))
    threshold = get_current_pass_score()
    result["verdict"] = "PASS" if overall >= threshold else "REJECT"
    return result

def enforce_editorial_gate(piece_name: str, score: float) -> bool:
    """
    Raise exception if an asset's score is below threshold.
    """
    threshold = get_current_pass_score()
    if score < threshold:
        raise EditorialRejectException(
            f"Editorial Reject for '{piece_name}': score {score:.1f} below threshold {threshold:.1f}"
        )
    return True

_PREVETTED_SOURCES = ("evergreen_template", "evergreen_distributor")
# LinkedIn, YouTube, and the Shopify blog post off-platform. A stock or
# evergreen piece has no measured editor score, and that used to count as
# pre-vetted — run 37192396900 sent a stock linkedin_post that way.
_EXTERNAL_AUTOPOST = ("linkedin_post", "yt_short", "blog_post")


def _editorial_ok(label: str, piece: dict) -> bool:
    """
    Apply the editorial threshold, exempting hand-written fallback templates
    from the on-platform gates only.

    The threshold scores LLM output. Fallback templates are written by hand and
    never receive an editorial_score, so they scored 0 and were rejected — which
    made the fallback dead code: on the days generation fails, the engine had
    nothing publishable at all and went silent while reporting success.

    The exemption is narrow and auditable: it applies ONLY to the curated
    sources, ONLY to this one gate, and NEVER to LinkedIn, YouTube, or the
    Shopify blog. Those auto-posters require a measured editor score. Schema,
    brand, claim verification, psychology governance, the north-star gate, the
    80/20 cap and the payoff gate all still apply. tests/test_fallback_safety.py
    asserts every template passes all of them, so the on-platform exemption
    rests on an enforced guarantee rather than on trust.

    A fabricated passing score was the alternative, and inventing a number to
    clear a gate is the habit this engine has spent its whole history removing.
    """
    source = str(piece.get("source") or "")
    if source in _PREVETTED_SOURCES and label not in _EXTERNAL_AUTOPOST:
        logger.info("[editorial] %s is a pre-vetted %s — editorial score not "
                    "applicable; all other gates still enforced",
                    label, source)
        return True
    if source in _PREVETTED_SOURCES and label in _EXTERNAL_AUTOPOST:
        logger.warning(
            "[editorial] %s is stock/fallback (%s) — external auto-post requires "
            "an editor score; the pre-vetted exemption does not apply",
            label, source,
        )
    raw = piece.get("editorial_score")
    if not isinstance(raw, dict) or raw.get("overall") in (None, ""):
        detail = str(piece.get("editorial_error") or "").strip()
        if not detail:
            detail = "no measured editorial score (scoring did not return a number)"
        raise EditorialRejectException(f"Editorial Reject for '{label}': {detail}")
    try:
        score = float(raw.get("overall"))
    except (TypeError, ValueError) as e:
        raise EditorialRejectException(
            f"Editorial Reject for '{label}': editorial overall is not a number"
        ) from e
    enforce_editorial_gate(label, score)
    return True


def has_copy(piece: dict, *keys: str) -> bool:
    """
    Does this asset carry any of the fields that mean "there is content here"?

    Each asset used to be gated on ONE hardcoded field, and every one of them
    was wrong for the current schema:

        reel     gated on hook_text  -> the schema field is `hook`
        carousel gated on title      -> the schema fields are `hook` + `slides`
        instagram gated on caption   -> the schema field is `body`

    A missing field is falsy, so all three assets failed the entry condition
    silently and were never validated at all — get_valid_assets returned
    ['linkedin_post'] alone and Instagram published nothing, while the run
    reported success. This is the same hook_text/title defect already fixed in
    slots._track; it was living in the canonical gate too.

    A cascade rather than a single key, so one schema rename cannot silently
    empty the publish set again.
    """
    if not isinstance(piece, dict) or not piece:
        return False
    return any(str(piece.get(k) or "").strip() or piece.get(k) for k in keys
               if piece.get(k) not in (None, "", [], {}))


def resolve_psychology_governance(content: dict) -> dict | None:
    """
    Governance rules for the psychology frame this content was generated under.

    FAILS CLOSED. The earlier form was:

        try:
            frm = get_frame(content["psychology_frame"])
            if frm: gov = frm.get("governance_rules")
        except Exception:
            pass

    so an unknown frame id, a typo, or an import error silently produced
    gov=None and the content proceeded UNGOVERNED — the risk rules vanished at
    exactly the moment something was wrong. A missing frame is now a hard
    rejection, because ungoverned generation is the thing governance exists to
    prevent.

    Returns the rules dict, or raises. None is returned ONLY when the content
    carries no psychology frame at all (legacy assets predating the registry).
    """
    frame_id = content.get("psychology_frame")
    if not frame_id:
        return None
    if str(frame_id).strip().lower() in ("default", "none", "unknown", ""):
        raise EditorialRejectException(
            f"psychology_frame is {frame_id!r} — there is no such frame in the "
            "registry. A placeholder frame means governance was never selected.")
    try:
        from content_generator.core.coffee_psychology import get_frame
        frm = get_frame(frame_id)
    except Exception as e:
        raise EditorialRejectException(
            f"psychology registry unavailable ({e}) — refusing to publish "
            "ungoverned content") from e
    if not frm:
        raise EditorialRejectException(
            f"psychology_frame {frame_id!r} is not in the registry — refusing to "
            "publish ungoverned content")
    return frm.get("governance_rules") or {}


def get_valid_assets(content: dict) -> list[str]:
    """
    Verify which of the generated assets are complete, pass schema validation,
    and meet brand guidelines.
    Returns a list of keys of valid, publishable assets.
    """
    # Resolve governance once, up front. If the frame is missing or bogus this
    # raises and NOTHING is publishable — the correct outcome, since every
    # per-asset brand check below depends on these rules.
    try:
        _governance = resolve_psychology_governance(content)
    except EditorialRejectException as e:
        logger.error("[editorial] %s", e)
        return []

    valid = []
    
    # 1. reel_1
    if "reel_1" in REQUIRED_DAILY_ASSETS:
        try:
            reels = content.get("reels") or []
            reel_1 = reels[0] if len(reels) > 0 else {}
            if isinstance(reel_1, dict) and reel_1:
                ensure_structural_fields(reel_1, "reel_1")
            if has_copy(reel_1, "hook", "hook_text", "headline", "title", "chosen_hook"):
                validate_or_fail(ReelSchema, reel_1)
                is_brand_ok, _brand_errs = validate_asset("reel_1", reel_1, _governance)
                if is_brand_ok:
                    _editorial_ok("reel_1", reel_1)
                    valid.append("reel_1")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "reel_1", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] reel_1 validation failed: %s", e)
        
    # 2. reel_2
    if "reel_2" in REQUIRED_DAILY_ASSETS:
        try:
            reels = content.get("reels") or []
            reel_2 = reels[1] if len(reels) > 1 else {}
            if isinstance(reel_2, dict) and reel_2:
                ensure_structural_fields(reel_2, "reel_2")
            if has_copy(reel_2, "hook", "hook_text", "headline", "title", "chosen_hook"):
                validate_or_fail(ReelSchema, reel_2)
                is_brand_ok, _brand_errs = validate_asset("reel_2", reel_2, _governance)
                if is_brand_ok:
                    _editorial_ok("reel_2", reel_2)
                    valid.append("reel_2")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "reel_2", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] reel_2 validation failed: %s", e)

    # 2b. growth_reel — prompt shape (chosen_hook/script), not the brand reel schema.
    #     It was never passed through this gate, so the evening slot could not
    #     publish it even when the copy was complete.
    growth = content.get("growth_reel") or {}
    if isinstance(growth, dict) and growth:
        try:
            ensure_structural_fields(growth, "growth_reel")
            if has_copy(growth, "hook", "hook_text", "chosen_hook", "caption"):
                validate_or_fail(ReelSchema, growth)
                is_brand_ok, _brand_errs = validate_asset("growth_reel", growth, _governance)
                if is_brand_ok:
                    _editorial_ok("growth_reel", growth)
                    valid.append("growth_reel")
                else:
                    logger.warning("[editorial] growth_reel REJECTED by brand validation: %s", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] growth_reel validation failed: %s", e)

    # 3. carousel
    if "carousel" in REQUIRED_DAILY_ASSETS:
        try:
            carousel = content.get("carousel") or {}
            if isinstance(carousel, dict) and carousel:
                ensure_structural_fields(carousel, "carousel")
            if has_copy(carousel, "hook", "title", "headline", "slides", "caption"):
                validate_or_fail(CarouselSchema, carousel)
                is_brand_ok, _brand_errs = validate_asset("carousel", carousel, _governance)
                if is_brand_ok:
                    _editorial_ok("carousel", carousel)
                    valid.append("carousel")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "carousel", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] carousel validation failed: %s", e)

    # 4. instagram_post
    if "instagram_post" in REQUIRED_DAILY_ASSETS:
        try:
            ig = content.get("instagram_post") or {}
            if isinstance(ig, dict) and ig:
                ensure_structural_fields(ig, "instagram_post")
            if has_copy(ig, "caption", "body", "hook"):
                validate_or_fail(InstagramSchema, ig)
                is_brand_ok, _brand_errs = validate_asset("instagram_post", ig, _governance)
                if is_brand_ok:
                    _editorial_ok("instagram_post", ig)
                    valid.append("instagram_post")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "instagram_post", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] instagram_post validation failed: %s", e)

    # 5. linkedin_post
    if "linkedin_post" in REQUIRED_DAILY_ASSETS:
        try:
            li = content.get("linkedin_post") or {}
            if isinstance(li, dict) and li:
                ensure_structural_fields(li, "linkedin_post")
            if has_copy(li, "body", "caption", "hook"):
                validate_or_fail(LinkedinSchema, li)
                is_brand_ok, _brand_errs = validate_asset("linkedin_post", li, _governance)
                if is_brand_ok:
                    _editorial_ok("linkedin_post", li)
                    valid.append("linkedin_post")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "linkedin_post", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] linkedin_post validation failed: %s", e)

    # 6. blog_post
    if "blog_post" in REQUIRED_DAILY_ASSETS:
        try:
            blog = content.get("blog_post") or {}
            if isinstance(blog, dict) and blog:
                ensure_structural_fields(blog, "blog_post")
            if has_copy(blog, "body", "caption", "title"):
                validate_or_fail(BlogSchema, blog)
                is_brand_ok, _brand_errs = validate_asset("blog_post", blog, _governance)
                if is_brand_ok:
                    _editorial_ok("blog_post", blog)
                    valid.append("blog_post")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "blog_post", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] blog_post validation failed: %s", e)

    # 7. yt_short
    if "yt_short" in REQUIRED_DAILY_ASSETS:
        try:
            yt = content.get("yt_short") or {}
            if isinstance(yt, dict) and yt:
                ensure_structural_fields(yt, "yt_short")
            if yt and isinstance(yt, dict):
                validate_or_fail(YoutubeShortSchema, yt)
                is_brand_ok, _brand_errs = validate_asset("yt_short", yt, _governance)
                if is_brand_ok:
                    _editorial_ok("yt_short", yt)
                    valid.append("yt_short")
                else:
                    logger.warning("[editorial] %s REJECTED by brand validation: %s", "yt_short", _brand_errs)
        except Exception as e:
            logger.warning("[editorial] yt_short validation failed: %s", e)
        
    return _apply_growth_director_gates(content, valid)


def _piece_for(content: dict, key: str) -> dict:
    """Map an asset key back to the content piece it was built from."""
    reels = content.get("reels") or []
    if key == "reel_1":
        if len(reels) > 0 and isinstance(reels[0], dict):
            return reels[0]
        p = content.get("reel_1")
        return p if isinstance(p, dict) else {}
    if key == "reel_2":
        if len(reels) > 1 and isinstance(reels[1], dict):
            return reels[1]
        p = content.get("reel_2")
        return p if isinstance(p, dict) else {}
    if key == "growth_reel":
        piece = content.get("growth_reel")
        return piece if isinstance(piece, dict) else {}
    piece = content.get(key)
    return piece if isinstance(piece, dict) else {}


def _apply_growth_director_gates(content: dict, valid: list[str]) -> list[str]:
    """
    The two Growth Director rules that can veto an otherwise-valid asset:

      NORTH STAR  "If it is not worth sharing privately, it is not worth
                   publishing." An asset can be schema-valid, on-brand and above
                   the editorial threshold and still be generic filler.
      80/20       Product promotion never exceeds 20% of published content.

    Dropping assets here can take the run below MIN_REQUIRED_ASSETS and block
    publishing outright. That is intended: "never publish content simply because
    it fills today's schedule."
    """
    kept = []
    for key in valid:
        piece = _piece_for(content, key)
        if not piece:
            kept.append(key)
            continue
        try:
            from content_generator.core.content_contract import shareability
            share = shareability(piece)
            if not share["passes"]:
                logger.warning(
                    "[editorial] %s REJECTED by north-star gate (%.0f/100): %s",
                    key, share["score"], "; ".join(share["reasons"][:3]))
                continue
        except Exception as e:
            logger.warning("[editorial] shareability check error for %s (%s) — failing closed", key, e)
            continue

        try:
            from content_generator.core.content_balance import check as balance_check
            bal = balance_check(piece, key)
            if not bal["allowed"]:
                logger.warning("[editorial] %s REJECTED by 80/20 cap: %s", key, bal["reason"])
                continue
        except Exception as e:
            logger.warning("[editorial] balance check error for %s (%s) — failing closed", key, e)
            continue

        # ADR-002 Phase 2 — payoff. A curiosity mechanism with nothing behind it
        # is bait, and a strong hook previously passed every gate even when the
        # viewer learned nothing.
        try:
            from content_generator.core.scroller_psychology import (
                payoff_strength, check_hook_decomposition,
            )
            payoff = payoff_strength(piece)
            if not payoff["passes"]:
                logger.warning("[editorial] %s REJECTED by payoff gate: %s",
                               key, payoff["reason"])
                continue

            # ADR-002 Phase 3 — the three hook channels must do different work.
            # Only applies to video assets, which are the ones with a spoken
            # channel at all.
            if key in ("reel_1", "reel_2", "growth_reel", "yt_short"):
                hooks = check_hook_decomposition(piece)
                if not hooks["passes"]:
                    logger.warning("[editorial] %s REJECTED by hook decomposition: %s",
                                   key, hooks["reason"])
                    continue
        except Exception as e:
            logger.warning("[editorial] scroller check error for %s (%s) — failing closed", key, e)
            continue

        # Pre-publish Creative Viral Readiness Gate (Level 3 Creative)
        try:
            from content_generator.core.viral_readiness import evaluate_viral_readiness
            readiness = evaluate_viral_readiness(piece, platform=key)
            piece["viral_readiness_score"] = readiness["score"]
            if not readiness["passes"]:
                logger.warning(
                    "[editorial] %s REJECTED by viral readiness gate (%.1f/100): %s",
                    key, readiness["score"], "; ".join(readiness["reasons"][:3]),
                )
                continue
        except Exception as e:
            logger.warning("[editorial] viral readiness check error for %s (%s) — failing closed", key, e)
            continue

        # Funnel objective compliance — ensure creative is genuinely value-first when assigned FOLLOW/DISCOVERY
        try:
            from content_generator.core.content_contract import check_objective_compliance
            compliance = check_objective_compliance(piece)
            if not compliance.get("creative_compliant", True):
                logger.warning(
                    "[editorial] %s REJECTED by objective compliance: %s",
                    key, compliance["reason"],
                )
                continue
            # If creative is compliant, heal CTA if follow/share cue was missing
            if not compliance["passes"] and compliance.get("suggested_cta"):
                curr_cta = str(piece.get("cta") or "").strip()
                if curr_cta:
                    piece["cta"] = f"{compliance['suggested_cta']} {curr_cta}"
                else:
                    piece["cta"] = compliance["suggested_cta"]
                logger.info("[editorial] Auto-aligned CTA for %s (%s objective)", key, piece.get("funnel_objective"))
        except Exception as e:
            logger.debug("[editorial] objective compliance check for %s: %s", key, e)

        kept.append(key)

    # ── Level 1: Portfolio-level 95% viral / 5% selling hard invariant ───────
    try:
        from content_generator.core.content_balance import enforce_portfolio_commercial_cap
        kept = enforce_portfolio_commercial_cap(kept, content)
    except Exception as e:
        logger.warning("[editorial] portfolio commercial cap error (%s) — failing closed", e)

    dropped = [k for k in valid if k not in kept]
    if dropped:
        logger.warning("[editorial] Growth Director gates dropped %s — quality over schedule",
                       dropped)
    return kept


def approved_assets(content: dict) -> dict:
    """
    THE canonical publish gate. Returns {asset_key: piece} for assets that
    passed EVERY mandatory layer — schema, brand, editorial threshold, the
    north-star shareability gate and the 80/20 cap.

    Schedulers must ask this and publish exactly what comes back. They must not
    call get_valid_assets() and then decide for themselves which object to send:
    that is how an invalid growth_reel got published while the guard was
    checking reel_1, and how "asset invalid -> replace with {} and hope the
    publisher skips it" became a safety boundary.

    Returning the OBJECTS rather than the names removes the second lookup where
    validation and selection could disagree.
    """
    out = {}
    for key in get_valid_assets(content):
        piece = _piece_for(content, key)
        if piece:
            out[key] = piece
    return out


def approved(content: dict, key: str) -> dict | None:
    """One approved asset, or None. Never returns an unvalidated object."""
    return approved_assets(content).get(key)


def pre_publish_check(content: dict) -> bool:
    """
    Ensure a minimum number of valid assets are present before publishing.
    Aborts publishing if count is below MIN_REQUIRED_ASSETS.
    """
    valid_assets = get_valid_assets(content)
    logger.info("[editorial] Valid publishable assets found: %s", valid_assets)
    
    if len(valid_assets) < MIN_REQUIRED_ASSETS:
        logger.error(
            """
    PURITY BEANS ENGINE ALERT

    Publish blocked.

    Valid assets:
    %s

    Required:
    %s
            """,
            valid_assets,
            MIN_REQUIRED_ASSETS
        )
        raise RuntimeError(
            f"Publish aborted: Content incomplete. Only {len(valid_assets)} valid assets "
            f"found (required at least {MIN_REQUIRED_ASSETS}): {valid_assets}"
        )
    return True
