"""Enforced growth-engine gate. A score never overrides a brand, claim, or schema fail."""
from __future__ import annotations

import os
import re

from content_generator.prompts.growth_engine.plans import (
    BANNED_OPENERS,
    LABEL_PLATFORM,
    OBJECTIVES,
    asset_plan,
)

DIMENSIONS = (
    "platform_fit",
    "hook",
    "retention",
    "payoff",
    "shareability",
    "saveability",
    "follow_conversion",
    "purchase_relevance",
    "brand_truth",
    "visual_integrity",
    "claim_verification",
    "originality",
    "mobile_readability",
    "cta_clarity",
    "schema",
)

_COPY_FIELDS = (
    "hook", "hook_text", "headline", "title", "body", "caption", "text", "content",
    "sub", "subtext", "introduction", "conclusion", "cta", "primary_cta",
    "comment_trigger", "community_question", "poll_question", "description", "meta_description",
)
_NESTED_KEYS = {"on_screen", "spoken", "heading", "body", "text", "hook", "headline", "cta"}
_VERIFIED_METRICS = {
    "reach", "non_follower_reach", "watch_time_s", "avg_view_duration_s", "completion_rate",
    "shares", "saves", "comments", "profile_visits", "follows_gained", "website_clicks",
    "link_clicks", "orders", "revenue",
}


def whatsapp_enabled() -> bool:
    env = os.getenv("GROWTH_WHATSAPP_ENABLED", "")
    return str(env).strip().lower() in {"1", "true", "yes"}


def _max_retries() -> int:
    try:
        return max(0, int(os.getenv("QUALITY_MAX_REGEN", "3")))
    except (TypeError, ValueError):
        return 3


def _threshold() -> float:
    from content_generator.core.editorial_engine import get_current_pass_score
    return float(get_current_pass_score())


def iter_copy(piece: dict) -> list[tuple[str, str]]:
    """Hook, frames, caption, comment prompt, and CTA, including nested scenes."""
    found: list[tuple[str, str]] = []
    if not isinstance(piece, dict):
        return found
    for key in _COPY_FIELDS:
        value = piece.get(key)
        if isinstance(value, str) and value.strip():
            found.append((key, value.strip()))
    for key, value in piece.items():
        if isinstance(value, dict) and str(key).startswith("story_"):
            for inner, text in value.items():
                if isinstance(text, str) and text.strip():
                    found.append((f"{key}.{inner}", text.strip()))
        if key in {"frames", "scenes", "slides", "script"} and isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, str) and item.strip():
                    found.append((f"{key}[{index}]", item.strip()))
                elif isinstance(item, dict):
                    for inner, text in item.items():
                        if inner in _NESTED_KEYS and isinstance(text, str) and text.strip():
                            found.append((f"{key}[{index}].{inner}", text.strip()))
    return found


def _blob(piece: dict) -> str:
    return "\n".join(text for _, text in iter_copy(piece))


def _native_hook_body(piece: dict) -> tuple[str, str]:
    """Read each format's own fields. A Story headline is a hook. A Short's scenes are the body."""
    hook = _first(piece, "hook", "hook_text", "headline", "title")
    body = _first(piece, "body", "caption", "text", "content", "introduction", "description")
    story = piece.get("story_1") if isinstance(piece.get("story_1"), dict) else {}
    if not hook and story:
        hook = str(story.get("headline") or story.get("poll_question") or "").strip()
    if not body:
        parts = []
        for key, value in piece.items():
            if str(key).startswith("story_") and isinstance(value, dict):
                parts.extend(str(value.get(name) or "") for name in ("headline", "subtext", "poll_question"))
        for key, text in iter_copy(piece):
            if ".spoken" in key or ".on_screen" in key or key.startswith("slides"):
                parts.append(text)
        body = " ".join(part for part in parts if part).strip()
    if not hook and body:
        hook = body.split("\n", 1)[0][:160].strip()
    return hook, body


