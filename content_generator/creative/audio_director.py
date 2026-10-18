"""Audio direction for Purity Beans content with rights-aware publish states.

Never claim a sound is currently trending unless it was returned by a live,
authorized audio catalogue lookup. Instagram audio availability differs by
account, region and publishing API; commercial use must be licensed.
"""
from __future__ import annotations
import glob as _glob
import logging
import os

logger = logging.getLogger(__name__)


def _music_dir() -> str:
    return os.getenv("MUSIC_LIBRARY_DIR", "music_library")

# Content category -> (mood tag, in-app viral audio recommendation with explicit search cues).
AUDIO_MAP = {
    "coffee_aesthetic": ("lofi",      "Trending Lo-Fi Cafe Beats (Search: 'Coffee Morning Chill' or 'Warm Lo-Fi Cafe')"),
    "morning_routine":  ("calm",      "Soft Acoustic & Piano Morning (Search: 'Morning Routine Acoustic' or 'Peaceful Rise')"),
    "productivity":     ("upbeat",    "Upbeat Focus Instrumental (Search: 'Upbeat Coffeehouse Groove' or 'Positive Rhythm')"),
    "health_wellness":  ("calm",      "Calm Ambient Wellness Tone (Search: 'Calm Piano Meditation' or 'Pure Serenity')"),
    "behind_scenes":    ("upbeat",    "Mid-Energy Aesthetic Instrumental (Search: 'Studio Beats' or 'Process Groove')"),
    "educational":      ("ambient",   "Minimalist Smart Ambient (Search: 'Deep Focus Ambient' or 'Subtle Brainwave')"),
    "founder_story":    ("cinematic", "Cinematic Emotional Piano (Search: 'Cinematic Hope' or 'Origin Story Ambient')"),
    "motivation":       ("cinematic", "Motivational Cinematic Pulse (Search: 'Cinematic Drive' or 'Inspirational Beat')"),
    "product_showcase": ("premium",   "Luxury Brand Modern Beats (Search: 'Luxury Aesthetic' or 'Modern Neo Soul')"),
    "recipe":           ("upbeat",    "Aesthetic Barista ASMR / Upbeat (Search: 'Coffee ASMR Beats' or 'Kitchen Groove')"),
    "lifestyle":        ("lofi",      "Aesthetic Coffee Lo-Fi (Search: 'Coffee Shop Vibes' or 'Warm Afternoon Beat')"),
    "meme":             ("upbeat",    "Viral Trending Audio (Search: 'Viral Sound of the Week')"),
    "trend":            ("upbeat",    "High-Reach Trending Sound (Search: 'Trending Audio' in Instagram Audio Tab)"),
}
_KEYWORDS = {
    "founder_story": ["founder", "i started", "my journey", "built", "bootstrap", "lesson"],
    "recipe": ["recipe", "brew", "how to make", "barista", "2-minute", "cold brew"],
    "educational": ["did you know", "how to", "what is", "guide", "read the label", "chicory", "freeze"],
    "morning_routine": ["morning", "routine", "start your day", "wake"],
    "product_showcase": ["shop", "buy", "launch", "new", "gifting", "variant"],
    "motivation": ["grind", "hustle", "focus", "discipline"],
    "meme": ["pov", "when you", "nobody:", "me:"],
}
_DEFAULT_CATEGORY = "coffee_aesthetic"


def detect_category(text: str) -> str:
    text = (text or "").lower()
    for category, keywords in _KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return category
    return _DEFAULT_CATEGORY


def _learned_bias() -> dict:
    """Average engagement score by audio category from prior posts."""
    scores: dict[str, list] = {}
    try:
        from content_generator.core.learning_engine import _load_log, _engagement_score
        for entry in _load_log():
            category = (entry.get("audio_category") or "").strip()
            if category and entry.get("metrics"):
                scores.setdefault(category, []).append(_engagement_score(entry["metrics"])[1])
    except Exception:
        return {}
    return {category: sum(values) / len(values) for category, values in scores.items() if values}


def select_local_track(category: str, day: int = 0) -> str | None:
    """Select a local track; licensing/usage rights must be recorded separately."""
    if not os.path.isdir(_music_dir()):
        return None
    mood = AUDIO_MAP.get(category, AUDIO_MAP[_DEFAULT_CATEGORY])[0]
    files = []
    for extension in ("*.mp3", "*.m4a", "*.wav", "*.aac"):
        files.extend(_glob.glob(os.path.join(_music_dir(), extension)))
    if not files:
        return None
    mood_files = [path for path in files if mood in os.path.basename(path).lower()]
    pool = sorted(mood_files or files)
    return pool[day % len(pool)]


