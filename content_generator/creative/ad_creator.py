"""Ad-creator video engine: cinematic, fast-cut, beat-synced reels and Shorts from REAL jar photos.

What a viral ad creator does, made explicit and testable:

* a hook that lands inside the first second (text slam + snap zoom);
* a hard cut every 1-3 seconds, snapped to the music's measured beat grid;
* constant camera motion (push-in, pull-out, pans, tilt, snap zoom) — no shot
  sits still;
* kinetic word-by-word captions, big and bold, one accent colour on the key word;
* a colour grade per template (warm film, moody contrast, golden hour...);
* a varied shot list: label macro, jar hero, low hero, split screen, texture
  plate, optional non-product b-roll, end card;
* a strong CTA end card (comment keyword / shop), with the UTM link carried on
  the piece for the caption and comment replies.

Product pixels always come from the official studio cutouts in
``brand_assets/approved_photos`` (via premium_cards.load_jar), placed on a
procedural studio backdrop. No AI or stock jar is ever drawn or generated, and
a cutout is never composited into a photographic scene. Non-product b-roll
(pour, steam) may fill separate shots only.

Several distinct templates rotate. Selection prefers templates whose REAL
measured outcomes beat the platform median (post_outcomes.template_scores),
keeps exploring untested ones, retires measured losers, and never gives two
video pieces the same template on one day. Every render must still pass the
unchanged 8.0 visual gate before it can publish.
"""
from __future__ import annotations

import glob
import hashlib
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

W, H = 1080, 1920
SW, SH = 1296, 2304          # still size: 1.2x so motion never reveals an edge
FPS = 30
ACCENT = "0xC8962E"
STORE = "https://p3online.in/"
VIDEO_LABELS = ("growth_reel", "reel_1", "yt_short")
RETIRE_RATIO = 0.60
RETIRE_MIN_N = 3

GRADES = {
    "warm_film": "eq=contrast=1.10:saturation=1.18:gamma=0.97,colorbalance=rs=0.05:bs=-0.05:rm=0.03:bm=-0.03",
    "moody_contrast": "eq=contrast=1.22:saturation=1.05:brightness=-0.03,colorbalance=rs=0.02:bs=0.04:rh=0.04:bh=-0.04",
    "golden_hour": "eq=contrast=1.06:saturation=1.25:gamma=0.95,colorbalance=rs=0.08:gs=0.03:bs=-0.08:rh=0.05",
    "clean_punch": "eq=contrast=1.14:saturation=1.22",
    "noir_macro": "eq=contrast=1.28:saturation=0.92:brightness=-0.04,colorbalance=rs=0.03:bs=-0.02",
}

# shot kinds: hook_split, hook_text, jar_hero, jar_low, jar_offset, label_macro,
# texture, broll, end_card. cadence = (min_s, max_s) per cut, snapped to beats.
TEMPLATES = {
    "fast_cut_curiosity": {
        "name": "Fast-cut curiosity", "hook": "curiosity question + split screen",
        "shots": ["hook_split", "label_macro", "jar_hero", "jar_low", "broll", "label_macro",
                  "jar_offset", "texture", "jar_hero", "label_macro", "jar_low"],
        "cadence": (1.0, 2.0), "duration": 24.0, "grade": "warm_film", "music": "lofi_cafe",
        "keyword": "CUP", "cta": "Comment CUP and I'll send you the link",
    },
    "problem_solution": {
        "name": "Problem -> fix demo", "hook": "name the everyday problem in 5 words",
        "shots": ["hook_text", "texture", "jar_hero", "label_macro", "jar_offset", "broll", "jar_low", "label_macro", "jar_hero"],
        "cadence": (1.0, 2.5), "duration": 18.0, "grade": "moody_contrast", "music": "cinematic_origin",
        "keyword": "FIX", "cta": "Comment FIX for the jar link",
    },
    "pov_ritual": {
        "name": "POV morning ritual", "hook": "POV: one real first-person moment",
        "shots": ["hook_text", "jar_low", "broll", "label_macro", "jar_hero", "texture", "jar_offset", "label_macro"],
        "cadence": (1.5, 3.0), "duration": 18.0, "grade": "golden_hour", "music": "calm_morning",
        "keyword": "RITUAL", "cta": "Comment RITUAL and I'll share the link",
    },
    "myth_vs_fact": {
        "name": "Myth vs fact", "hook": "MYTH: a belief people repeat",
        "shots": ["hook_split", "label_macro", "jar_hero", "jar_offset", "texture", "label_macro", "jar_low", "jar_hero"],
        "cadence": (1.0, 1.5), "duration": 16.0, "grade": "clean_punch", "music": "upbeat_roast",
        "keyword": "FACT", "cta": "Comment FACT for the link",
    },
    "asmr_macro": {
        "name": "ASMR macro texture", "hook": "one sensory word, no voice needed",
        "shots": ["hook_text", "label_macro", "broll", "jar_low", "label_macro", "texture", "jar_hero"],
        "cadence": (1.5, 3.0), "duration": 15.0, "grade": "noir_macro", "music": "ambient_lounge",
        "keyword": "AROMA", "cta": "Comment AROMA for the link",
    },
    "listicle_3": {
        "name": "3 things in 15 seconds", "hook": "3 things nobody tells you about X",
        "shots": ["hook_text", "jar_hero", "label_macro", "jar_offset", "broll", "label_macro", "jar_low", "texture"],
        "cadence": (1.0, 2.0), "duration": 20.0, "grade": "warm_film", "music": "premium_jazz",
        "keyword": "LIST", "cta": "Comment LIST and I'll send the link",
    },
}
MOTIONS = ("push_in", "pan_right", "pull_out", "tilt_up", "pan_left", "snap_zoom")
_BANNED = re.compile(r"100\s*%|\bfresh\w*|\blab[\s-]*tested\b|zero\s+acidity|single[\s-]*origin", re.I)
_LABELISH = re.compile(r"^[A-Za-z_]+(?:[ _-][A-Za-z]+){0,2}$")