def _first(piece: dict, *keys: str) -> str:
    for key in keys:
        value = piece.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", "", str(text or "").lower())).strip()


def _banned(hook: str) -> str:
    opening = _norm(hook)
    for banned in BANNED_OPENERS:
        if opening.startswith(_norm(banned)):
            return banned
    return ""


def _dim(name: str, score: float, evidence: str, *, hard: bool = False) -> dict:
    return {"name": name, "score": round(float(score), 2), "evidence": evidence, "hard_fail": hard}


def _schema_issues(label: str, piece: dict) -> list[str]:
    from content_generator.core.schema_validation import (
        BlogSchema, CarouselSchema, InstagramSchema, LinkedinSchema, ReelSchema,
        YoutubeShortSchema, validate_or_fail,
    )
    schemas = {
        "reel_1": ReelSchema, "reel_2": ReelSchema, "growth_reel": ReelSchema,
        "carousel": CarouselSchema, "instagram_post": InstagramSchema,
        "linkedin_post": LinkedinSchema, "blog_post": BlogSchema, "yt_short": YoutubeShortSchema,
    }
    if label == "threads_post":
        text = _first(piece, "text", "body", "content")
        if text and len(text) > 500:
            return ["threads text is over 500 characters"]
        return []
    schema = schemas.get(label)
    if schema is None:
        return []
    try:
        validate_or_fail(schema, piece)
    except Exception as exc:
        return [str(exc).strip().replace("\n", " ")[:300]]
    return []


def _sibling_hooks(content: dict, label: str) -> list[tuple[str, str, str]]:
    rows = []
    for other_label, _platform, piece in _assets(content):
        if other_label == label or not isinstance(piece, dict):
            continue
        hook = _first(piece, "hook", "hook_text", "headline", "title")
        cta = _first(piece, "cta", "primary_cta")
        rows.append((other_label, _norm(hook), _norm(cta)))
    return rows


