"""
Free motion-reel generator — real reel VIDEOS at zero cost, no AI credits.

Turns a reel's beats into a vertical 1080x1920 mp4: each beat is a branded
real-jar composite (from real_jar_composer) shown with a gentle zoom, chained
with crossfades. moviepy only — renders on any CI runner, no GPU, no API.

Not AI-cinematic, but: real product, real motion, on-screen captions, fully
automated. Pairs with the two-tier strategy — hero reels stay manual (Runway/
fal.ai); daily volume is these.

Optional background music: set REEL_MUSIC_FILE to a royalty-free audio path.
Silent otherwise (safe — add trending audio in-app if desired).
"""
from __future__ import annotations
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_BEAT_SECONDS = 2.0   # Exactly 1 bar at 120 BPM (0.5s * 4 = 2.0s) for downbeat synchronization
_MAX_BEATS    = 6


def _fallback_beats(reel: dict) -> list[dict]:
    """Claim-safe beats when a reel has no frames. Unknown jars stay neutral."""
    from content_generator.creative.cinematic_frame import _product_class
    product = str(reel.get("product") or "").strip()
    kind = _product_class(product)
    hook = str(reel.get("hook_text") or reel.get("hook") or "").strip()
    if kind == "ultra":
        return [
            {"on": hook or "ULTRA BLEND", "sub": "70% coffee. 30% chicory."},
            {"on": "30% CHICORY", "sub": "The blend is on the label."},
            {"on": "PURITY BEANS", "sub": "Shop at p3online.in"},
        ]
    if kind == "pure":
        return [
            {"on": hook or "ONE INGREDIENT", "sub": "pure coffee. Zero chicory."},
            {"on": "READ THE LABEL", "sub": "Coffee. Nothing else."},
            {"on": "PURITY BEANS", "sub": "Shop at p3online.in"},
        ]
    return [
        {"on": hook or "READ THE LABEL", "sub": "India's cleanest instant coffee."},
        {"on": "CHECK THE BACK", "sub": "The ingredient list is the recipe."},
        {"on": "PURITY BEANS", "sub": "Shop at p3online.in"},
    ]


def _beats_from_reel(reel: dict) -> list[dict]:
    """Extract (on_screen, spoken) beats from a reel in any of its shapes."""
    beats = []
    for fr in (reel.get("frames") or reel.get("script") or []):
        if isinstance(fr, dict):
            on = str(fr.get("on_screen") or fr.get("headline") or "").strip()
            sub = str(fr.get("spoken") or fr.get("voiceover") or "").strip()
            if on or sub:
                beats.append({"on": on or (sub[:32] + "…"), "sub": sub})
    if not beats:
        beats = _fallback_beats(reel)
    return beats[:_MAX_BEATS]


def resolve_reel_product(reel: dict):
    """The featured SKU for a reel/short dict.

    Generated reels carry the SKU under ``featured_product`` (or the growth
    plan), not ``product``. Reading only ``product`` gave None, which skipped
    the cinematic motion renderer and fell back to the flat Ken Burns poster
    slideshow (Oct 20 evening reel).
    """
    if not isinstance(reel, dict):
        return None
    for key in ("product", "featured_product", "sku"):
        v = reel.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for parent in ("growth_plan", "growth_review"):
        node = reel.get(parent)
        if isinstance(node, dict):
            if isinstance(node.get("sku"), str) and node["sku"].strip():
                return node["sku"].strip()
            plan = node.get("plan")
            if isinstance(plan, dict) and isinstance(plan.get("sku"), str) and plan["sku"].strip():
                return plan["sku"].strip()
    return None


