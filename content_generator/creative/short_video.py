"""
Dedicated YouTube Shorts Video Generator — high retention, beat-synced, distinct visual identity.

Distinct from Instagram Reels and Stories:
1. YouTube-native visual language: High-contrast Canary Yellow subtitles, YouTube Shorts eyebrow badge,
   scene progress indicator pill ('PART 1 OF 4').
2. YouTube Shorts narrative pacing: Built directly from yt_short schema scenes (problem -> discovery -> test -> payoff).
3. 120 BPM Musical Downbeat Lock: Each scene is timed to exactly 2.000s (1 full bar at 120 BPM),
   so cuts land precisely on the kick and impact transients for hypnotic retention.
4. Clean export: Outputs short_video_day{day}_{date}.mp4 for priority pickup by YouTube publisher.
"""
from __future__ import annotations
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_SCENE_DURATION = 2.0   # Exactly 1 bar at 120 BPM (0.5s * 4 = 2.0s)
_MAX_SCENES = 6


def _scenes_from_short(yt_short: dict) -> list[dict]:
    """Extract structured scenes from yt_short schema."""
    raw_scenes = yt_short.get("scenes") or []
    scenes = []
    for sc in raw_scenes:
        if isinstance(sc, dict):
            on = str(sc.get("on_screen") or sc.get("headline") or "").strip()
            spoken = str(sc.get("spoken") or sc.get("voiceover") or "").strip()
            if on or spoken:
                scenes.append({"on": on or spoken[:40], "sub": spoken})

    if not scenes:
        hook = str(yt_short.get("hook") or yt_short.get("title") or "READ THE LABEL").strip()
        tagline = str(yt_short.get("tagline") or "The ingredient list is the recipe.").strip()
        product = str(yt_short.get("product") or "").strip()
        from content_generator.creative.cinematic_frame import _product_class
        kind = _product_class(product)
        if kind == "ultra":
            third_on, third_sub = "ULTRA BLEND", "70% coffee. 30% chicory."
        elif kind == "pure":
            third_on, third_sub = (product or "PURE COFFEE").upper(), "pure coffee. Zero chicory."
        else:
            third_on, third_sub = "READ THE LABEL", "Check the blend before you brew."
        scenes = [
            {"on": hook, "sub": tagline},
            {"on": "TURN THE JAR", "sub": "The front is the promise. The back is the recipe."},
            {"on": third_on, "sub": third_sub},
            {"on": "PURITY BEANS", "sub": "Order at p3online.in"},
        ]

    return scenes[:_MAX_SCENES]


def _cinematic(beats, product, day, label, on_date, seconds, format_type="short"):
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


def build_short_video(yt_short: dict, day: int, label: str = "short_video", on_date=None) -> str | None:
    """
    Render a dedicated vertical YouTube Short video (1080x1920 MP4) with beat-synced audio.
    Returns path to rendered MP4 or None.
    """
    if os.getenv("ENABLE_SHORT_VIDEO", "true").lower() != "true":
        return None

    from content_generator.creative.reel_video import resolve_reel_product
    _cin = _cinematic(_scenes_from_short(yt_short), resolve_reel_product(yt_short), day, label, on_date, 12.0, format_type="short")
    if _cin:
        return _cin
    try:
        from moviepy import ImageClip, concatenate_videoclips
    except Exception as e:
        logger.info("[short_video] moviepy unavailable (%s) — skipping YouTube Short video", e)
        return None

    from content_generator.creative.cinematic_frame import compose_cinematic_frame

    scenes = _scenes_from_short(yt_short)
    if not scenes:
        return None

    product = yt_short.get("product")
    total_scenes = len(scenes)
    frame_paths = []

    for i, sc in enumerate(scenes):
        p = compose_cinematic_frame(
            headline=sc["on"],
            sub=sc["sub"],
            day=day,
            idx=i,
            product=product,
            width=1080,
            height=1920,
            label=f"{label}_scene{i}_day{day}",
            format_type="short",
            scene_idx=i,
            total_scenes=total_scenes,
            on_date=on_date,
        )
        if p:
            frame_paths.append(p)

    if not frame_paths:
        return None

    clips = []
    for i, p in enumerate(frame_paths):
        try:
            # Snap scene to 2.000s musical downbeat
            dur = _SCENE_DURATION
            clip = ImageClip(p).with_duration(dur)
            # Dynamic push-in for YouTube retention
            if i % 2 == 0:
                clip = clip.resized(lambda t, d=dur: 1.0 + 0.05 * (t / d))
            else:
                clip = clip.resized(lambda t, d=dur: 1.05 - 0.04 * (t / d))
            clips.append(clip)
        except Exception as e:
            logger.debug("[short_video] scene clip build failed: %s", e)

    if not clips:
        return None

    try:
        video = concatenate_videoclips(clips, method="compose")
    except Exception:
        video = concatenate_videoclips(clips)

    # Attach 120 BPM beat-synced audio
    music = os.getenv("SHORT_MUSIC_FILE")
    if not (music and os.path.exists(music)):
        try:
            from content_generator.creative.audio_director import get_audio_plan
            hook = str(yt_short.get("hook") or yt_short.get("tagline") or "")
            music = get_audio_plan(hook, day).get("local_track")
        except Exception as e:
            logger.debug("[short_video] audio selection skipped: %s", e)

    if music and os.path.exists(music):
        try:
            from moviepy import AudioFileClip
            audio = AudioFileClip(music)
            dur = min(audio.duration, video.duration)
            audio = audio.subclipped(0, dur)
            try:
                audio = audio.with_volume_scaled(1.8)
            except Exception as ve:
                logger.debug("[short_video] volume scaling failed: %s", ve)
            video = video.with_audio(audio)
        except Exception as e:
            logger.debug("[short_video] music attach failed: %s", e)

    os.makedirs(_OUT_DIR, exist_ok=True)
    from content_generator.core.ist_dates import today_ist
    if on_date is None:
        date_str = today_ist().isoformat()
    elif hasattr(on_date, "isoformat"):
        date_str = on_date.isoformat()
    else:
        date_str = str(on_date)[:10]
    out = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}.mp4")

    temp_audio = os.path.join(_OUT_DIR, f"temp_{label}_{os.getpid()}_{day}.m4a")
    try:
        video.write_videofile(
            out,
            fps=24,
            codec="libx264",
            audio_codec="aac" if video.audio else None,
            bitrate="10000k",
            pixel_format="yuv420p",
            ffmpeg_params=["-crf", "18", "-movflags", "+faststart"],
            temp_audiofile=temp_audio,
            remove_temp=True,
            logger=None,
            threads=2,
        )
        logger.info("[short_video] Rendered %.1fs YouTube Short -> %s", video.duration, out)
        return out
    except Exception as e:
        logger.warning("[short_video] render failed: %s", e)
        return None
    finally:
        try:
            video.close()
        except Exception:
            pass