def review_asset(platform: str, piece: dict, content: dict | None = None, *, label: str = "", attempts: int | None = None, max_retries: int | None = None) -> dict:
    """Score one asset. Hard fails cannot PASS, whatever the average is."""
    content = content if isinstance(content, dict) else {}
    piece = piece if isinstance(piece, dict) else {}
    label = label or next((key for key, value in LABEL_PLATFORM.items() if value == platform), platform)
    platform = LABEL_PLATFORM.get(label, platform)
    featured = str(content.get("featured_product") or piece.get("featured_product") or piece.get("product") or "")
    if not featured:
        from content_generator.core.product_truth import featured_product_name
        featured = featured_product_name(content)
    plan = asset_plan(platform if platform in ("reel", "carousel", "ig_single", "stories", "facebook", "threads", "linkedin", "yt_short", "blog", "whatsapp") else "facebook", int(content.get("day_number") or 0), featured, variant=1 if label == "reel_2" else 0)
    piece["growth_plan"] = plan
    hook, body = _native_hook_body(piece)
    cta = _first(piece, "cta", "primary_cta")
    blob = _blob(piece)
    hard: list[str] = []
    banned = _banned(hook)
    if banned:
        hard.append(f"banned_opener:{banned}")

    from content_generator.core.product_truth import asset_product_truth_findings
    findings = asset_product_truth_findings(piece, featured=featured)
    if findings:
        hard.append("claim_or_brand:" + str(findings[0].get("message") or findings[0])[:180])
    from content_generator.prompts.growth_engine.platforms import ultra_positive_story
    if ultra_positive_story(featured) and (
        not re.search(r"70\s*%\s*coffee", blob, re.I) or not re.search(r"30\s*%\s*chicory", blob, re.I)
    ):
        hard.append("ultra_ratio_missing")

    try:
        from content_generator.core.brand_validator import validate_no_prohibited_claims
        if blob and not validate_no_prohibited_claims(blob):
            hard.append("prohibited_claim")
    except Exception as exc:
        hard.append(f"claim_scan_error:{type(exc).__name__}")

    schema = _schema_issues(label, piece)
    if schema:
        hard.append("schema:" + schema[0][:180])

    own_hook, own_cta = _norm(hook), _norm(cta)
    order = [name for name, _platform, _piece in _assets(content)]
    rank = order.index(label) if label in order else len(order)
    for other, other_hook, other_cta in _sibling_hooks(content, label):
        if order.index(other) if other in order else -1 >= rank:
            continue
        if own_hook and len(own_hook) > 12 and own_hook == other_hook:
            hard.append(f"duplicate_hook:{other}")
            break
        if own_cta and len(own_cta) > 20 and own_cta == other_cta:
            hard.append(f"duplicate_cta:{other}")
            break

    specific = len(hook.split()) >= 3 and not banned
    fact = bool(re.search(r"100%|70%|30%|chicory|robusta|arabica|label|freeze|agglomerat|rs\s*\d", blob, re.I))
    dims = [
        _dim("platform_fit", 9 if hook and body else 4, "Hook and body are both present." if hook and body else "The platform asset is missing a hook or a body."),
        _dim("hook", 2 if banned else (9 if specific else 4), f"Banned opener '{banned}'." if banned else ("The hook names a specific subject." if specific else "The hook is too thin to stop a scroll.")),
        _dim("retention", 8 if fact and body else 5, "The body contains a concrete coffee fact." if fact and body else "The body does not yet pay the viewer for staying."),
        _dim("payoff", 8 if hook and body else 4, "The body continues the hook." if hook and body else "There is no payoff after the hook."),
        _dim("shareability", 9 if re.search(r"\b(send|share|comment|reply|question)\b", blob, re.I) else 6, "There is a reason to pass this on." if re.search(r"\b(send|share|comment|reply)\b", blob, re.I) else "No explicit share or reply ask."),
        _dim("saveability", 8 if fact else 6, "A checkable fact is worth saving." if fact else "Little here to save."),
        _dim("follow_conversion", 8 if re.search(r"follow|subscribe|@puritybeans|reads? the (jar|label)|label", blob, re.I) else 5, "The follow reason is specific." if re.search(r"follow|subscribe|@puritybeans|reads? the (jar|label)|label", blob, re.I) else "No follow promise is visible."),
        _dim("purchase_relevance", 8 if re.search(r"bold|ultra|purista|purica|prima|p3online|shop|wholesale", blob, re.I) else 6, "The featured jar or a verified next step is named." if re.search(r"bold|ultra|p3online|shop", blob, re.I) else "No product next step. Allowed when the objective is reach, scored as incomplete for a shop ask."),
        _dim("brand_truth", 0 if any(item.startswith("claim_or_brand") or item == "ultra_ratio_missing" for item in hard) else 10, "Product truth failed." if findings or "ultra_ratio_missing" in hard else "No product-truth finding.", hard=any(item.startswith("claim_or_brand") or item == "ultra_ratio_missing" for item in hard)),
        _dim("visual_integrity", 8, "No generated frame is attached. The jar compositor remains the only image path, and it does not redraw the label."),
        _dim("claim_verification", 0 if "prohibited_claim" in hard else 10, "A prohibited claim is present." if "prohibited_claim" in hard else "No prohibited health or medical claim.", hard="prohibited_claim" in hard),
        _dim("originality", 0 if any(item.startswith("duplicate_") for item in hard) else 9, "This hook or CTA repeats another platform today." if any(item.startswith("duplicate_") for item in hard) else "Hook and CTA are not copied from another asset today.", hard=any(item.startswith("duplicate_") for item in hard)),
        _dim("mobile_readability", 6 if hook.isupper() and len(hook) > 48 else 9, "The hook is a long all-caps line." if hook.isupper() and len(hook) > 48 else "The hook is short enough to read on a phone."),
        _dim("cta_clarity", 9 if cta and cta.count("http") <= 1 else (5 if not cta else 7), "One CTA field is present." if cta else "No single next step is declared."),
        _dim("schema", 0 if schema else 8, schema[0] if schema else "No schema or length failure for this format.", hard=bool(schema)),
    ]
    if len(dims) != len(DIMENSIONS) or [item["name"] for item in dims] != list(DIMENSIONS):
        hard.append("dimension_contract")
    overall = round(sum(item["score"] for item in dims) / len(DIMENSIONS), 2)
    threshold = _threshold()
    used = int(piece.get("_growth_attempts") or attempts or 1)
    budget = _max_retries() if max_retries is None else int(max_retries)
    if hard or overall < threshold:
        decision = "BLOCKED" if used > budget else "REGENERATE"
    else:
        decision = "PASS"
    feedback = "; ".join(hard) or "; ".join(
        f"{item['name']} {item['score']}: {item['evidence']}" for item in dims if item["score"] < threshold
    )
    review = {
        "platform": platform,
        "label": label,
        "decision": decision,
        "overall": overall,
        "threshold": threshold,
        "dimensions": dims,
        "hard_fails": hard,
        "attempts": used,
        "retry_limit": budget,
        "feedback": feedback,
        "plan": plan,
        "published": False,
    }
    piece["growth_review"] = review
    return review


