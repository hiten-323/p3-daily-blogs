"""
Dynamic vertical Story Video generator for Instagram Stories.

Primary path: a rich layered 9–12s motion story (gradient, parallax bokeh,
true-colour jar cutout, kinetic text, royalty-free original bed) via
`story_motion.render_story_motion`. Falls back to a short Ken-Burns still
only when the motion path fails.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_DEFAULT_STORY_DURATION = float(os.getenv("STORY_MOTION_SECONDS", "10"))


def _sku_from(text: str | None, day: int) -> str:
    t = (text or "").lower()
    for s in ("ultra blend", "ultra_blend", "purista", "purica", "bold"):
        if s.replace("_", " ") in t or s in t:
            return "ultra_blend" if "ultra" in s else s.replace(" ", "_")
    try:
        from content_generator.rotation import PRODUCTS, pick as pick_product
        return str(pick_product(PRODUCTS, day) or "bold")
    except Exception:
        return "bold"


def build_story_video(
    image_path: str = None,
    headline: str = "",
    day: int = 0,
    duration: float = _DEFAULT_STORY_DURATION,
    label: str = "story_video",
    frame_paths: list[str] = None,
    on_date=None,
    reference_text: str | None = None,
    sub: str = "",
    product: str | None = None,
) -> str | None:
    """Render a 9–12s vertical story video (1080x1920 MP4) with audio.

    Prefers the motion story. Falls back to Ken Burns on a still if motion
    fails. Returns the MP4 path, or None when every path fails (caller then
    posts the improved static frame).
    """
    if os.getenv("ENABLE_STORY_VIDEO", "true").lower() != "true":
        logger.info("[story_video] disabled via ENABLE_STORY_VIDEO=false")
        return None

    try:
        from content_generator.creative.product_reel_templates import (
            materialize_template, select_product_reel,
        )
        selected = select_product_reel(text=reference_text if reference_text is not None else headline)
        if selected:
            logger.info("[story_video] reusing founder product reel %s", os.path.basename(selected["path"]))
            return materialize_template(selected["path"], day, label, on_date=on_date, hook_text=headline)
    except Exception as exc:
        logger.debug("[story_video] product reel lookup skipped: %s", exc)

    from content_generator.core.ist_dates import today_ist
    date_str = (on_date.isoformat() if hasattr(on_date, "isoformat")
                else str(on_date)[:10] if on_date else today_ist().isoformat())
    from content_generator.creative.approved_photos import _norm_sku
    sku = _norm_sku(product) or _norm_sku(_sku_from(reference_text or headline, day)) or "bold"

    if os.getenv("CINEMATIC_VIDEO", "1") != "0":
        try:
            from content_generator.creative import cinematic_motion
            out = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}_cinematic.mp4")
            meta = cinematic_motion.render_cinematic_until_pass(
                sku, [{"on": headline, "sub": sub}], out,
                seconds=duration or _DEFAULT_STORY_DURATION, seed=day,
                format_type="story")
            if meta:
                return out
            logger.warning("[story_video] cinematic story held by visual gate; trying premium card story")
        except Exception as exc:
            logger.warning("[story_video] cinematic path failed: %s", exc)

    if os.getenv("PREMIUM_CARDS", "1") != "0":
        try:
            from content_generator.creative import premium_cards, visual_gate
            recent = visual_gate.recent_layouts()
            for attempt in range(4):
                layout = [l for l in premium_cards.LAYOUTS if l != "split_left"][(day + attempt) % 3]
                out = os.path.join(premium_cards._OUT, f"{label}_day{day}_{date_str}_premium.mp4")
                meta = premium_cards.render_story_video(sku, headline, sub, out, seed=day + attempt,
                                                        seconds=duration or _DEFAULT_STORY_DURATION, layout=layout)
                verdict = visual_gate.evaluate_video(out, meta, recent)
                if verdict["passed"]:
                    visual_gate.remember_layout(layout, label)
                    return out
                logger.warning("[visual-gate] story try %d failed: %s", attempt + 1, verdict["reasons"][:4])
                if visual_gate.is_vision_hold(verdict):
                    break
            logger.error("[visual-gate] premium story held after re-renders; not posting a failing story")
            return None
        except Exception as exc:
            logger.warning("[story_video] premium story path failed: %s", exc)

    try:
        from content_generator.creative.story_motion import render_story_motion
        result = render_story_motion(
            sku=sku, headline=headline, sub=sub, day=day,
            label=f"{label}_day{day}_{date_str}", seconds=duration or _DEFAULT_STORY_DURATION,
        )
        if result and result.get("video") and not result.get("qa"):
            logger.info("[story_video] motion story -> %s (source jar %s)",
                        result["video"], result.get("source_jar"))
            return result["video"]
        if result and result.get("qa"):
            logger.warning("[story_video] motion QA failed: %s — falling back", result["qa"])
    except Exception as exc:
        logger.warning("[story_video] motion path failed: %s", exc)

    paths = frame_paths or ([image_path] if image_path and os.path.exists(image_path) else [])
    if not paths:
        return None
    return _ken_burns(paths, headline, day, duration or 6.0, label, on_date)


def _ken_burns(paths, headline, day, duration, label, on_date) -> str | None:
    try:
        from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
    except Exception as e:
        logger.info("[story_video] moviepy unavailable (%s)", e)
        return None
    clip = audio = None
    try:
        if len(paths) == 1:
            clip = ImageClip(paths[0]).with_duration(duration)
            try:
                clip = clip.resized(lambda t: 1.0 + 0.04 * (t / max(0.1, duration)))
            except Exception:
                pass
        else:
            beat = duration / len(paths)
            clips = []
            for p in paths:
                c = ImageClip(p).with_duration(beat)
                try:
                    c = c.resized(lambda t, d=beat: 1.0 + 0.03 * (t / max(0.1, d)))
                except Exception:
                    pass
                clips.append(c)
            clip = concatenate_videoclips(clips, method="compose")
        music_path = os.getenv("STORY_MUSIC_FILE")
        if not (music_path and os.path.exists(music_path)):
            try:
                from content_generator.creative.audio_director import get_audio_plan
                music_path = get_audio_plan(headline, day).get("local_track")
            except Exception:
                music_path = None
        if music_path and os.path.exists(music_path):
            try:
                audio = AudioFileClip(music_path)
                audio = audio.subclipped(0, min(audio.duration, duration)).with_volume_scaled(1.6)
                clip = clip.with_audio(audio)
            except Exception:
                pass
        os.makedirs(_OUT_DIR, exist_ok=True)
        from content_generator.core.ist_dates import today_ist
        date_str = (on_date.isoformat() if hasattr(on_date, "isoformat")
                    else str(on_date)[:10] if on_date else today_ist().isoformat())
        out_path = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}.mp4")
        temp_audio = os.path.join(_OUT_DIR, f"temp_{label}_{os.getpid()}_{day}.m4a")
        clip.write_videofile(out_path, fps=24, codec="libx264",
                             audio_codec="aac" if clip.audio else None, bitrate="8000k",
                             pixel_format="yuv420p",
                             ffmpeg_params=["-crf", "18", "-movflags", "+faststart"],
                             temp_audiofile=temp_audio, remove_temp=True, logger=None, threads=2)
        return out_path
    except Exception as e:
        logger.warning("[story_video] Ken Burns fallback failed: %s", e)
        return None
    finally:
        for obj in (audio, clip):
            if obj is not None:
                try:
                    obj.close()
                except Exception:
                    pass
