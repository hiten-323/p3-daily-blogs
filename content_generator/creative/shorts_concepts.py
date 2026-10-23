"""Daily concept library + no-repeat rotation for YouTube Shorts and IG Reels.

Hiten: "all the shorts look alike; every day they should feel different with a
new video background and an awe factor that urges viewers to follow."

Each concept is a distinct cinematic background world (scene), with its own
camera motion, palette tone (applied on top of the jar-label palette from
premium_cards.PALETTES, so colours still belong to the jar), jar layout,
beat transition, music mood, first-second hook lines and an AI video prompt
for providers that can generate a fresh background clip.

Rotation rules (persisted in output/learning/concept_history.json):
  * no concept, layout or motion repeats within ROTATION_DAYS for a format
  * the Short and the Reel on the same day never share concept/layout/motion
  * hook text is not reused within HOOK_DAYS for a format

Real jar cutouts only: concepts describe the BACKGROUND. AI prompts explicitly
forbid jars, packaging, text and logos; the official jar is composited on top.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os

logger = logging.getLogger(__name__)

ROTATION_DAYS = int(os.getenv("CONCEPT_ROTATION_DAYS", "7"))
HOOK_DAYS = int(os.getenv("CONCEPT_HOOK_DAYS", "14"))
HISTORY_PATH = os.path.join("output", "learning", "concept_history.json")

# Jar layouts (more than ROTATION_DAYS + 1 so a 7-day no-repeat is always satisfiable).
# horizon = surface line (fraction of H); cx = jar centre x; scale = jar height multiplier;
# light = key-light path (x0, y0, x1, y1) as fractions.
LAYOUTS = {
    "hero_center":   dict(horizon=0.74, cx=0.50, scale=1.00, light=(0.25, 0.30, 0.75, 0.40)),
    "low_wide":      dict(horizon=0.79, cx=0.50, scale=0.92, light=(0.75, 0.25, 0.30, 0.42)),
    "offset_right":  dict(horizon=0.75, cx=0.58, scale=0.94, light=(0.20, 0.22, 0.45, 0.40)),
    "offset_left":   dict(horizon=0.75, cx=0.42, scale=0.94, light=(0.80, 0.22, 0.55, 0.40)),
    "high_horizon":  dict(horizon=0.70, cx=0.50, scale=0.90, light=(0.50, 0.12, 0.50, 0.35)),
    "monument":      dict(horizon=0.80, cx=0.50, scale=1.06, light=(0.50, 0.30, 0.50, 0.30)),
    "far_stage":     dict(horizon=0.77, cx=0.50, scale=0.80, light=(0.15, 0.40, 0.85, 0.40)),
    "rule_thirds_r": dict(horizon=0.76, cx=0.62, scale=0.88, light=(0.10, 0.20, 0.40, 0.45)),
    "rule_thirds_l": dict(horizon=0.76, cx=0.38, scale=0.88, light=(0.90, 0.20, 0.60, 0.45)),
}

MOTIONS = ("push_in", "pull_out", "orbit", "parallax_pan_l", "parallax_pan_r",
           "rack_focus", "speed_ramp", "crane_up", "dolly_zoom")
TRANSITIONS = ("flash", "whip", "dissolve", "zoom_punch", "light_leak")

# music_library tracks by mood
MUSIC = {
    "cinematic": "cinematic_origin.wav", "jazz": "premium_jazz.wav", "lofi": "lofi_cafe.wav",
    "ambient": "ambient_lounge.wav", "upbeat": "upbeat_roast.wav", "calm": "calm_morning.wav",
}

_NO_JAR = ("no jar, no packaging, no bottle, no label, no text, no logo, no people, no hands, "
           "empty negative space in the lower centre for a product to be placed, vertical 9:16, "
           "photoreal, shallow depth of field, cinematic grade")

# scene = procedural renderer style (cinematic_motion._Backdrop); tone = palette transform.
CONCEPTS: list[dict] = [
    dict(id="granule_dissolve", name="Macro granules dissolving in slow-mo", scene="granules",
         motions=("push_in", "speed_ramp", "rack_focus"), tone="rich", transition="zoom_punch", music="cinematic",
         hooks=("Watch it melt in 3 seconds", "This is what instant should look like", "Slow-mo. Zero clumps."),
         ai_prompt="extreme macro slow motion of dark coffee granules falling and dissolving into hot water, amber backlight"),
    dict(id="steam_backlight", name="Steam curling in backlight", scene="steam",
         motions=("crane_up", "push_in", "rack_focus"), tone="noir", transition="dissolve", music="ambient",
         hooks=("Wait for the steam", "The first sip starts here", "Morning, but make it cinematic"),
         ai_prompt="thick white steam curling upward against a strong warm backlight in a dark room, slow motion"),
    dict(id="crema_swirl", name="Pour and crema swirl", scene="swirl",
         motions=("orbit", "push_in", "dolly_zoom"), tone="golden", transition="whip", music="jazz",
         hooks=("That swirl though", "Stir once. Fall in love.", "Crema mood, every cup"),
         ai_prompt="top-down slow motion of milk pouring into coffee creating a hypnotic crema swirl, warm tones"),
    dict(id="golden_hour_kitchen", name="Golden-hour kitchen light sweep", scene="light_sweep",
         motions=("parallax_pan_r", "pull_out", "crane_up"), tone="golden", transition="light_leak", music="calm",
         hooks=("Golden hour, golden cup", "Your 6 PM ritual just upgraded", "Light hits different with coffee"),
         ai_prompt="golden hour sunlight sweeping across a cosy kitchen counter, dust motes in the light beams"),
    dict(id="rain_window_cafe", name="Rain-on-window café mood", scene="rain",
         motions=("rack_focus", "parallax_pan_l", "push_in"), tone="cool", transition="dissolve", music="lofi",
         hooks=("Rain outside. Coffee inside.", "Sound on for this one", "Cancel plans. Brew this."),
         ai_prompt="raindrops running down a cafe window at dusk with warm blurred lights behind, moody"),
    dict(id="marble_spotlight", name="Dark marble with spotlight", scene="spotlight",
         motions=("dolly_zoom", "pull_out", "orbit"), tone="noir", transition="flash", music="cinematic",
         hooks=("Lights. Jar. Action.", "Meet the main character", "Spotlight on your morning"),
         ai_prompt="dark black marble tabletop with a single dramatic theatrical spotlight cone and floating dust"),
    dict(id="bean_cascade", name="Roasted bean cascade", scene="cascade",
         motions=("speed_ramp", "crane_up", "push_in"), tone="rich", transition="zoom_punch", music="upbeat",
         hooks=("It's raining beans", "From bean to jar, in one shot", "Every bean, picked for this"),
         ai_prompt="slow motion cascade of glossy roasted coffee beans falling and bouncing, dark warm background"),
    dict(id="ink_in_water", name="Smoke and ink-in-water plumes", scene="ink",
         motions=("orbit", "rack_focus", "pull_out"), tone="velvet", transition="dissolve", music="ambient",
         hooks=("Hypnotic, right?", "Don't blink", "Mood, in motion"),
         ai_prompt="slow motion plumes of dark brown ink blooming and curling in clear water, studio backlight"),
    dict(id="night_city_bokeh", name="Night city bokeh", scene="city_bokeh",
         motions=("parallax_pan_l", "rack_focus", "pull_out"), tone="neon", transition="whip", music="lofi",
         hooks=("Late night? Good coffee.", "City lights, cup in hand", "After hours, upgraded"),
         ai_prompt="out of focus night city lights bokeh seen through a window, warm and teal glow, gentle drift"),
    dict(id="sunrise_window", name="Sunrise through the window", scene="sunrise",
         motions=("crane_up", "push_in", "parallax_pan_r"), tone="dawn", transition="light_leak", music="calm",
         hooks=("Sunrise in a cup", "Alarm off. Kettle on.", "Your 7 AM glow-up"),
         ai_prompt="soft sunrise light pouring through a window with sheer curtains moving, warm haze, morning calm"),
    dict(id="light_tunnel", name="Particle and light-streak tunnel", scene="tunnel",
         motions=("dolly_zoom", "speed_ramp", "push_in"), tone="neon", transition="flash", music="upbeat",
         hooks=("Warp speed to your first sip", "Energy, unlocked", "Ready? Go."),
         ai_prompt="abstract tunnel of warm golden light streaks and particles rushing toward camera, hyperspace"),
    dict(id="monsoon_chai_time", name="Monsoon chai-time vibe", scene="monsoon",
         motions=("parallax_pan_r", "rack_focus", "crane_up"), tone="cool", transition="dissolve", music="lofi",
         hooks=("Monsoon called. Coffee answered.", "Baarish + coffee = perfect", "Pakoda optional. This isn't."),
         ai_prompt="monsoon rain falling on a balcony at dusk with warm lamp glow and wet green leaves, cosy"),
    dict(id="velvet_orbit", name="Velvet studio orbit", scene="velvet",
         motions=("orbit", "pull_out", "parallax_pan_l"), tone="velvet", transition="whip", music="jazz",
         hooks=("Luxury, but make it daily", "Slow down. Look closer.", "Studio-grade morning"),
         ai_prompt="slowly rotating studio with deep velvet fabric folds and soft rim light, luxury product backdrop"),
    dict(id="ember_glow", name="Ember glow and rising sparks", scene="embers",
         motions=("crane_up", "speed_ramp", "dolly_zoom"), tone="rich", transition="light_leak", music="cinematic",
         hooks=("Roasted to this", "Feel the heat?", "Fire-roasted mood"),
         ai_prompt="glowing embers and rising sparks in darkness, warm orange bokeh, slow motion"),
]

_BY_ID = {c["id"]: c for c in CONCEPTS}
_BANNED_HOOK = ("100%", "pure", "chicory", "₹", "rs.", "per cup", "/cup")


def get(concept_id: str) -> dict | None:
    return _BY_ID.get(concept_id)


def _date(d) -> _dt.date:
    if isinstance(d, _dt.date):
        return d
    return _dt.date.fromisoformat(str(d)[:10])


def load_history(path: str | None = None) -> list[dict]:
    try:
        with open(path or HISTORY_PATH) as f:
            rows = json.load(f)
        return rows if isinstance(rows, list) else rows.get("records", [])
    except Exception:
        return []


def save_history(rows: list[dict], path: str | None = None) -> None:
    p = path or HISTORY_PATH
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    with open(p, "w") as f:
        json.dump(rows[-400:], f, indent=1)


def _window(rows, on_date, days, fmt=None):
    d = _date(on_date)
    out = []
    for r in rows:
        try:
            rd = _date(r.get("date"))
        except Exception:
            continue
        if 0 <= (d - rd).days < days and (fmt is None or r.get("format") == fmt):
            out.append(r)
    return out


def _order(seq, key):
    return sorted(seq, key=lambda x: hashlib.sha256(f"{key}|{x}".encode()).hexdigest())


def format_key(format_type: str) -> str:
    """History key for a surface. Reel and Short stay themselves.

    Other surfaces (a sales-push reel or story) do not collapse into the daily
    reel, so they cannot overwrite that reel's variety slot.
    """
    raw = str(format_type or "reel").strip().lower()
    if raw in ("short", "yt_short", "youtube"):
        return "short"
    if raw in ("reel", "ig_reel"):
        return "reel"
    return raw or "reel"


def pick(on_date, format_type: str, *, sku: str = "", history: list[dict] | None = None,
         exclude_concepts=(), exclude_layouts=(), path: str | None = None) -> dict:
    """Choose today's concept/motion/layout/transition/hook for a format, honouring rotation rules."""
    fmt = format_key(format_type)
    rows = load_history(path) if history is None else history
    ds = _date(on_date).isoformat()
    recent = _window(rows, ds, ROTATION_DAYS, fmt)
    sibling = [r for r in rows if r.get("date") == ds and r.get("format") != fmt]
    # A same-day re-render of the same format must not count against itself.
    recent = [r for r in recent if r.get("date") != ds]
    hooks_used = {r.get("hook") for r in _window(rows, ds, HOOK_DAYS, fmt)} | {r.get("hook") for r in sibling}

    def used(field):
        return {r.get(field) for r in recent} | {r.get(field) for r in sibling}

    key = f"{ds}|{fmt}|{sku}"
    bad_c = used("concept") | set(exclude_concepts)
    concepts = [c for c in _order([c["id"] for c in CONCEPTS], key) if c not in bad_c] or \
               [c for c in _order([c["id"] for c in CONCEPTS], key) if c not in set(exclude_concepts)]
    c = _BY_ID[concepts[0]]
    bad_m = used("motion")
    motions = [m for m in c["motions"] if m not in bad_m] + [m for m in _order(MOTIONS, key) if m not in bad_m]
    motion = (motions or list(_order(MOTIONS, key)))[0]
    bad_l = used("layout") | set(exclude_layouts)
    layouts = [lay for lay in _order(list(LAYOUTS), key) if lay not in bad_l] \
        or [lay for lay in _order(list(LAYOUTS), key) if lay not in set(exclude_layouts)] \
        or _order(list(LAYOUTS), key)
    sib_t = {r.get("transition") for r in sibling}
    alts = [t for t in _order(TRANSITIONS, key) if t not in sib_t]
    transition = c["transition"] if c["transition"] not in sib_t else (alts[0] if alts else c["transition"])
    hooks = [h for h in c["hooks"] if h not in hooks_used] or list(c["hooks"])
    hook = _order(hooks, key)[0]
    return dict(date=ds, format=fmt, concept=c["id"], name=c["name"], scene=c["scene"], tone=c["tone"],
                motion=motion, layout=layouts[0], transition=transition, music=c["music"],
                music_track=MUSIC.get(c["music"]), hook=hook, ai_prompt=f"{c['ai_prompt']}, {_NO_JAR}")