def _assets(content: dict) -> list[tuple[str, str, dict]]:
    rows: list[tuple[str, str, dict]] = []
    mapping = (
        ("growth_reel", "growth_reel"),
        ("carousel", "carousel"),
        ("instagram_post", "instagram_post"),
        ("stories", "stories"),
        ("facebook_post", "facebook_post"),
        ("threads_post", "threads_post"),
        ("linkedin_post", "linkedin_post"),
        ("yt_short", "yt_short"),
        ("blog_post", "blog_post"),
    )
    reels = content.get("reels") if isinstance(content.get("reels"), list) else []
    if reels and isinstance(reels[0], dict) and reels[0]:
        rows.append(("reel_1", "reel", reels[0]))
    if len(reels) > 1 and isinstance(reels[1], dict) and reels[1]:
        rows.append(("reel_2", "reel", reels[1]))
    for label, key in mapping:
        piece = content.get(key)
        if isinstance(piece, dict) and piece:
            rows.append((label, LABEL_PLATFORM[label], piece))
    if whatsapp_enabled():
        piece = content.get("whatsapp") if isinstance(content.get("whatsapp"), dict) else {}
        rows.append(("whatsapp", "whatsapp", piece or {"hook": "", "body": ""}))
    return rows


def review_portfolio(content: dict, *, max_retries: int | None = None) -> dict:
    """Score the day and write the portfolio summary onto the content object."""
    assets = []
    for label, platform, piece in _assets(content):
        assets.append(review_asset(platform, piece, content, label=label, max_retries=max_retries))
    counts = {"PASS": 0, "REGENERATE": 0, "BLOCKED": 0}
    for asset in assets:
        counts[asset["decision"]] = counts.get(asset["decision"], 0) + 1
    featured = str(content.get("featured_product") or "")
    summary = {
        "sku": featured,
        "threshold": _threshold(),
        "objectives": list(OBJECTIVES),
        "assets": assets,
        "counts": counts,
        "complement": (
            "Reel discovers a label fact, the carousel saves the check, the single image is recall, "
            "Stories ask for one interaction, Facebook tells the situation, Threads asks one question, "
            "LinkedIn speaks to a buyer, the Short pays off alone, and the blog answers the search."
        ),
        "published": False,
    }
    content["growth_portfolio"] = summary
    return summary


