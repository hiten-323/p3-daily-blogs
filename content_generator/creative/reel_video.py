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
_BEAT_SECONDS = 2.6
_MAX_BEATS    = 8


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
        hook = str(reel.get("hook_text") or reel.get("hook") or "REAL COFFEE. ZERO CHICORY.")
        beats = [
            {"on": hook, "sub": ""},
            {"on": "NO CHICORY", "sub": "100% coffee. Nothing else."},
            {"on": "PURITY BEANS", "sub": "Shop at p3online.in"},
        ]
    return beats[:_MAX_BEATS]


def build_reel_video(reel: dict, day: int, label: str = "reel_video") -> str | None:
    """
    Render a vertical motion reel. Returns mp4 path or None (caller falls back
    to an image post).
    """
    if os.getenv("ENABLE_REEL_VIDEO", "true").lower() != "true":
        return None
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

    beats = _beats_from_reel(reel)
    frame_paths = []
    for i, b in enumerate(beats):
        p = _frame(
            headline=b["on"], sub=b["sub"], day=day, idx=i,
            width=1080, height=1920, label=f"{label}_beat{i}_day{day}",
        ) if _frame.__name__ == "compose_cinematic_frame" else _frame(
            headline=b["on"], body=b["sub"], day=day, idx=i,
            width=1080, height=1920, label=f"{label}_beat{i}_day{day}",
        )
        if p:
            frame_paths.append(p)
    if not frame_paths:
        return None

    dirs = {}
    try:
        from content_generator.analytics.creative_post_audit import get_visual_adaptation_directives
        lower_label = str(label or "").lower()
        target_platform = "youtube" if ("youtube" in lower_label or "yt_" in lower_label or "short" in lower_label) else "instagram"
        dirs = get_visual_adaptation_directives(platform=target_platform)
    except Exception:
        dirs = {}

    boost_motion = dirs.get("boost_motion", True)

    clips = []
    for i, p in enumerate(frame_paths):
        try:
            dur = 2.0 if (i == 0 and boost_motion) else _BEAT_SECONDS
            clip = ImageClip(p).with_duration(dur)
            # Dynamic Ken Burns motion: hook beat punchy scale, alternating beats push-in/push-out
            try:
                if boost_motion:
                    if i % 2 == 0:
                        clip = clip.resized(lambda t, d=dur: 1.0 + 0.10 * (t / d))
                    else:
                        clip = clip.resized(lambda t, d=dur: 1.08 - 0.06 * (t / d))
                else:
                    clip = clip.resized(lambda t, d=dur: 1.0 + 0.05 * (t / d))
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
            video = video.with_audio(audio)
        except Exception as e:
            logger.debug("[reel_video] music attach failed: %s", e)

    os.makedirs(_OUT_DIR, exist_ok=True)
    from content_generator.core.ist_dates import today_ist
    date_str = today_ist().isoformat()
    out = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}.mp4")
    try:
        video.write_videofile(out, fps=24, codec="libx264", audio_codec="aac",
                              logger=None, threads=2)
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