def record(choice: dict, *, phashes=(), source: str = "procedural", label: str = "",
           path: str | None = None) -> None:
    rows = load_history(path)
    rows = [r for r in rows if not (r.get("date") == choice.get("date") and r.get("format") == choice.get("format"))]
    rows.append({k: choice.get(k) for k in ("date", "format", "concept", "motion", "layout", "transition", "hook", "music")}
                | {"phash": list(phashes), "bg_source": source, "label": label})
    save_history(rows, path)


def hook_is_claim_safe(text: str) -> bool:
    t = (text or "").lower()
    return not any(b in t for b in _BANNED_HOOK)


# ── perceptual hash variety gate ─────────────────────────────────────────────
PHASH_MIN_DISTANCE = int(os.getenv("SHORTS_PHASH_MIN_DISTANCE", "12"))


def phash(img) -> str:
    """64-bit DCT perceptual hash (hex) of a PIL image or array."""
    import numpy as np
    from PIL import Image
    if not isinstance(img, Image.Image):
        img = Image.fromarray(np.asarray(img).astype("uint8"))
    g = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), np.float64)
    n = 32
    k = np.arange(n)
    dct = np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
    coef = dct @ g @ dct.T
    low = coef[:8, :8].flatten()
    med = np.median(low[1:])
    bits = (low > med).astype(int)
    return f"{int(''.join(map(str, bits)), 2):016x}"


def hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def key_frames(path: str, fractions=(0.05, 0.5, 0.92)):
    import imageio.v2 as imageio
    r = imageio.get_reader(path, format="FFMPEG")
    try:
        try:
            total = int(r.count_frames())
        except Exception:
            total = int(r.get_length())
        return [r.get_data(min(total - 1, int(f * (total - 1)))) for f in fractions]
    finally:
        r.close()


def variety_check(path: str, choice: dict, *, history: list[dict] | None = None,
                  hist_path: str | None = None) -> dict:
    """Reject a render whose concept repeats or whose key frames look like a recent one."""
    rows = load_history(hist_path) if history is None else history
    ds, fmt = choice.get("date"), choice.get("format")
    recent = [r for r in _window(rows, ds, ROTATION_DAYS + 1, fmt) if r.get("date") != ds]
    recent += [r for r in rows if r.get("date") == ds and r.get("format") != fmt]
    reasons = []
    for r in recent:
        if r.get("concept") == choice.get("concept"):
            reasons.append(f"concept_repeat:{r.get('concept')}@{r.get('date')}/{r.get('format')}")
    try:
        hashes = [phash(f) for f in key_frames(path)]
    except Exception as exc:
        return {"passed": False, "reasons": [f"variety_frames_unreadable:{type(exc).__name__}"], "phash": []}
    closest = None
    for r in recent:
        old = r.get("phash") or []
        if len(old) != len(hashes):
            continue
        d = sum(hamming(a, b) for a, b in zip(hashes, old)) / len(hashes)
        if closest is None or d < closest[0]:
            closest = (d, r)
        if d < PHASH_MIN_DISTANCE:
            reasons.append(f"too_similar_to:{r.get('date')}/{r.get('format')}:{r.get('concept')}:d={d:.1f}")
    return {"passed": not reasons, "reasons": reasons, "phash": hashes,
            "closest_distance": None if closest is None else round(closest[0], 1)}
