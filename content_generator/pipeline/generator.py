"""
Generation pipeline.

Phase 1 — 8 independent tasks run in parallel via ThreadPoolExecutor:
    reel_1, reel_2, instagram_post, carousel, linkedin_post, blog_post, stories, yt_short

Phase 2 — depends on phase 1 results:
    video_prompts (needs reel_1, reel_2, yt_short)

Image prompts are generated locally (no LLM call).

New parameters:
    research_context — optional dict from agents.research.run_research()
                       Injects trend + competitor + strategy context into every prompt.
"""
import os
import json
import logging
import datetime
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from content_generator.rotation import (
    HOOK_ARCHETYPES, SAVE_MECHANICS, LINKEDIN_ANGLES, FACEBOOK_ANGLES, THREADS_ANGLES, PRODUCTS,
    get_day_number, get_todays_blog_topic, pick,
)
from content_generator.prompts import (
    reels, instagram_post, carousel, linkedin, stories, yt_short, video_prompts,
)
from content_generator.prompts import growth_reel
from content_generator.prompts.brand import build_avoid_block
from content_generator.providers.llm_router import call as llm_call, get_usage_log
from content_generator.core.ist_dates import content_date_iso, today_ist

logger = logging.getLogger(__name__)





def _has_native_threads_text(piece: object) -> bool:
    """True only when a Threads-specific object contains publishable native copy."""
    if not isinstance(piece, dict):
        return False
    text = str(piece.get("text") or piece.get("body") or piece.get("content") or "").strip()
    return bool(text) and len(text) <= 480


def _repair_threads_post(piece: object, angle: tuple, avoid: str, day_number: int, context: str) -> dict:
    """Retry malformed Threads generation instead of storing another platform's object."""
    if _has_native_threads_text(piece):
        return piece
    from content_generator.prompts import threads
    strict_suffix = (
        "\\n\\nOUTPUT CONTRACT: Return ONLY a JSON object with exactly two keys: "
        '"angle" and "text". "text" must be a native Threads post under 480 characters. '
        "Do not return reels, carousel, Facebook, LinkedIn, or any other asset."
    )
    for attempt in range(2):
        try:
            candidate = llm_call(
                threads.build(angle, avoid, day_number) + (context or "") + strict_suffix,
                f"threads_post_repair_{attempt + 1}",
                600,
            )
        except Exception as exc:
            logger.warning("[pipeline] Threads copy repair %d failed: %s", attempt + 1, exc)
            continue
        if _has_native_threads_text(candidate):
            logger.info("[pipeline] Repaired malformed native Threads copy on attempt %d", attempt + 1)
            return candidate
    logger.error("[pipeline] Threads output was not native text after two repairs; holding Threads rather than reusing another platform's copy")
    return {}


def _generate_blog(day_number: int, topic: str, context: str) -> dict:
    """Sectioned blog. Never returns {} when generation was attempted."""
    try:
        from content_generator.core.blog_writer import generate_blog_post
        piece = generate_blog_post(
            day_number,
            context_suffix=(context or "") + (f"\n\nANGLE: {topic}" if topic else ""),
            write_files=False,
        )
    except Exception as exc:
        logger.error("[blog] HELD blog_post — generation raised and the piece was not dropped: %s", exc)
        return {"held": True, "hold_reason": f"provider_failure during blog generation: {exc}"}
    if not isinstance(piece, dict) or not piece:
        reason = "blog generation returned an empty piece"
        logger.error("[blog] HELD blog_post: %s", reason)
        return {"held": True, "hold_reason": reason}
    if piece.get("hold_reason"):
        logger.error("[blog] HELD blog_post: %s", piece["hold_reason"])
    return piece


def _extended_content_enabled() -> bool:
    """
    Extended assets (reel_2, blog, stories, yt_short) increase free-tier TPM load.

    Source of truth: founder_policies.yaml content.enable_extended_content.
    Env ENABLE_EXTENDED_CONTENT is an emergency override only (set to force on/off
    without editing policy). Unset env → policy wins.
    """
    env = os.getenv("ENABLE_EXTENDED_CONTENT")
    if env is not None and str(env).strip() != "":
        return str(env).lower() == "true"
    try:
        from content_generator.core.founder_policy import policy
        return bool(policy().get("enable_extended_content", False))
    except Exception as e:
        logger.debug("[pipeline] policy extended-content unavailable (%s) — default false", e)
        return False


# ── Image prompts — generated locally, no LLM ─────────────────────────────────

