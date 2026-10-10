"""
Dynamic vertical Story Video generator with audio for Instagram Stories.

Turns a safe-zone compliant cinematic story frame into an engaging 9:16 vertical
MP4 story video (7-8 seconds) with gentle Ken Burns motion and royalty-free
background audio from music_library/.

This enables Instagram Stories to play with full sound and motion rather than
being a silent, static, flat image.
"""
from __future__ import annotations
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_DEFAULT_STORY_DURATION = 7.5


def build_story_video(
    image_path: str,
    headline: str = "",
    day: int = 0,
    duration: float = _DEFAULT_STORY_DURATION,
    label: str = "story_video",
) -> str | None:
    """
    Render a 7-8s dynamic vertical story video (1080x1920 MP4) with audio.
    Returns the path to the MP4 file or None on failure/unavailability.
    """
    if not image_path or not os.path.exists(image_path):
        logger.warning("[story_video] Base image path does not exist: %s", image_path)
        return None

    if os.getenv("ENABLE_STORY_VIDEO", "true").lower() != "true":
        logger.info("[story_video] Story video disabled via ENABLE_STORY_VIDEO=false")
        return None

    try:
        from moviepy import ImageClip, AudioFileClip
    except Exception as e:
        logger.info("[story_video] moviepy unavailable (%s) — skipping story video", e)
        return None

    clip = None
    audio = None
    try:
        clip = ImageClip(image_path).with_duration(duration)
        
        # Subtle Ken Burns zoom: 1.0 to 1.03 scale over duration
        try:
            clip = clip.resized(lambda t: 1.0 + 0.03 * (t / max(0.1, duration)))
        except Exception as ze:
            logger.debug("[story_video] zoom effect skipped: %s", ze)

        # Audio track selection: Audio Director mood-matched royalty-free track
        music_path = os.getenv("STORY_MUSIC_FILE")
        if not (music_path and os.path.exists(music_path)):
            try:
                from content_generator.creative.audio_director import get_audio_plan
                music_path = get_audio_plan(headline, day).get("local_track")
            except Exception as ae:
                logger.debug("[story_video] audio director skipped: %s", ae)

        if music_path and os.path.exists(music_path):
            try:
                audio = AudioFileClip(music_path)
                dur = min(audio.duration, duration)
                audio = audio.subclipped(0, dur)
                clip = clip.with_audio(audio)
            except Exception as me:
                logger.debug("[story_video] audio attach skipped: %s", me)

        os.makedirs(_OUT_DIR, exist_ok=True)
        from content_generator.core.ist_dates import today_ist
        date_str = today_ist().isoformat()
        out_path = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}.mp4")

        clip.write_videofile(
            out_path,
            fps=24,
            codec="libx264",
            audio_codec="aac" if clip.audio else None,
            logger=None,
            threads=2,
        )
        logger.info("[story_video] Rendered %.1fs story video -> %s", clip.duration, out_path)
        return out_path
    except Exception as e:
        logger.warning("[story_video] video render failed: %s", e)
        return None
    finally:
        if audio is not None:
            try:
                audio.close()
            except Exception:
                pass
        if clip is not None:
            try:
                clip.close()
            except Exception:
                pass
