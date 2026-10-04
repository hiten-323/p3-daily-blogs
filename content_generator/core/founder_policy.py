"""
Founder Policy Engine + Version Manager — steer the engine by config, not prompts.

The founder edits founder_policies.yaml. Every pipeline step reads policy here.
Missing file/keys fall back to safe defaults, so a bad edit never breaks a run.

Domain-structured (business / content / brand / marketing / quality /
publishing / experiments) with a version block. Backward-compatible flat
accessors are provided so existing callers keep working:

    policy().target_kpi          # -> business.target_kpi
    policy().auto_publish         # -> content.auto_publish
    policy().priority_segments    # -> marketing.priority_segments
    policy().strategy_bias()      # prompt-injectable directive
    policy().version              # "1.0"

Version Manager: record_policy_version() logs each new version with its
effective date to output/learning/policy_history.json, so performance can be
traced back to the policy that produced it (every asset stamps policy_version).
"""
from __future__ import annotations
from content_generator.core.ist_dates import today_ist
import datetime
import json
import logging
import os

logger = logging.getLogger(__name__)


def _policy_path() -> str:
    return os.getenv("FOUNDER_POLICY_FILE", "founder_policies.yaml")


def _history_path() -> str:
    learning = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
    return os.path.join(learning, "policy_history.json")


# Domain-structured defaults (mirror founder_policies.yaml)
_DEFAULTS = {
    "version": {"number": "1.0", "effective_date": "", "author": "Founder", "changes": []},
    "business": {"objective": "growth", "target_kpi": "followers"},
    "content":  {"auto_publish": True, "reels_per_day": 1, "blogs_per_week": 7,
                 "require_real_jar": True,
                 "enable_extended_content": True,
                 "core_avatar": "Urban Indian coffee drinker, 22-40, who cares about what they consume",
                 "core_topic_lane": "The truth about instant coffee quality and how to drink better coffee"},
    "brand":    {"premium": True, "aggressive_sales": False, "educational": True,
                 "creator_dna": "We are Purity Beans. We make 100% pure instant coffee for "
                                "Indians who are done being fooled by chicory-filled 'coffee'. "
                                "Listen to us because we print exactly what's inside — and dare "
                                "you to read any other label."},
    "marketing": {"priority_segments": ["general"], "active_campaign_override": ""},
    "quality":  {"minimum_score": 8.0, "legal_risk_threshold": 0.25, "plagiarism_threshold": 0},
    "publishing": {"instagram": True, "facebook": True, "linkedin": True, "youtube": True,
                   "max_daily_posts": {"instagram": 3, "facebook": 2, "linkedin": 1, "youtube": 1}},
    "experiments": {"enabled": True, "max_parallel": 2},
}

