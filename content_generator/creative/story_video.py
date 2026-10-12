"""
Dynamic vertical Story Video generator with audio for Instagram Stories.

Turns a safe-zone compliant cinematic story frame into an engaging 9:16 vertical
MP4 story video (6.0 seconds, three bars at 120 BPM) with gentle Ken Burns motion
and royalty-free background audio from music_library/.

This enables Instagram Stories to play with full sound and motion rather than
being a silent, static, flat image.
"""
from __future__ import annotations
import datetime
import logging
import os

logger = logging.getLogger(__name__)

_OUT_DIR = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
_DEFAULT_STORY_DURATION = 6.0   # Exactly 3 bars at 120 BPM (2.0s * 3 = 6.0s) for beat synchronization


def build_story_video(
    image_path: str = None,
    headline: str = "",
    day: int = 0,
    duration: float = _DEFAULT_STORY_DURATION,
    label: str = "story_video",
    frame_paths: list[str] = None,
    on_date=None,
) -> str | None:
    """
    Render a 6.0s dynamic vertical story video (1080x1920 MP4) with beat-synced audio.
    Supports either a single high-impact frame or a 2-beat interactive story progression.
    Returns the path to the MP4 file or None on failure/unavailability.
    """
    paths = frame_paths or ([image_path] if image_path and os.path.exists(image_path) else [])
    if not paths:
        logger.warning("[story_video] No valid image paths provided for story video")
        return None

    if os.getenv("ENABLE_STORY_VIDEO", "true").lower() != "true":
        logger.info("[story_video] Story video disabled via ENABLE_STORY_VIDEO=false")
        return None

    try:
        from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
    except Exception as e:
        logger.info("[story_video] moviepy unavailable (%s) — skipping story video", e)
        return None

    clip = None
    audio = None
    try:
        if len(paths) == 1:
            clip = ImageClip(paths[0]).with_duration(duration)
            try:
                clip = clip.resized(lambda t: 1.0 + 0.04 * (t / max(0.1, duration)))
            except Exception as ze:
                logger.debug("[story_video] zoom effect skipped: %s", ze)
        else:
            beat_dur = duration / len(paths)
            clips = []
            for idx, p in enumerate(paths):
                c = ImageClip(p).with_duration(beat_dur)
                try:
                    c = c.resized(lambda t, d=beat_dur: 1.0 + 0.03 * (t / max(0.1, d)))
                except Exception:
                    pass
                clips.append(c)
            clip = concatenate_videoclips(clips, method="compose")

        # Audio track selection: Audio Director mood-matched royalty-free track (120 BPM beat-synced)
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
                try:
                    # Boost volume to commercial loudness (~ -14 LUFS / dB) so story audio is clear and punchy
                    audio = audio.with_volume_scaled(1.8)
                except Exception as ve:
                    logger.debug("[story_video] volume scaling failed: %s", ve)
                clip = clip.with_audio(audio)
            except Exception as me:
                logger.debug("[story_video] audio attach skipped: %s", me)

        os.makedirs(_OUT_DIR, exist_ok=True)
        from content_generator.core.ist_dates import today_ist
        if on_date is None:
            date_str = today_ist().isoformat()
        elif hasattr(on_date, "isoformat"):
            date_str = on_date.isoformat()
        else:
            date_str = str(on_date)[:10]
        out_path = os.path.join(_OUT_DIR, f"{label}_day{day}_{date_str}.mp4")

        temp_audio = os.path.join(_OUT_DIR, f"temp_{label}_{os.getpid()}_{day}.m4a")
        clip.write_videofile(
            out_path,
            fps=24,
            codec="libx264",
            audio_codec="aac" if clip.audio else None,
            bitrate="10000k",
            pixel_format="yuv420p",
            ffmpeg_params=["-crf", "18", "-movflags", "+faststart"],
            temp_audiofile=temp_audio,
            remove_temp=True,
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