# ── template choice (learned) ────────────────────────────────────────────────

def utm_link(template_id: str, label: str, keyword: str) -> str:
    source = "youtube" if label == "yt_short" else "instagram"
    token = "".join(ch for ch in keyword.lower() if ch.isalnum()) or "link"
    return (f"{STORE}?utm_source={source}&utm_medium={label}"
            f"&utm_campaign=ad_{template_id}&utm_content={token}")


def _jitter(*parts) -> float:
    digest = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(digest[:6], 16) / 0xFFFFFF * 0.05


def _recent_templates(label: str, days: int = 2) -> list[str]:
    try:
        from content_generator.core.distinctness import load_history
        rows = load_history(days=days)
    except Exception:
        return []
    return [r.get("template") for r in rows if r.get("label") == label and r.get("template")]


def choose_template(label: str, day: int, *, taken: tuple[str, ...] = (), scores: dict | None = None,
                    recent: list[str] | None = None) -> str:
    """Pick today's template for one video piece: learned winners first, still exploring."""
    if scores is None:
        try:
            from content_generator.analytics.post_outcomes import template_scores
            scores = template_scores()
        except Exception:
            scores = {}
    recent = _recent_templates(label) if recent is None else recent
    ranked = []
    for tid in TEMPLATES:
        stat = scores.get(tid) or {}
        n = int(stat.get("n") or 0)
        ratio = float(stat.get("ratio") or 1.0)
        retired = n >= RETIRE_MIN_N and ratio <= RETIRE_RATIO
        value = ratio + 0.35 / math.sqrt(n + 1) + _jitter(day, label, tid)
        if tid in taken:
            value -= 10
        if tid in recent:
            value -= 1.0
        if retired:
            value -= 5
        ranked.append((value, tid))
    ranked.sort(reverse=True)
    return ranked[0][1]


def planned_templates(day: int, scores: dict | None = None) -> dict[str, str]:
    """Today's distinct template per video label, deterministic for prompts and render."""
    plan: dict[str, str] = {}
    taken: list[str] = []
    for label in VIDEO_LABELS:
        tid = ""
        if label == "growth_reel":
            try:
                from content_generator.prompts.growth_reel import format_for_day
                if format_for_day(day) == "fast_cut_curiosity":
                    tid = "fast_cut_curiosity"
            except Exception:
                tid = ""
        if not tid:
            tid = choose_template(label, day, taken=tuple(taken), scores=scores)
        plan[label] = tid
        taken.append(tid)
    return plan


def assign_templates(content: dict, day: int) -> dict[str, str]:
    """Stamp distinct ad templates on today's video pieces (fast-cut days keep fast-cut)."""
    plan = planned_templates(day)
    taken: list[str] = []
    out: dict[str, str] = {}
    pieces = {
        "growth_reel": content.get("growth_reel") if isinstance(content.get("growth_reel"), dict) else None,
        "reel_1": (content.get("reels") or [None])[0] if isinstance(content.get("reels"), list) and content.get("reels") else None,
        "yt_short": content.get("yt_short") if isinstance(content.get("yt_short"), dict) else None,
    }
    for label in VIDEO_LABELS:
        piece = pieces.get(label)
        if not isinstance(piece, dict) or not piece:
            continue
        tid = piece.get("ad_template_id") or (
            "fast_cut_curiosity" if piece.get("growth_template_id") == "fast_cut_curiosity" else plan[label])
        if tid not in TEMPLATES or tid in taken:
            tid = choose_template(label, day, taken=tuple(taken))
        stamp(piece, tid, label)
        taken.append(tid)
        out[label] = tid
    return out