def _image_prompts() -> dict:
    return {
        "ai_image_prompts": [
            {
                "id":      "img_carousel_cover",
                "use_for": "Instagram carousel cover (1080x1080)",
                "prompt": (
                    "Cinematic dark espresso tones — Purity Beans jar centred on black marble, "
                    "single diagonal golden beam from upper right, micro coffee granules scattered, "
                    "editorial luxury food photography, deep shadows, faint cream steam wisps, "
                    "razor-sharp product label"
                ),
            },
            {
                "id":      "img_reel_cover",
                "use_for": "Instagram Reel thumbnail (1080x1920 vertical)",
                "prompt": (
                    "Vertical cinematic coffee portrait — Purity Beans jar as sole hero, "
                    "warm amber backlight through frosted glass, shallow depth of field, "
                    "single thread of steam, dark moody atmosphere, no people, no text, editorial quality"
                ),
            },
            {
                "id":      "img_linkedin_banner",
                "use_for": "LinkedIn post image (1200x628)",
                "prompt": (
                    "Wide editorial product landscape — Purity Beans jar on dark weathered wooden desk, "
                    "MacBook soft-blurred at left edge, single warm desk lamp, professional but human, "
                    "documentary texture, 16:9 wide composition, no text"
                ),
            },
            {
                "id":      "img_blog_hero",
                "use_for": "Blog hero image (1200x630)",
                "prompt": (
                    "Lifestyle editorial — Indian professional hands cradling a dark ceramic mug, "
                    "Purity Beans jar visible soft-focus on desk, warm morning window light from left, "
                    "genuine moment not staged, documentary grain, 16:9 crop"
                ),
            },
            {
                "id":      "img_story_bg",
                "use_for": "Instagram Story background (1080x1920)",
                "prompt": (
                    "Vertical dark editorial — heavily blurred Purity Beans jar in background "
                    "with deep amber bokeh, top two-thirds empty for text overlay, grain texture, "
                    "deep blacks, warm gold accent light"
                ),
            },
        ]
    }


# ── Research context helpers ──────────────────────────────────────────────────

def _build_context_suffix(research: dict) -> str:
    """
    Build a prompt suffix from research intelligence.
    Appended to every LLM prompt so all content is trend-aware and
    competitor-differentiated.
    """
    if not research:
        return ""
    parts: list[str] = []

    if research.get("trends_prompt_block"):
        parts.append(research["trends_prompt_block"])

    if research.get("competitor_prompt_block"):
        parts.append(research["competitor_prompt_block"])

    sc = research.get("strategy_context", {})
    if sc.get("top_performing_hook"):
        parts.append(
            f"PERFORMANCE INSIGHT: The '{sc['top_performing_hook']}' hook archetype "
            f"currently averages {sc['top_hook_avg_views']:,} views for Purity Beans. "
            f"Lean into this archetype where it fits naturally."
        )

    parts.append(
        "ANTI-CANNIBALIZATION DIVERSITY RULE:\n"
        "Use trend intelligence as subtle background if applicable, but DO NOT overwrite "
        "your specific assigned angle/format. Every platform has an independent job: do not "
        "replicate another platform's premise."
    )

    return ("\n\n" + "\n\n".join(parts)) if parts else ""


def _optimized_pick(bank: list, day: int, label: str = "", offset: int = 0):
    """
    Pick a bank item biased toward top performers.
    Falls back to plain round-robin if no performance data exists.
    """
    try:
        from content_generator.analytics.optimizer import get_optimized_pick
        return get_optimized_pick(bank, day, label=label, offset=offset)
    except Exception:
        return pick(bank, day, offset)


# ── Pipeline ───────────────────────────────────────────────────────────────────