def _cinematic(beats, product, day, label, on_date, seconds, format_type="reel"):
    """Procedural cinematic motion (cinematic_motion), gated by visual_gate. None -> legacy path."""
    if os.getenv("CINEMATIC_VIDEO", "1") == "0":
        return None
    try:
        from content_generator.creative.approved_photos import _norm_sku
        from content_generator.creative import cinematic_motion
        sku = _norm_sku(product)
        if not sku:
            return None
        from content_generator.core.ist_dates import today_ist
        ds = on_date.isoformat() if hasattr(on_date, "isoformat") else str(on_date or today_ist().isoformat())[:10]
        out = os.path.join(os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative")),
                           f"{label}_day{day}_{ds}_cinematic.mp4")
        meta = cinematic_motion.render_cinematic_until_pass(
            sku, [{"on": b.get("on", ""), "sub": b.get("sub", "")} for b in beats], out,
            seconds=seconds, seed=day, format_type=format_type, on_date=ds)
        return out if meta else None
    except Exception as exc:
        logger.warning("[cinematic] path failed (%s); using legacy frames", exc)
        return None


def _photo_fallback(reel, day, label, on_date, *, fast: bool) -> str | None:
    """Last-resort local FFmpeg reel from approved real photos; still needs the 8.0 gate."""
    try:
        from content_generator.creative import ken_burns, visual_gate
        path = ken_burns.render_reel(reel if isinstance(reel, dict) else {}, day, label, on_date, fast=fast, use_broll=False)
        if not path:
            return None
        verdict = visual_gate.evaluate_video(path, {"requires_jar": False}, visual_gate.recent_layouts())
        if verdict.get("passed"):
            logger.info("[reel_video] local FFmpeg real-photo fallback passed 8.0 visual gate")
            return path
        reasons = [str(x) for x in (verdict.get("reasons") or [])]
        logger.error("[reel_video] local FFmpeg fallback held by 8.0 visual gate: %s", reasons[:6])
        try:
            from content_generator.scheduler.daily import _remember_obstacle
            _remember_obstacle(label, "; ".join(reasons), "render", gate="local_ffmpeg_visual_gate")
        except Exception:
            pass
        return None
    except Exception as exc:
        logger.warning("[reel_video] photo fallback failed: %s", type(exc).__name__)
        return None


def build_reel_video(reel: dict, day: int, label: str = "reel_video", on_date=None) -> str | None:
    """
    Render a vertical motion reel. Returns mp4 path or None (caller falls back
    to an image post).
    """
    if os.getenv("ENABLE_REEL_VIDEO", "true").lower() != "true":
        return None
    try:
        from content_generator.creative.product_reel_templates import (
            materialize_template, resolve_reusable_reel,
        )
        source = resolve_reusable_reel(reel if isinstance(reel, dict) else {})
        inspiration = {}
        if isinstance(reel, dict) and isinstance(reel.get("reel_inspiration"), dict):
            inspiration = reel["reel_inspiration"]
        if source and inspiration.get("publish_source_video") is False:
            logger.info(
                "[reel_video] style reference %s is not the posted asset",
                inspiration.get("source_filename") or "gourmet_duo_mini.mp4",
            )
            source = None
        if source:
            hook = ""
            if isinstance(reel, dict):
                hook = str(reel.get("hook_text") or reel.get("caption") or "")
            logger.info(
                "[reel_video] reusing product reel template %s; source audio is silent "
                "and viral music stays on the audio director",
                os.path.basename(source),
            )
            return materialize_template(source, day, label, on_date=on_date, hook_text=hook)
        if inspiration.get("mode") == "style_cues":
            cue_ids = ", ".join(
                str(cue.get("id") or "") for cue in (inspiration.get("cues") or []) if isinstance(cue, dict)
            )
            logger.info("[reel_video] style cues only (%s); reference file stays in the bank", cue_ids)
    except Exception as exc:
        logger.debug("[reel_video] product reel lookup skipped: %s", exc)
    fast_cut = isinstance(reel, dict) and reel.get("growth_template_id") == "fast_cut_curiosity"
    _cin = _cinematic(_beats_from_reel(reel), resolve_reel_product(reel), day, label, on_date, 12.0, format_type="reel")
    if _cin:
        return _cin
    logger.warning("[reel_video] cinematic provider/procedural path did not pass for %s; trying gated local FFmpeg real-photo Ken Burns",
                   label)
    return _photo_fallback(reel, day, label, on_date, fast=fast_cut)