def stamp(piece: dict, template_id: str, label: str) -> dict:
    spec = TEMPLATES[template_id]
    piece["ad_template_id"] = template_id
    piece.setdefault("video_style", {
        "template": template_id, "grade": spec["grade"], "cadence_s": list(spec["cadence"]),
        "duration_s": spec["duration"], "music": spec["music"],
    })
    if label != "growth_reel" or not piece.get("reply_link"):
        piece["ad_cta_link"] = utm_link(template_id, label, spec["keyword"])
    else:
        piece["ad_cta_link"] = piece["reply_link"]
    return piece


def prompt_contract(label: str, day: int) -> str:
    """Script contract for the chosen template, appended to video generation prompts."""
    if label not in VIDEO_LABELS:
        return ""
    tid = planned_templates(day)[label]
    if label == "growth_reel" and tid == "fast_cut_curiosity":
        return ""  # the growth-reel prompt already carries the full fast-cut contract
    spec = TEMPLATES[tid]
    lo, hi = spec["cadence"]
    return (
        f"AD-CREATOR VIDEO TEMPLATE for {label}: {spec['name']} (ad_template_id {tid}).\n"
        f"- Hook in the FIRST SECOND: {spec['hook']}. Max 7 words on screen, readable in under 1s.\n"
        f"- Then a new shot every {lo:g}-{hi:g}s (hard cuts on the beat); write 6-9 frames, each with a 3-8 word "
        "on_screen line and one short spoken line. Every frame is a different shot: label macro, jar hero, "
        "texture, pour/steam b-roll (never a jar), low angle, end card.\n"
        f"- Captions run word by word; put the single most important word of each line first-class (it gets the gold accent).\n"
        f"- Teach one concrete coffee point before any ask. End card CTA: \"{spec['cta']}\".\n"
        "- The jar on screen is always the real photographed jar; never describe an AI or redesigned jar.\n"
        "- Same claim rules as everywhere: no purity percentage, no freshness, lab or acidity claims, no origin claims, "
        "no health claims, no fake urgency, no giveaways, no competitor knocks. Ultra Blend is 70% coffee 30% chicory and "
        "is never called pure. Freeze-dried only Purica/Purista; agglomerated only Bold/Prima. No spoken prices."
    )


# ── script -> timeline ───────────────────────────────────────────────────────