def generate_daily_content(
    day_number: int  = None,
    research_context: dict = None,
) -> dict:
    """
    Generate a full day's content via a two-phase parallel pipeline.

    Args:
        day_number:       Override the auto-computed day counter (for testing).
        research_context: Output of agents.research.run_research() — injects
                          trends, competitor data, and performance insights into
                          every prompt. Pass None to skip (safe default).

    Returns a dict with these keys:
        date, day_number, reels, instagram_post, carousel, linkedin_post,
        blog_post, stories, yt_short, video_prompts, ai_image_prompts,
        performance_targets
    """
    if day_number is None:
        day_number = get_day_number()

    if day_number < 0:
        raise ValueError(f"day_number must be >= 0, got {day_number}")

    todays_date = today_ist().isoformat()
    avoid       = build_avoid_block()

    # Optimizer-biased selections (falls back to round-robin if no data)
    product = pick(PRODUCTS, day_number)
    arch_1  = _optimized_pick(HOOK_ARCHETYPES, day_number, label="reel_1_hook")
    arch_2  = _optimized_pick(HOOK_ARCHETYPES, day_number, label="reel_2_hook", offset=5)
    mech    = _optimized_pick(SAVE_MECHANICS,  day_number, label="carousel_mech")
    angle   = _optimized_pick(LINKEDIN_ANGLES, day_number, label="linkedin_angle")
    topic   = get_todays_blog_topic(day_number)

    # Context suffix injected into every prompt
    ctx = _build_context_suffix(research_context or {})

    # Continuous learning — inject what worked / failed from past posts
    try:
        from content_generator.core.learning_engine import get_learning_block
        from content_generator.analytics.instagram_growth import get_instagram_growth_block
        learning = get_learning_block()
        if learning:
            ctx += "\n\n" + learning
        ig_growth = get_instagram_growth_block()
        if ig_growth:
            ctx += "\n\n" + ig_growth
        # Post-generation visual QA becomes an input to the NEXT generation.
        # This is deliberately separate from measured performance learning:
        # heuristics can constrain bad/repetitive visuals, but never masquerade
        # as evidence that a format is viral.
        try:
            from content_generator.analytics.creative_post_audit import get_adaptation_block
            visual_adaptation = get_adaptation_block()
            if visual_adaptation:
                ctx += "\n\n" + visual_adaptation
        except Exception as visual_exc:
            logger.debug("[pipeline] visual adaptation block unavailable: %s", visual_exc)
    except Exception as e:
        logger.debug("[pipeline] learning block unavailable: %s", e)

    # Creative fatigue guard — never repeat the last 60 days of hooks/angles
    try:
        from content_generator.analytics.hook_selector import get_fatigue_block
        fatigue = get_fatigue_block()
        if fatigue:
            ctx += "\n\n" + fatigue
    except Exception as e:
        logger.debug("[pipeline] fatigue block unavailable: %s", e)

    # Growth Director — stage-aware strategy brief (Million Follower Mode,
    # one funnel objective per reel, watch-time structure)
    try:
        from content_generator.core.growth_director import get_strategy_brief
        ctx += "\n\n" + get_strategy_brief(day_number)
    except Exception as e:
        logger.debug("[pipeline] growth director unavailable: %s", e)

    logger.info(
        "[pipeline] Day #%d (%s) | product=%s | Reel1=%s | Reel2=%s | Carousel=%s | LinkedIn=%s",
        day_number, todays_date, product, arch_1[0], arch_2[0], mech[0], angle[0],
    )

    # ── Phase 1: core tasks (always run) ─────────────────────────────────────
    # Keep core small to stay within free-tier TPM limits (Groq/Cerebras).
    # Extended tasks (blog, stories, yt_short) gated by founder policy.
    _extended = _extended_content_enabled()
    logger.info("[pipeline] extended content %s (policy/env)", "ON" if _extended else "OFF")

    # Semantic Anti-Cannibalization: Assign independent angles from dedicated platform premise banks
    fb_angle = _optimized_pick(FACEBOOK_ANGLES, day_number, label="facebook_angle")
    th_angle = _optimized_pick(THREADS_ANGLES, day_number, label="threads_angle")

    phase1_tasks = {
        "reel_1":         (reels.build,          ("reel_1", arch_1, "morning (7-9am)",       "reel_morning", avoid, day_number), 1800),
        "carousel":       (carousel.build,       (mech, avoid, day_number),                                           2200),
        "linkedin_post":  (linkedin.build,       (angle, avoid),                                                      1200),
        "instagram_post": (instagram_post.build, (day_number, avoid),                                                  800),
        "growth_reel":    (growth_reel.build,    (day_number, avoid),                                                 2500),
    }

    if _extended:
        from content_generator.prompts import threads, facebook
        phase1_tasks.update({
            "reel_2":        (reels.build,    ("reel_2", arch_2, "evening/night (8-10pm)", "reel_night", avoid, day_number), 1800),
            "stories":       (stories.build,  (day_number,),                                                      1500),
            "yt_short":      (yt_short.build, (product, day_number),                                              1500),
            "threads_post":  (threads.build,  (th_angle, avoid, day_number),                                      600),
            "facebook_post": (facebook.build, (fb_angle, avoid, day_number),                                     800),
        })

    phase1_results: dict[str, dict] = {}

    # Concurrency is capped low by default: free-tier LLMs (e.g. Groq 12K TPM)
    # get 429-throttled when several large generations fire at once — more
    # workers makes it worse, not better. Raise GEN_MAX_WORKERS only when a
    # high-quota provider (valid Gemini key) is carrying the load.
    _workers = max(1, int(os.getenv("GEN_MAX_WORKERS", "2")))
    with ThreadPoolExecutor(max_workers=_workers) as pool:
        futures = {
            pool.submit(llm_call, fn(*args) + ctx, label, tokens): label
            for label, (fn, args, tokens) in phase1_tasks.items()
        }
        for future in as_completed(futures):
            label = futures[future]
            try:
                phase1_results[label] = future.result()
            except Exception as e:
                logger.error("[pipeline] %s failed: %s", label, e)
                raise

    # The blog is sectioned (outline, then one expansion per heading). A provider
    # failure keeps the draft and records why it was held. It must not cancel
    # the other assets, and it must not be replaced with an empty object.
    if _extended:
        phase1_results["blog_post"] = _generate_blog(day_number, topic, ctx)

    # A malformed model response must not smuggle another platform's assets
    # into the Threads field. Retry the native prompt, then hold if still invalid.
    if _extended:
        phase1_results["threads_post"] = _repair_threads_post(
            phase1_results.get("threads_post"), th_angle, avoid, day_number, ctx
        )

    # Fill optional keys with empty dicts so downstream code doesn't KeyError
    for optional in ("reel_2", "blog_post", "stories", "yt_short", "threads_post", "facebook_post"):
        phase1_results.setdefault(optional, {})

    # Semantic Premise Lock: verify portfolio premise diversity
    try:
        from content_generator.core.semantic_lock import verify_portfolio_diversity
        div_check = verify_portfolio_diversity(phase1_results)
        if not div_check["passes"]:
            logger.warning("[pipeline] Premise diversity notice: duplicates=%s", div_check["duplicates"])
    except Exception as e:
        logger.debug("[pipeline] semantic diversity check error: %s", e)

    # ── Phase 2: video prompts (depends on phase 1) ───────────────────────────
    vp = llm_call(
        video_prompts.build(
            phase1_results["reel_1"],
            phase1_results["reel_2"],
            phase1_results["yt_short"],
            product,
        ),
        label="video_prompts",
        max_tokens=3500,
    )

    # ── Merge ─────────────────────────────────────────────────────────────────
    import uuid as _uuid
    from content_generator.core.versions import PROMPT_VERSION, SCHEMA_VERSION

    def _kpi_at_creation() -> str:
        try:
            from content_generator.core.reward import get_active_kpi
            return get_active_kpi()
        except Exception as e:
            logger.warning("[decision] target KPI unavailable at creation: %s", e)
            return ""

    def _policy_version_at_creation() -> str:
        try:
            from content_generator.core.founder_policy import policy
            return str(policy().version)
        except Exception as e:
            logger.debug("[decision] policy version unavailable: %s", e)
            return ""

    def _selected_frame_id(ctx: dict | None) -> str:
        try:
            from content_generator.core.coffee_psychology import (
                get_frame, recommended_frame_for_format,
            )
        except Exception as e:
            logger.warning("[psychology] registry unavailable: %s", e)
            return ""
        candidate = str((ctx or {}).get("psychology_frame_id") or "").strip()
        if candidate and get_frame(candidate):
            return candidate
        if candidate:
            logger.warning("[psychology] frame %r not in registry — reselecting", candidate)
        try:
            # recommended_frame_for_format returns a LIST of frame ids in
            # preference order. This only handled a dict or a bare string, so
            # str(list) produced "['revelation', ...]" — never a valid id — and
            # selection fell through to "", which the editorial gate then
            # rejects as ungoverned. Take the first id that resolves.
            recommended = recommended_frame_for_format("reel")
            if isinstance(recommended, dict):
                recommended = [recommended.get("id")]
            elif isinstance(recommended, str):
                recommended = [recommended]
            for fid in (recommended or []):
                fid = str(fid or "").strip()
                if fid and get_frame(fid):
                    logger.info("[psychology] selected frame: %s", fid)
                    return fid
        except Exception as e:
            logger.warning("[psychology] frame recommendation failed: %s", e)
        logger.error("[psychology] no valid frame selected — run will be rejected "
                     "by the editorial gate rather than publish ungoverned")
        return ""

    output = {
        "date":           todays_date,
        "day_number":     day_number,
        "generation_id":  f"gen_{today_ist().isoformat()}_{_uuid.uuid4().hex[:8]}",
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "psychology_frame":         _selected_frame_id(research_context),
        "psychology_frame_version": (research_context or {}).get("psychology_frame_version", 1),
        "target_kpi_at_creation":   _kpi_at_creation(),
        "policy_version_at_creation": _policy_version_at_creation(),
        "reels":          [phase1_results["reel_1"], phase1_results["reel_2"]],
        "instagram_post": phase1_results["instagram_post"],
        "carousel":       phase1_results["carousel"],
        "linkedin_post":  phase1_results["linkedin_post"],
        "blog_post":      phase1_results["blog_post"],
        "stories":        phase1_results["stories"],
        "yt_short":       phase1_results["yt_short"],
        "growth_reel":    phase1_results.get("growth_reel", {}),
        "threads_post":   phase1_results.get("threads_post", {}),
        "facebook_post":  phase1_results.get("facebook_post", {}),
        **vp,
        **_image_prompts(),
        "performance_targets": {
            "reel_views_3s":           15000,
            "reel_views_30s":          5000,
            "reel_saves":              800,
            "reel_shares":             300,
            "carousel_swipe_rate_pct": 65,
            "carousel_saves":          600,
            "linkedin_impressions":    3000,
            "linkedin_comments":       40,
            "story_poll_votes":        500,
            "story_dm_replies":        50,
            "link_clicks":             200,
            "new_followers":           300,
        },
    }

    # Platform-native follower-growth diagnostics are persisted with every
    # generation so reports can identify missing native assets and risky copy.
    # Diagnostics do not fabricate a score or silently block unrelated assets.
    try:
        from content_generator.core.growth_contract import audit_portfolio
        output["follower_growth_audit"] = audit_portfolio(output)
        for platform, result in output["follower_growth_audit"]["results"].items():
            if not result["passes"] or result["warnings"]:
                logger.warning(
                    "[growth-contract] %s passes=%s errors=%s warnings=%s",
                    platform, result["passes"], result["errors"], result["warnings"],
                )
    except Exception as exc:
        # Record failure as a visible hold in diagnostics, never as a silent pass.
        logger.exception("[growth-contract] audit failed")
        output["follower_growth_audit"] = {
            "contract_version": "follower-growth-v1",
            "passes": False,
            "audit_error": str(exc),
        }

    if os.getenv("ENABLE_USAGE_LOG", "false").lower() == "true":
        output["usage"] = get_usage_log()

    vp_data   = output.get("video_prompts", {})
    vp_frames = (
        len(vp_data.get("reel_1",    {}).get("frames", []))
        + len(vp_data.get("reel_2",  {}).get("frames", []))
        + len(vp_data.get("yt_short",{}).get("scenes", []))
    )
    logger.info(
        "[pipeline] Done — 2 reels | 1 insta post | 1 carousel | 1 linkedin | "
        "1 blog | 1 stories | 1 yt short | %d video prompt frames",
        vp_frames,
    )
    return output


