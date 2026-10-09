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


# category -> (local-track mood, human-readable audio direction)
AUDIO_MAP = {
    "coffee_aesthetic": ("lofi", "warm café instrumental or currently rising coffee/lifestyle sound"),
    "morning_routine": ("calm", "soft piano/acoustic sound with a calm morning mood"),
    "productivity": ("upbeat", "light upbeat instrumental with a clean rhythm"),
    "health_wellness": ("calm", "calm ambient audio; keep voice and claims clear"),
    "behind_scenes": ("upbeat", "mid-energy instrumental matched to the cuts"),
    "educational": ("ambient", "low-volume ambient bed; voiceover remains dominant"),
    "founder_story": ("cinematic", "subtle cinematic/emotional bed"),
    "motivation": ("cinematic", "motivational cinematic bed"),
    "product_showcase": ("premium", "premium, rhythmic launch sound"),
    "recipe": ("upbeat", "kitchen ASMR or licensed food-preparation sound"),
    "lifestyle": ("lofi", "aesthetic lifestyle sound with a natural pace"),
    "meme": ("upbeat", "the exact meme sound only after live availability/licensing check"),
    "trend": ("upbeat", "the live-verified audio associated with this format"),
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
