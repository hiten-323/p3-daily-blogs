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


def get_format_audio_plan(format_type: str = "reel", category: str = "coffee_aesthetic", day: int = 0, seconds: float = 10.0) -> dict:
    """Return format-tailored audio plan with downbeat grid and platform loudness filter."""
    fmt = str(format_type or "reel").strip().lower()
    directives = FORMAT_AUDIO_DIRECTIVES.get(fmt, FORMAT_AUDIO_DIRECTIVES["reel"])
    track = select_track_for_format(fmt, category, day)

    # Calculate downbeat grid (e.g. 0.0, 2.0, 4.0, 6.0, 8.0, 10.0 for 120 BPM)
    bar_sec = directives["bar_seconds"]
    downbeats = [round(i * bar_sec, 3) for i in range(int(seconds / bar_sec) + 1) if i * bar_sec <= seconds]

    fade_start = max(0.0, seconds - 0.8)
    af_filter = f"{directives['loudness_filter']},afade=t=in:d=0.2,afade=t=out:st={fade_start:.2f}:d=0.8"

    return {
        "format": fmt,
        "category": category,
        "local_track": track,
        "bpm": directives["target_bpm"],
        "bar_seconds": bar_sec,
        "downbeats": downbeats,
        "loudness_filter": af_filter,
        "description": directives["description"],
    }