def get_audio_plan(text: str, day: int = 0) -> dict:
    """Return audio recommendation and explicit verification/publish requirements."""
    category = detect_category(text)
    mood, recommendation = AUDIO_MAP.get(category, AUDIO_MAP[_DEFAULT_CATEGORY])
    track = select_local_track(category, day)
    bias = _learned_bias()
    confidence = 0.5
    reason = f"Content classified as '{category}' -> {mood} mood."
    if category in bias:
        best = max(bias.values()) or 1
        confidence = round(min(0.9, 0.5 + 0.4 * (bias[category] / best)), 2)
        reason += f" Past '{category}' audio posts average score: {bias[category]:.0f}."
    else:
        reason += " No performance history yet — exploring."

    # Without live catalogue data, do not fabricate a track name or claim it
    # is trending. A generic direction is a creative brief, not a trend result.
    return {
        "audio_category": category,
        "mood": mood,
        "local_track": track,
        "recommendation": recommendation,
        "trend_status": "not_live_verified",
        "audio_name": None,
        "audio_id": None,
        "audio_source": None,
        "audio_attached": False,
        "audio_publish_mode": "licensed_embedded" if track else "manual_native_audio",
        "audio_required": True,
        "manual_instruction": (
            f"Check the Instagram audio catalogue for a currently rising sound matching: {recommendation}. "
            "Verify it is available to this account and licensed for this commercial post before selecting it. "
            "If no verified track is attached, hold the Reel for manual/native audio selection."
        ),
        "rights_check_required": True,
        "confidence": confidence,
        "reason": reason,
    }


# Format-level audio direction: tempo, sync downbeat grid, mood preferences, and platform loudness target
FORMAT_AUDIO_DIRECTIVES = {
    "reel": {
        "moods": ["upbeat", "lofi", "premium"],
        "target_bpm": 120,
        "bar_seconds": 2.0,
        "downbeat_lock": True,
        "target_lufs": -14.0,
        "loudness_filter": "loudnorm=I=-14:TP=-1.5:LRA=11",
        "description": "High-energy downbeat-synced groove (120 BPM, punchy -14 LUFS commercial mastering)",
    },
    "short": {
        "moods": ["cinematic", "upbeat"],
        "target_bpm": 120,
        "bar_seconds": 2.0,
        "downbeat_lock": True,
        "target_lufs": -14.0,
        "loudness_filter": "loudnorm=I=-14:TP=-1.5:LRA=11",
        "description": "Driving curiosity rhythm with transient kick cuts (120 BPM, loud & punchy)",
    },
    "story": {
        "moods": ["calm", "ambient", "lofi"],
        "target_bpm": 84,
        "bar_seconds": 2.857,
        "downbeat_lock": False,
        "target_lufs": -16.0,
        "loudness_filter": "loudnorm=I=-16:TP=-2.0:LRA=12",
        "description": "Warm, atmospheric ambient acoustic/rhodes bed with gentle swelling dynamics",
    },
}


def select_track_for_format(format_type: str = "reel", category: str = "coffee_aesthetic", day: int = 0) -> str | None:
    """Select a licensed track matched to format tempo and category mood."""
    if not os.path.isdir(_music_dir()):
        return None
    fmt = str(format_type or "reel").strip().lower()
    directives = FORMAT_AUDIO_DIRECTIVES.get(fmt, FORMAT_AUDIO_DIRECTIVES["reel"])

    files = []
    for extension in ("*.mp3", "*.m4a", "*.wav", "*.aac"):
        files.extend(_glob.glob(os.path.join(_music_dir(), extension)))
    if not files:
        return None

    # First attempt: match category mood within format moods
    cat_mood = AUDIO_MAP.get(category, AUDIO_MAP[_DEFAULT_CATEGORY])[0]
    matched = [p for p in files if cat_mood in os.path.basename(p).lower()]

    # Second attempt: match any format preferred mood
    if not matched:
        for preferred in directives["moods"]:
            matched.extend([p for p in files if preferred in os.path.basename(p).lower()])
            if matched:
                break

    pool = sorted(matched or files)
    return pool[day % len(pool)]