def _place(content: dict, label: str, piece: dict) -> None:
    if label == "reel_1":
        content.setdefault("reels", [{}, {}])[0] = piece
    elif label == "reel_2":
        reels = content.setdefault("reels", [{}, {}])
        if len(reels) < 2:
            reels.append(piece)
        else:
            reels[1] = piece
    else:
        content[label if label != "growth_reel" else "growth_reel"] = piece


def enforce_portfolio(content: dict, regenerate=None, max_retries: int | None = None) -> dict:
    """Regenerate hard fails and sub-threshold assets, then BLOCK what is still dirty."""
    budget = _max_retries() if max_retries is None else int(max_retries)
    summary = review_portfolio(content, max_retries=budget)
    rounds = 0
    while regenerate is not None and rounds < budget:
        pending = [asset for asset in summary["assets"] if asset["decision"] == "REGENERATE"]
        if not pending:
            break
        for asset in pending:
            label = asset["label"]
            current = next(piece for name, _platform, piece in _assets(content) if name == label)
            current["_growth_attempts"] = int(current.get("_growth_attempts") or 1) + 1
            improved = regenerate(label, current, asset.get("feedback") or "")
            if isinstance(improved, dict) and improved:
                merged = {**current, **improved, "_growth_attempts": current["_growth_attempts"]}
                _place(content, label, merged)
        summary = review_portfolio(content, max_retries=budget)
        rounds += 1
    for asset in summary["assets"]:
        if asset["decision"] == "REGENERATE":
            asset["decision"] = "BLOCKED"
            asset["blocked_reason"] = "retry limit reached"
            for name, _platform, piece in _assets(content):
                if name == asset["label"] and isinstance(piece.get("growth_review"), dict):
                    piece["growth_review"]["decision"] = "BLOCKED"
                    piece["growth_review"]["blocked_reason"] = "retry limit reached"
    summary["counts"] = {"PASS": 0, "REGENERATE": 0, "BLOCKED": 0}
    for asset in summary["assets"]:
        summary["counts"][asset["decision"]] = summary["counts"].get(asset["decision"], 0) + 1
    content["growth_portfolio"] = summary
    return summary


def performance_hypothesis(platform: str, entry: dict) -> dict:
    """A learning note only when the metrics were verified. Likes are not virality."""
    if not isinstance(entry, dict) or entry.get("metrics_verified") is not True or entry.get("platform_confirmed") is not True:
        return {"used": False, "platform": platform, "reason": "unverified_metrics"}
    metrics = {key: value for key, value in (entry.get("metrics") or {}).items() if key in _VERIFIED_METRICS and isinstance(value, (int, float))}
    if not metrics:
        return {"used": False, "platform": platform, "reason": "no_verified_metric_fields"}
    reach = float(metrics.get("reach") or 0)
    shares = float(metrics.get("shares") or 0) + float(metrics.get("saves") or 0)
    hypothesis = "Test the same hook shape again." if reach and shares / reach >= 0.02 else "Keep the fact, change the opening."
    return {
        "used": True,
        "platform": platform,
        "metrics": metrics,
        "hypothesis": hypothesis,
        "viral_claim": False,
    }


def learning_block(entries: list[dict] | None = None) -> str:
    """Prompt text built only from verified, platform-confirmed rows."""
    if entries is None:
        try:
            from content_generator.core.learning_engine import _load_log
            entries = _load_log()
        except Exception:
            entries = []
    lines = []
    for entry in entries or []:
        note = performance_hypothesis(str(entry.get("track") or entry.get("platform") or ""), entry)
        if note.get("used"):
            lines.append(f"- {note['platform']}: {note['hypothesis']}")
    if not lines:
        return ""
    return "VERIFIED PERFORMANCE ONLY (ignore likes as a virality claim):\n" + "\n".join(lines[:5])


def confirmed_published(record: dict | None) -> bool:
    """True only after the platform read-back confirms the object."""
    return bool(record and record.get("status") == "VERIFIED_LIVE" and record.get("published") is True)