def _clean(text: str) -> str:
    try:
        from content_generator.creative import render_claims as rc
        text = rc.guard(str(text or ""))
    except Exception:
        text = str(text or "")
    text = _BANNED.sub("", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def script_from_piece(piece: dict) -> dict:
    """Hook + body lines + CTA from any reel/Short shape."""
    piece = piece if isinstance(piece, dict) else {}
    from content_generator.analytics.post_outcomes import piece_hook
    overlay = str(piece.get("hook_text_overlay") or "").strip()
    hook = overlay if len(overlay.split()) >= 2 else piece_hook(piece)
    lines = []
    for frame in (piece.get("frames") or piece.get("scenes") or piece.get("script") or []):
        if isinstance(frame, dict):
            line = str(frame.get("spoken") or frame.get("voiceover") or frame.get("on_screen") or "").strip()
            if line:
                lines.append(line)
    hook_words = _clean(hook).split()[:7]
    tid = piece.get("ad_template_id") or "fast_cut_curiosity"
    cta = TEMPLATES.get(tid, TEMPLATES["fast_cut_curiosity"])["cta"]
    return {"hook": " ".join(hook_words) or "Watch this", "lines": [_clean(l) for l in lines if _clean(l)],
            "cta": _clean(cta)}


def beat_grid(track: str | None, seconds: float) -> float:
    try:
        from content_generator.creative.audio_director import measure_track_tempo
        bpm = float(measure_track_tempo(track, seconds=min(seconds, 30.0)).get("bpm") or 120.0)
    except Exception:
        bpm = 120.0
    beat = 60.0 / bpm if bpm > 0 else 0.5
    while beat < 0.4:
        beat *= 2
    while beat > 1.0:
        beat /= 2
    return round(beat, 4)


def plan_timeline(template_id: str, beat: float, duration: float | None = None) -> list[dict]:
    """Cut list on the beat: hook <= ~1s, body cuts within cadence (1-3s), 2.5s end card."""
    spec = TEMPLATES[template_id]
    total = float(duration or spec["duration"])
    lo, hi = spec["cadence"]
    hook_len = max(1, round(1.0 / beat)) * beat
    end_len = max(2.0, round(2.5 / beat) * beat)
    body_total = total - hook_len - end_len
    lengths: list[float] = []
    used, i = 0.0, 0
    while used < body_total - 1e-6:
        target = lo if i % 3 == 0 else (lo + hi) / 2
        n = max(1, round(target / beat))
        sec = n * beat
        if sec < lo - 0.06:
            sec += beat
        if sec > hi + 1e-6 and n > 1:
            sec -= beat
        sec = min(sec, body_total - used)
        lengths.append(sec)
        used += sec
        i += 1
    # A sub-minimum tail is merged into the previous cut (split in two if that gets too long).
    if len(lengths) >= 2 and lengths[-1] < min(lo, 1.0) - 0.06:
        tail = lengths.pop()
        merged = lengths.pop() + tail
        if merged > 3.0:
            first = max(1, round(merged / beat) // 2) * beat  # keep the split on the beat grid
            lengths += [first, merged - first]
        else:
            lengths.append(merged)
    shots = [{"kind": spec["shots"][0], "start": 0.0, "seconds": round(hook_len, 3), "motion": "snap_zoom"}]
    t = hook_len
    body = spec["shots"][1:]
    for k, sec in enumerate(lengths):
        shots.append({"kind": body[k % len(body)], "start": round(t, 3), "seconds": round(sec, 3),
                      "motion": MOTIONS[k % len(MOTIONS)]})
        t += sec
    shots.append({"kind": "end_card", "start": round(t, 3), "seconds": round(total - t, 3), "motion": "push_in"})
    return shots


def _shot_at(shots: list[dict], t: float) -> dict:
    for shot in shots:
        if shot["start"] <= t < shot["start"] + shot["seconds"]:
            return shot
    return shots[-1]


def caption_events(script: dict, shots: list[dict], keyword: str = "") -> list[dict]:
    """Word-by-word captions across the body shots; hook slam on shot 0; CTA on the end card."""
    events = []
    hook = shots[0]
    events.append({"text": script["hook"], "start": 0.0, "end": hook["seconds"], "style": "hook"})
    body_start = hook["seconds"]
    # The comment ask lands on the last body cut; the end card is the clean shop lock-up.
    cta_shot = shots[-2] if len(shots) >= 3 else shots[-1]
    body_end = cta_shot["start"]
    words = " ".join(script.get("lines") or []).split()
    # 1-2 word chunks, CapCut style, at a readable ~0.5s each.
    chunks: list[str] = []
    k = 0
    while k < len(words):
        take = 1 if len(words[k]) >= 8 or (k + 1 < len(words) and len(words[k + 1]) >= 8) else 2
        chunks.append(" ".join(words[k:k + take]))
        k += take
    slots = max(1, int((body_end - body_start) / 0.5))
    chunks = chunks[:slots]
    if chunks:
        step = (body_end - body_start) / len(chunks)
        for k, chunk in enumerate(chunks):
            s = body_start + k * step
            y = 0.075 if _shot_at(shots, s + 0.01)["kind"] == "label_macro" else 0.20
            events.append({"text": chunk, "start": round(s, 3), "end": round(s + step, 3), "style": "word",
                           "accent": any(_is_accent(w, keyword) for w in chunk.split()), "y": y})
    end_a, end_b = shots[-1]["start"], shots[-1]["start"] + shots[-1]["seconds"]
    events.append({"text": script["cta"], "start": cta_shot["start"], "end": end_a, "style": "cta"})
    events.append({"text": "Shop p3online.in", "start": end_a, "end": end_b, "style": "shop"})
    return events


def _is_accent(word: str, keyword: str = "") -> bool:
    w = re.sub(r"[^A-Za-z0-9]", "", word)
    if not w:
        return False
    if any(ch.isdigit() for ch in w):
        return True
    if keyword and w.upper() == keyword.upper():
        return True
    return w.lower() in {"bold", "purica", "purista", "prima", "ultra", "chicory", "label", "never", "only",
                         "freeze-dried", "agglomerated", "aroma", "crema"}


# ── stills from real product photos ──────────────────────────────────────────

def _sku_key(product: str | None) -> str:
    try:
        from content_generator.creative.approved_photos import _norm_sku
        return _norm_sku(product or "") or ""
    except Exception:
        return ""


def _render_stills(sku: str, shots: list[dict], work: str, seed: int, plates: list[str]) -> list[str]:
    from PIL import Image
    from content_generator.creative import cinematic_motion as cm
    from content_generator.creative import premium_cards as pc
    palettes = pc.PALETTES[sku]
    paths = []
    jar_cache: dict[int, Image.Image] = {}
    light = (0.25, 0.30, 0.75, 0.40)
    backdrops = {}

    def backdrop(idx: int, t: float, clean: bool = False):
        k = idx % len(palettes)
        key = (k, clean)
        if key not in backdrops:
            bd = cm._Backdrop(palettes[k], seed + k, light, 0.80)
            if clean:
                bd.bokeh = []  # end card: clean studio sweep, steam and light only
            backdrops[key] = bd
        return backdrops[key].frame(t, 10.0).convert("RGB").resize((SW, SH), Image.LANCZOS)

    def jar(h: int):
        if h not in jar_cache:
            jar_cache[h] = pc.load_jar(sku, h, source=pc.official_jar_asset(sku))
        return jar_cache[h]

    def hero(idx: int, scale: float, cx_frac: float, base_frac: float, t: float, clean: bool = False):
        canvas = backdrop(idx, t, clean).convert("RGBA")
        j = jar(int(SH * scale))
        box = pc.place_jar(canvas, j, int(SW * cx_frac), int(SH * base_frac), palettes[idx % len(palettes)])
        return canvas.convert("RGB"), box

    for n, shot in enumerate(shots):
        kind = shot["kind"]
        t = 1.0 + (n * 1.7) % 8.0
        dest = os.path.join(work, f"s{n:02d}.jpg")
        if kind == "jar_hero":
            img, _ = hero(n, 0.64, 0.5, 0.92, t)
        elif kind == "end_card":
            img, _ = hero(n + 1, 0.52, 0.5, 0.94, t + 4.0, clean=True)  # new light/palette: motion vs the hook
        elif kind == "jar_low":
            img, _ = hero(n + 1, 0.78, 0.5, 1.0, t)
        elif kind == "jar_offset":
            img, _ = hero(n, 0.60, 0.60 if n % 2 else 0.40, 0.93, t)
        elif kind == "label_macro":
            full, box = hero(n, 0.70, 0.5, 0.96, t)
            x0, y0, x1, y1 = box
            jh = y1 - y0
            cw = int((x1 - x0) * (1.08 if (n // 2) % 2 else 0.92))
            ch = int(cw * SH / SW)
            cy = y0 + int(jh * (0.50 if (n // 2) % 2 else 0.56))
            cx = (x0 + x1) // 2
            crop = full.crop((max(0, cx - cw // 2), max(0, cy - ch // 2),
                              min(SW, cx + cw // 2), min(SH, cy + ch // 2)))
            img = crop.resize((SW, SH), Image.LANCZOS)
        elif kind == "broll" and plates:
            img = Image.open(plates[n % len(plates)]).convert("RGB")
            scale = max(SW / img.width, SH / img.height)
            img = img.resize((int(img.width * scale) + 1, int(img.height * scale) + 1), Image.LANCZOS)
            img = img.crop(((img.width - SW) // 2, (img.height - SH) // 2, (img.width - SW) // 2 + SW, (img.height - SH) // 2 + SH))
        elif kind == "hook_split":
            top = (Image.open(plates[0]).convert("RGB") if plates else backdrop(n + 1, t + 3))
            top = top.resize((SW, SH // 2), Image.LANCZOS)
            bottom, _ = hero(n, 0.66, 0.5, 0.97, t)
            bottom = bottom.resize((SW, SH // 2), Image.LANCZOS)
            img = Image.new("RGB", (SW, SH))
            img.paste(top, (0, 0))
            img.paste(bottom, (0, SH // 2))
        elif kind == "hook_text":
            img, _ = hero(n, 0.56, 0.5, 0.97, t)
        else:  # texture (or broll without a plate)
            img = backdrop(n + 1, t + 2.0)
        img.save(dest, quality=92)
        paths.append(dest)
    return paths


# ── ffmpeg assembly ──────────────────────────────────────────────────────────

def _ffmpeg() -> str | None:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _font() -> str | None:
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                 "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                 "brand_assets/fonts/IBMPlexSerif-Bold.ttf"):
        if os.path.isfile(path):
            return path
    return None


def _esc(text: str) -> str:
    text = str(text or "").replace("'", "\u2019")  # typographic apostrophe is safe inside drawtext quotes
    kept = [ch if (ch.isalnum() or ch in " -?!.\u2019") else " " for ch in text]
    return " ".join("".join(kept).split())


def motion_expr(motion: str, frames: int) -> str:
    d = max(1, frames)
    p = f"(on/{d})"
    center = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    if motion == "pull_out":
        return f"z='1.16-0.12*{p}':{center}"
    if motion == "pan_left":
        return f"z='1.12':x='(iw-iw/zoom)*(1-{p})':y='ih/2-(ih/zoom/2)'"
    if motion == "pan_right":
        return f"z='1.12':x='(iw-iw/zoom)*{p}':y='ih/2-(ih/zoom/2)'"
    if motion == "tilt_up":
        return f"z='1.12':x='iw/2-(iw/zoom/2)':y='(ih-ih/zoom)*(1-{p})'"
    if motion == "snap_zoom":
        return f"z='1.0+0.16*min(1,{p}*4)':{center}"
    return f"z='1.0+0.12*{p}':{center}"


def _wrap(text: str, width: int = 14) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines[:3]


def caption_filters(events: list[dict], font: str | None) -> list[str]:
    if not font:
        return []
    ff = font.replace("\\", "/").replace(":", "\\:")
    out = []
    for ev in events:
        a, b = ev["start"], ev["end"]
        if ev["style"] == "shop" and ev.get("overlay"):
            continue  # drawn by the premium end-card overlay instead
        if ev["style"] == "shop":
            out.append(
                f"drawtext=fontfile={ff}:text='{_esc(ev['text'].upper())}':fontsize=54:fontcolor=white:"
                f"borderw=5:bordercolor=black@0.8:x=(w-text_w)/2:y=h*0.30:"
                f"enable='between(t\\,{a:.3f}\\,{b:.3f})'")
            continue
        if ev["style"] in ("hook", "cta"):
            size = 104 if ev["style"] == "hook" else 78
            y0 = 0.14 if ev["style"] == "hook" else 0.12
            for li, line in enumerate(_wrap(ev["text"], 13 if ev["style"] == "hook" else 18)):
                color = ACCENT if (ev["style"] == "cta" and li == 0) else "white"
                out.append(
                    f"drawtext=fontfile={ff}:text='{_esc(line.upper())}':fontsize={size}:fontcolor={color}:"
                    f"borderw=7:bordercolor=black@0.85:shadowcolor=black@0.6:shadowx=4:shadowy=6:"
                    f"x=(w-text_w)/2:y=h*{y0}+{li}*{int(size * 1.12)}:"
                    f"alpha='min(1,(t-{a:.3f})/0.08)':enable='between(t\\,{a:.3f}\\,{b:.3f})'")
        else:
            color = ACCENT if ev.get("accent") else "white"
            out.append(
                f"drawtext=fontfile={ff}:text='{_esc(ev['text'].upper())}':fontsize=96:fontcolor={color}:"
                f"borderw=7:bordercolor=black@0.85:shadowcolor=black@0.6:shadowx=4:shadowy=6:"
                f"x=(w-text_w)/2:y=h*{ev.get('y', 0.20)}:enable='between(t\\,{a:.3f}\\,{b:.3f})'")
    return out


def end_tagline(sku: str) -> str:
    """Claim-safe end-card line: the product's own name, nothing else."""
    names = {"ultra": "Ultra Blend Instant Coffee", "ultra_blend": "Ultra Blend Instant Coffee"}
    key = str(sku or "").lower()
    return names.get(key) or f"{key.replace('_', ' ').title()} Premium Instant Coffee"


def _pil_font(name: str, size: int):
    from PIL import ImageFont
    for path in (f"brand_assets/fonts/{name}", "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def end_card_overlay(tagline: str, out_png: str) -> str:
    """Premium end card: serif lock-up, auto-fit lines, soft spotlight shade, no outlines."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    # spotlight: darker top band and side margins, open centre where the jar sits
    shade = Image.new("L", (W // 8, H // 8))
    sw, sh = shade.size
    for yy in range(sh):
        top = max(0.0, 1 - yy / (sh * 0.44)) ** 1.6
        for xx in range(sw):
            side = (abs(xx - sw / 2) / (sw / 2)) ** 2.2
            shade.putpixel((xx, yy), int(min(200, 160 * top + 120 * side)))
    img.paste(Image.new("RGBA", (W, H), (8, 6, 4, 255)), (0, 0),
              shade.resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(24)))
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(text)
    gold, cream = (226, 184, 92, 255), (250, 244, 232, 255)
    max_w = W * 0.84

    def fit(name, size, s):
        f = _pil_font(name, size)
        while size > 28 and d.textlength(s, font=f) > max_w:
            size -= 4
            f = _pil_font(name, size)
        return f

    def centre(y, s, font, fill):
        d.text(((W - d.textlength(s, font=font)) / 2, y), s, font=font, fill=fill)

    y = int(H * 0.085)
    d.line([(W / 2 - 70, y), (W / 2 + 70, y)], fill=gold, width=3)
    y += 40
    head = "Shop Purity Beans"
    centre(y, head, fit("IBMPlexSerif-Bold.ttf", 104, head), gold)
    y += 132
    sub = str(tagline or "").replace("'", "\u2019").strip()
    for line in _wrap(sub, 28)[:2]:
        centre(y, line, fit("IBMPlexSerif-Italic.ttf", 58, line), cream)
        y += 74
    y += 30
    url = "p3online.in"
    f_url = _pil_font("IBMPlexSerif-SemiBold.ttf", 50)
    w = d.textlength(url, font=f_url)
    d.rounded_rectangle([(W - w) / 2 - 44, y - 14, (W + w) / 2 + 44, y + 74], radius=44,
                        outline=(226, 184, 92, 210), width=2, fill=(12, 9, 6, 130))
    centre(y, url, f_url, cream)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 150), (0, 6), text.split()[3])
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(10)))
    img = Image.alpha_composite(img, text)
    img.save(out_png)
    return out_png


def filtergraph(shots: list[dict], grade: str, captions: list[str], overlay_input: int | None = None) -> str:
    chains, labels = [], []
    for i, shot in enumerate(shots):
        frames = max(2, int(round(shot["seconds"] * FPS)))
        chains.append(
            f"[{i}:v]zoompan={motion_expr(shot['motion'], frames)}:d={frames}:s={W}x{H}:fps={FPS},"
            f"trim=end_frame={frames},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{i}]")
        labels.append(f"[v{i}]")
    post = [GRADES.get(grade, GRADES["warm_film"]), "vignette=angle=PI/5", "noise=alls=3:allf=t"] + captions
    graph = ";".join(chains) + ";" + "".join(labels) + f"concat=n={len(shots)}:v=1:a=0," + ",".join(post)
    if overlay_input is None:
        return graph + "[v]"
    end = shots[-1]
    a = end["start"]
    return (graph + "[base];"
            f"[{overlay_input}:v]format=rgba,fade=t=in:st={a:.3f}:d=0.25:alpha=1[ov];"
            f"[base][ov]overlay=0:0:enable='gte(t\\,{a:.3f})',format=yuv420p[v]")


def _music(name: str) -> str | None:
    root = os.getenv("MUSIC_LIBRARY_DIR", "music_library")
    preferred = os.path.join(root, f"{name}.wav")
    if os.path.isfile(preferred):
        return preferred
    tracks = sorted(glob.glob(os.path.join(root, "*.wav")))
    return tracks[0] if tracks else None


def render(piece: dict, out_path: str, *, label: str = "reel_1", day: int = 0, template_id: str | None = None,
           use_broll: bool = True, on_date: str = "") -> dict | None:
    """Render one ad-style video. Returns meta (path, template, cuts, bpm) or None."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        logger.info("[ad_creator] ffmpeg missing")
        return None
    from content_generator.creative.reel_video import resolve_reel_product
    sku = _sku_key(resolve_reel_product(piece))
    try:
        from content_generator.creative import premium_cards as pc
        if sku not in pc.PALETTES:
            logger.info("[ad_creator] no palette/cutout for %r", sku)
            return None
    except Exception:
        return None
    tid = template_id or piece.get("ad_template_id") or choose_template(label, day)
    if tid not in TEMPLATES:
        tid = "fast_cut_curiosity"
    spec = TEMPLATES[tid]
    track = _music(spec["music"])
    beat = beat_grid(track, spec["duration"])
    shots = plan_timeline(tid, beat)
    total = round(shots[-1]["start"] + shots[-1]["seconds"], 3)
    script = script_from_piece({**piece, "ad_template_id": tid})
    events = caption_events(script, shots, spec["keyword"])
    work = tempfile.mkdtemp(prefix="adcreator-")
    try:
        plates = []
        if use_broll:
            try:
                from content_generator.creative.ken_burns import broll_stills
                plates = broll_stills(f"{label}_ad", work, on_date or "")
            except Exception:
                plates = []
        from content_generator.creative import render_claims as rc
        token = rc.set_sku(sku)
        try:
            stills = _render_stills(sku, shots, work, seed=int(day or 0), plates=plates)
        finally:
            rc.reset_sku(token)
        overlay = None
        try:
            overlay = end_card_overlay(end_tagline(sku), os.path.join(work, "end_overlay.png"))
            for ev in events:
                if ev["style"] == "shop":
                    ev["overlay"] = True
        except Exception as exc:
            logger.info("[ad_creator] end-card overlay skipped: %s", type(exc).__name__)
        graph = filtergraph(shots, spec["grade"], caption_filters(events, _font()),
                            overlay_input=(len(stills) if overlay else None))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        cmd = [ffmpeg, "-nostdin", "-y", "-loglevel", "error"]
        for still in stills:
            cmd += ["-i", still]
        if overlay:
            cmd += ["-loop", "1", "-framerate", str(FPS), "-t", f"{total:.3f}", "-i", overlay]
        if track:
            cmd += ["-stream_loop", "-1", "-i", track]
        else:
            cmd += ["-f", "lavfi", "-i", "anoisesrc=color=brown:r=44100:a=0.015"]
        fade = max(0.0, total - 0.8)
        audio_idx = len(stills) + (1 if overlay else 0)
        cmd += ["-filter_complex", graph, "-map", "[v]", "-map", f"{audio_idx}:a",
                "-af", f"loudnorm=I=-14:TP=-1.5:LRA=11,afade=t=in:d=0.15,afade=t=out:st={fade:.2f}:d=0.8",
                "-t", f"{total:.3f}", "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-maxrate", "9M", "-bufsize", "18M",
                "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_path]
        subprocess.run(cmd, check=True, capture_output=True, timeout=max(180, int(total) * 12))
    except Exception as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or b"")[-300:].decode("utf-8", "replace")
        logger.warning("[ad_creator] render failed: %s %s", type(exc).__name__, detail)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not os.path.isfile(out_path) or os.path.getsize(out_path) < 10_000:
        return None
    piece.setdefault("ad_template_id", tid)
    return {
        "path": out_path, "template": tid, "grade": spec["grade"], "bpm_beat_s": beat,
        "cuts": [s["start"] for s in shots], "shots": [s["kind"] for s in shots],
        "motions": [s["motion"] for s in shots], "duration": total, "captions": len(events),
        "music": os.path.basename(track) if track else None, "sku": sku, "real_jar_only": True,
    }


def enabled() -> bool:
    flag = os.getenv("AD_CREATOR_VIDEO", "").strip()
    if flag in ("0", "1"):
        return flag == "1"
    return not os.getenv("PYTEST_CURRENT_TEST")


def piece_label(render_label: str) -> str:
    low = str(render_label or "").lower()
    if "growth" in low:
        return "growth_reel"
    if "short" in low or "yt" in low:
        return "yt_short"
    return "reel_1"


def render_for(piece: dict, render_label: str, day: int, on_date=None) -> str | None:
    """Entry point for reel_video / short_video: ad-creator render gated at 8.0, or None."""
    if not enabled() or not isinstance(piece, dict):
        return None
    label = piece_label(render_label)
    ds = on_date.isoformat() if hasattr(on_date, "isoformat") else str(on_date or "")[:10]
    out_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    out = os.path.join(out_dir, f"{render_label}_day{day}_{ds or 'today'}_ad.mp4")
    try:
        return render_until_pass(piece, out, label=label, day=day, on_date=ds)
    except Exception as exc:
        logger.warning("[ad_creator] %s skipped: %s", render_label, type(exc).__name__)
        return None


def render_until_pass(piece: dict, out_path: str, *, label: str, day: int = 0, on_date: str = "",
                      gate=None, max_tries: int | None = None) -> str | None:
    """Render, gate at the unchanged 8.0 bar, try the next template on a miss; log every miss."""
    if not enabled():
        return None
    tries = int(max_tries or os.getenv("AD_CREATOR_TRIES", "2"))
    if gate is None:
        from content_generator.creative import visual_gate
        gate = lambda path: visual_gate.evaluate_video(path, {"requires_jar": False}, visual_gate.recent_layouts())
    first = piece.get("ad_template_id") or choose_template(label, day)
    order = [first] + [t for t in TEMPLATES if t != first]
    for attempt, tid in enumerate(order[:tries]):
        meta = render(piece, out_path, label=label, day=day, template_id=tid, on_date=on_date,
                      use_broll=attempt == 0)
        if not meta:
            _lesson(label, f"ad_creator_render_failed:{tid}")
            continue
        verdict = gate(out_path) or {}
        if verdict.get("passed"):
            stamp(piece, tid, label)
            piece["video_render"] = {k: meta[k] for k in ("template", "grade", "duration", "shots", "music")}
            logger.info("[ad_creator] %s %s passed the 8.0 visual gate", label, tid)
            return out_path
        reasons = [str(r) for r in (verdict.get("reasons") or [])][:5]
        logger.warning("[ad_creator] %s %s held by visual gate: %s", label, tid, reasons)
        _lesson(label, f"ad_creator_visual_gate:{tid}: " + "; ".join(reasons))
    return None


def _lesson(label: str, reason: str) -> None:
    try:
        from content_generator.core.obstacle_lessons import platform_for, record
        record(platform_for(label), label, "video_render", "visual_gate", reason,
               "Ad-creator render missed; the existing cinematic and real-photo fallbacks still run at the same 8.0 bar.",
               fix="Try a different template/grade; never use an AI jar.")
    except Exception:
        return