def save_content(content_data: dict, output_dir: str = "output") -> str:
    if not isinstance(content_data, dict):
        raise TypeError("content_data must be a dict")
    os.makedirs(output_dir, exist_ok=True)
    # Filename and the date field are the same IST day. Legacy long-form
    # dates already in the dict are normalized so later slots can match them.
    date_str = content_date_iso(content_data.get("date")) or today_ist().isoformat()
    content_data["date"] = date_str
    if not str(content_data.get("generation_id") or "").strip():
        source = str(content_data.get("_source") or content_data.get("source") or "generated").strip()
        prefix = "fallback" if source.startswith("emergency_fallback") else "gen"
        content_data["generation_id"] = f"{prefix}_{date_str}_{uuid.uuid4().hex[:8]}"
        logger.info("[pipeline] assigned missing generation_id=%s", content_data["generation_id"])
    filepath = os.path.join(output_dir, f"content_{date_str}.json")
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(content_data, f, indent=2, ensure_ascii=False)
    blog = content_data.get("blog_post")
    if isinstance(blog, dict) and str(blog.get("title") or "").strip() and str(blog.get("body") or "").strip():
        try:
            from content_generator.core.blog_render import write_blog_files
            write_blog_files(blog, output_dir, date_str)
        except Exception as exc:
            logger.error("[blog] HELD file write failed for %s: %s", date_str, exc)
    logger.info("[pipeline] Saved → %s", filepath)
    return filepath
