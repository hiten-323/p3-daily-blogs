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
            {"on": hook or "ONE INGREDIENT", "sub": "100% coffee. Zero chicory."},
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
    try:
        from moviepy import ImageClip, concatenate_videoclips
    except Exception as e:
        logger.info("[reel_video] moviepy unavailable (%s) — skipping video", e)
        return None

    # Cinematic frames (real jar, white knocked out, gradient backdrop) —
    # falls back to the static-post composer if unavailable.
    try:
        from content_generator.creative.cinematic_frame import compose_cinematic_frame as _frame
    except Exception:
        from content_generator.creative.real_jar_composer import compose_post_image as _frame

    from content_generator.publisher.surface_copy import clean_reel_beats
    beats = clean_reel_beats(reel)
    total_beats = len(beats)
    product = reel.get("product") or reel.get("featured_product")
    frame_paths = []
    for i, b in enumerate(beats):
        if _frame.__name__ == "compose_cinematic_frame":
            p = _frame(
                headline=b["on"], sub=b["sub"], day=day, idx=i, product=product,
                width=1080, height=1920, label=f"{label}_beat{i}_day{day}",
                format_type="reel", scene_idx=i, total_scenes=total_beats,
                on_date=on_date,
            )
        else:
            p = _frame(
                headline=b["on"], body=b["sub"], day=day, idx=i, product=product,
                width=1080, height=1920, label=f"{label}_beat{i}_day{day}",
            )
        if p:
            try:
                from content_generator.creative.jar_frame import audit_product_image
                visual = audit_product_image(p)
            except Exception as exc:
                logger.warning("[reel_video] jar QA failed closed: %s", exc)
                visual = {"ok": False}
            if not visual.get("ok"):
                logger.error("[reel_video] skipping beat %s: %s", i, visual.get("issues"))
                continue
            frame_paths.append(p)
    if not frame_paths:
        return None

    dirs = {}
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        dirs = get_visual_adaptation_directives(platform="instagram")
    except Exception:
        dirs = {}

    boost_motion = dirs.get("boost_motion", True)

    clips = []
    for i, p in enumerate(frame_paths):
        try:
            dur = _BEAT_SECONDS
            clip = ImageClip(p).with_duration(dur)
            # Subtle Ken Burns motion: gentle push-in / push-out keeping jar textures and typography razor sharp
            try:
                if boost_motion:
                    if i % 2 == 0:
                        clip = clip.resized(lambda t, d=dur: 1.0 + 0.04 * (t / d))
                    else:
                        clip = clip.resized(lambda t, d=dur: 1.04 - 0.03 * (t / d))
                else:
                    clip = clip.resized(lambda t, d=dur: 1.0 + 0.02 * (t / d))
            except Exception as _e:
                logger.debug("[reel_video] optional step failed: %s", _e)
            clips.append(clip)
        except Exception as e:
            logger.debug("[reel_video] clip build failed: %s", e)

    if not clips:
        return None

    try:
        video = concatenate_videoclips(clips, method="compose")
    except Exception:
        video = concatenate_videoclips(clips)

    # Background music: Audio Director picks a mood-matched royalty-free track
    # from music_library/ for the content; env override wins if set.
    music = os.getenv("REEL_MUSIC_FILE")
    if not (music and os.path.exists(music)):
        try:
            from content_generator.creative.audio_director import get_audio_plan
            hook = str(reel.get("hook_text") or reel.get("caption") or "")
            music = get_audio_plan(hook, day).get("local_track")
        except Exception as e:
            logger.debug("[reel_video] audio director skipped: %s", e)
    if music and os.path.exists(music):
        try:
            from moviepy import AudioFileClip
            audio = AudioFileClip(music)
            dur = min(audio.duration, video.duration)
            audio = audio.subclipped(0, dur)
            try:
                # Scale volume to commercial loudness (~ -14 LUFS / dB) so it's punchy and audible
                audio = audio.with_volume_scaled(1.8)
            except Exception as ve:
                logger.debug("[reel_video] volume scaling failed: %s", ve)
            video = video.with_audio(audio)
        except Exception as e:
            logger.debug("[reel_video] music attach failed: %s", e)

    os.makedirs(_OUT_DIR, exist_ok=True)
    from content_generator.core.ist_dates import today_ist
    if on_date is None:
        date_str = today_ist().isoformat()
    elif hasattr(on_date, "isoformat"):
        date_str = on_date.isoformat()
    else:
        date_str = str(on_date)[:10]
    out = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}.mp4")
    try:
        temp_audio = os.path.join(_OUT_DIR, f"temp_{label}_{os.getpid()}_{day}.m4a")
        video.write_videofile(
            out,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            bitrate="10000k",
            pixel_format="yuv420p",
            ffmpeg_params=["-crf", "18", "-movflags", "+faststart"],
            temp_audiofile=temp_audio,
            remove_temp=True,
            logger=None,
            threads=2,
        )
        logger.info("[reel_video] Rendered %ds reel -> %s", int(video.duration), out)
        return out
    except Exception as e:
        logger.warning("[reel_video] render failed: %s", e)
        return None
    finally:
        try:
            video.close()
        except Exception as _e:
            logger.debug("[reel_video] optional step failed: %s", _e)