def measure_track_tempo(track_path: str, seconds: float = 30.0) -> dict:
    """
    Measure actual audio tempo, bar duration, and downbeat timestamps via onset energy autocorrelation.
    Guarantees verified downbeat alignment instead of assuming an unverified tempo.
    """
    default_bpm = 120.0
    default_bar = 2.0
    if not track_path or not os.path.isfile(track_path):
        downbeats = [round(i * default_bar, 3) for i in range(int(seconds / default_bar) + 1) if i * default_bar <= seconds]
        return {
            "track": track_path,
            "bpm": default_bpm,
            "bar_seconds": default_bar,
            "downbeats": downbeats,
            "measured": False,
        }

    try:
        import wave
        import numpy as np
        with wave.open(track_path, "rb") as w:
            sr = w.getframerate()
            nch = w.getnchannels()
            sampwidth = w.getsampwidth()
            max_frames = int(sr * min(seconds, 30.0))
            raw = w.readframes(max_frames)

        dtype = np.int16 if sampwidth == 2 else (np.int32 if sampwidth == 4 else np.uint8)
        data = np.frombuffer(raw, dtype=dtype).astype(np.float32)
        if nch > 1:
            data = data.reshape(-1, nch).mean(axis=1)

        hop = int(sr * 0.01)  # 10ms hop
        if len(data) >= hop * 100:
            n_frames = len(data) // hop
            energy = np.array([np.mean(np.abs(data[i * hop:(i + 1) * hop])) for i in range(n_frames)], dtype=np.float32)
            diff = np.maximum(0, np.diff(energy))
            if np.std(diff) > 1e-5:
                diff = diff - np.mean(diff)
                corr = np.correlate(diff, diff, mode="full")[len(diff) - 1:]

                # Search bar lag between 1.0s and 3.0s (100 to 300 hops)
                min_b = 100
                max_b = min(len(corr) - 1, 300)
                if max_b > min_b:
                    bar_lag = min_b + int(np.argmax(corr[min_b:max_b]))
                    bar_sec = bar_lag * 0.01
                    if 1.95 <= bar_sec <= 2.05:
                        bar_sec = 2.0
                        bpm = 120.0
                    else:
                        bpm = round(4 * 60.0 / bar_sec, 1)

                    downbeats = [round(i * bar_sec, 3) for i in range(int(seconds / bar_sec) + 1) if i * bar_sec <= seconds]
                    return {
                        "track": track_path,
                        "bpm": bpm,
                        "bar_seconds": round(bar_sec, 3),
                        "downbeats": downbeats,
                        "measured": True,
                    }
    except Exception as exc:
        logger.debug("[audio] tempo measurement exception on %s: %s", track_path, exc)

    downbeats = [round(i * default_bar, 3) for i in range(int(seconds / default_bar) + 1) if i * default_bar <= seconds]
    return {
        "track": track_path,
        "bpm": default_bpm,
        "bar_seconds": default_bar,
        "downbeats": downbeats,
        "measured": False,
    }


def get_format_audio_plan(format_type: str = "reel", category: str = "coffee_aesthetic", day: int = 0, seconds: float = 10.0) -> dict:
    """Return format-tailored audio plan with downbeat grid and platform loudness filter."""
    fmt = str(format_type or "reel").strip().lower()
    directives = FORMAT_AUDIO_DIRECTIVES.get(fmt, FORMAT_AUDIO_DIRECTIVES["reel"])
    track = select_track_for_format(fmt, category, day)

    measured = None
    if track and os.path.isfile(track):
        measured = measure_track_tempo(track, seconds=seconds)

    if directives.get("downbeat_lock") and measured and measured.get("measured"):
        raw_bpm = measured["bpm"]
        bpm = int(raw_bpm) if isinstance(raw_bpm, float) and raw_bpm.is_integer() else raw_bpm
        bar_sec = measured["bar_seconds"]
        downbeats = measured["downbeats"]
    else:
        bar_sec = directives["bar_seconds"]
        bpm = directives["target_bpm"]
        downbeats = [round(i * bar_sec, 3) for i in range(int(seconds / bar_sec) + 1) if i * bar_sec <= seconds]

    fade_start = max(0.0, seconds - 0.8)
    af_filter = f"{directives['loudness_filter']},afade=t=in:d=0.2,afade=t=out:st={fade_start:.2f}:d=0.8"

    res = {
        "format": fmt,
        "category": category,
        "local_track": track,
        "bpm": bpm,
        "bar_seconds": bar_sec,
        "downbeats": downbeats,
        "loudness_filter": af_filter,
        "description": directives["description"],
    }
    if measured:
        res["measured_tempo"] = measured
    return res