# Backward-compat flat keys -> (domain, key)
_FLAT_MAP = {
    "target_kpi":             ("business", "target_kpi"),
    "objective":              ("business", "objective"),
    "auto_publish":           ("content", "auto_publish"),
    "require_real_jar":       ("content", "require_real_jar"),
    "enable_extended_content": ("content", "enable_extended_content"),
    "priority_segments":      ("marketing", "priority_segments"),
    "active_campaign_override": ("marketing", "active_campaign_override"),
    "legal_risk_threshold":   ("quality", "legal_risk_threshold"),
    "minimum_score":          ("quality", "minimum_score"),
    "max_daily_posts":        ("publishing", "max_daily_posts"),
}


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class FounderPolicy:
    def __init__(self, data: dict):
        self._d = data

    # ── access ────────────────────────────────────────────────────────────────

    def domain(self, name: str) -> dict:
        return self._d.get(name, _DEFAULTS.get(name, {}))

    @property
    def version(self) -> str:
        return str(self._d.get("version", {}).get("number", "1.0"))

    @property
    def brand_voice(self) -> dict:
        return self.domain("brand")

    def __getattr__(self, name):
        if name in _FLAT_MAP:
            dom, key = _FLAT_MAP[name]
            return self._d.get(dom, {}).get(key, _DEFAULTS[dom][key])
        raise AttributeError(name)

    def get(self, key, default=None):
        if key in _FLAT_MAP:
            dom, k = _FLAT_MAP[key]
            return self._d.get(dom, {}).get(k, _DEFAULTS[dom].get(k, default))
        return self._d.get(key, _DEFAULTS.get(key, default))

    # ── derived (what the pipeline consumes) ─────────────────────────────────

    def strategy_bias(self) -> str:
        kpi = self.get("target_kpi", "followers")
        voice = self.domain("brand")
        segs = ", ".join(self.get("priority_segments", ["general"]))
        campaign = self.get("active_campaign_override", "")

        kpi_line = {
            "followers":  "Optimize for FOLLOWER GROWTH — shareable, non-salesy value.",
            "engagement": "Optimize for ENGAGEMENT — comments, saves, conversation.",
            "revenue":    "Optimize for REVENUE — route qualified attention to purchase.",
        }.get(kpi, "Optimize for FOLLOWER GROWTH.")

        tone = []
        if voice.get("premium", True):
            tone.append("premium/editorial")
        if voice.get("educational", True):
            tone.append("educational")
        tone.append("assertive sales" if voice.get("aggressive_sales") else "value-first (soft CTAs)")

        bits = [f"FOUNDER POLICY v{self.version}: {kpi_line}",
                "Voice: " + ", ".join(tone) + ".",
                f"Prioritize speaking to: {segs}."]
        if campaign:
            bits.append(f"Active campaign focus: {campaign}.")
        return " ".join(bits)

    def as_dict(self) -> dict:
        return dict(self._d)


_cached: FounderPolicy | None = None


def load_policy(force: bool = False) -> FounderPolicy:
    global _cached
    if _cached is not None and not force:
        return _cached
    data = json.loads(json.dumps(_DEFAULTS))   # deep copy
    path = _policy_path()
    try:
        if os.path.exists(path):
            import yaml
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            if isinstance(loaded, dict):
                data = _deep_merge(data, loaded)
            logger.info("[policy] Loaded v%s (kpi=%s, auto_publish=%s, extended=%s)",
                        data.get("version", {}).get("number"),
                        data.get("business", {}).get("target_kpi"),
                        data.get("content", {}).get("auto_publish"),
                        data.get("content", {}).get("enable_extended_content"))
        else:
            logger.info("[policy] No founder_policies.yaml — safe defaults")
    except Exception as e:
        logger.warning("[policy] Could not read %s (%s) — defaults", path, e)
    _cached = FounderPolicy(data)
    return _cached


def policy() -> FounderPolicy:
    return load_policy()


# ── Version Manager ──────────────────────────────────────────────────────────

def record_policy_version() -> dict:
    """
    Log the current policy version + effective date the first time it is seen.
    Builds an audit trail (policy_history.json) linking version -> date range,
    so performance reviews can attribute results to the policy in force.
    """
    p = load_policy()
    ver_block = p.as_dict().get("version", {})
    number = str(ver_block.get("number", "1.0"))

    hist_path = _history_path()
    history = []
    if os.path.exists(hist_path):
        try:
            with open(hist_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    if history and str(history[-1].get("number")) == number:
        return history[-1]   # already recorded

    record = {
        "number":         number,
        "effective_date": ver_block.get("effective_date") or today_ist().isoformat(),
        "author":         ver_block.get("author", "Founder"),
        "changes":        ver_block.get("changes", []),
        "recorded_at":    datetime.datetime.now().isoformat(timespec="seconds"),
        "snapshot":       {"target_kpi": p.get("target_kpi"),
                           "auto_publish": p.get("auto_publish"),
                           "enable_extended_content": p.get("enable_extended_content"),
                           "priority_segments": p.get("priority_segments")},
    }
    history.append(record)
    os.makedirs(os.path.dirname(hist_path), exist_ok=True)
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(history[-100:], f, indent=2, ensure_ascii=False)
    logger.info("[policy] Recorded new policy version %s", number)
    return record
