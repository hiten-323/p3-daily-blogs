"""Final reel fallback: ffmpeg hard cuts and a slow punch-in on real photos.

AI video is not used here. Photos come from the approved-photo manifest
(cutouts and real photos, no baked-copy cards). A quiet bed keeps the
timeline from going silent. Word captions sit in the lower middle.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

W, H = 1080, 1920
FPS = 12
ACCENT = "0xC8962E"


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
    candidates = (
        "brand_assets/fonts/IBMPlexSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    )
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def real_product_paths(sku: str | None = None) -> list[str]:
    """Approved jar photos only. Infographics and blocked files stay out."""
    from content_generator.creative import approved_photos as photos
    root = photos._DIR
    pool = photos.items(None, sku, ("cutout", "real_photo"))
    if sku and len(pool) < 2:
        pool = pool + [it for it in photos.items(None, None, ("cutout", "real_photo")) if it not in pool]
    paths = []
    for item in pool:
        if item.get("baked_copy") or item.get("blocked"):
            continue
        path = os.path.join(root, item["file"])
        if os.path.isfile(path):
            paths.append(path)
    return paths


def shot_plan(duration: float, n_photos: int, *, split: bool) -> list[dict]:
    """Hard cuts of 1-3 seconds. Every shot punches in. No crossfade."""
    duration = max(2.0, float(duration))
    count = max(2, int(round(duration / 2.0)))
    if n_photos:
        count = max(count, 1)
    base = duration / count
    while base > 3.0:
        count += 1
        base = duration / count
    while base < 1.0 and count > 2:
        count -= 1
        base = duration / count
    shots = []
    for i in range(count):
        shots.append({
            "index": i % max(1, n_photos),
            "seconds": round(base, 3),
            "punch_in": True,
            "transition": "cut",
            "split": bool(split and i == 0),
        })
    return shots


def _esc(text: str) -> str:
    """Keep drawtext from seeing commas, quotes, or percent signs."""
    cleaned = []
    for ch in str(text or ""):
        cleaned.append(ch if ch.isalnum() or ch in " -" else " ")
    return " ".join("".join(cleaned).split())


def _caption_filters(words: list[str], seconds: float, font: str | None) -> str:
    if not words or not font:
        return ""
    step = max(0.2, seconds / len(words))
    fontfile = font.replace("\\", "/").replace(":", "\\:")
    parts = []
    for i, word in enumerate(words):
        start = round(i * step, 3)
        end = round(min(seconds, (i + 1) * step), 3)
        color = ACCENT if i == len(words) - 1 else "white"
        parts.append(
            "drawtext="
            f"fontfile={fontfile}:text='{_esc(word)}':fontsize=72:"
            f"fontcolor={color}:shadowcolor=black@0.8:shadowx=3:shadowy=3:"
            "x=(w-text_w)/2:y=h*0.62:"
            f"enable='between(t\\,{start}\\,{end})'"
        )
    return "," + ",".join(parts)


def filtergraph(n_inputs: int, shots: list[dict], words: list[str], font: str | None) -> str:
    """zoompan punch-in, optional opening stack, hard concat. No xfade."""
    chains = []
    labels = []
    cursor = 0
    for shot_i, shot in enumerate(shots):
        seconds = shot["seconds"]
        frames = max(FPS, int(round(seconds * FPS)))
        zoom = (
            f"zoompan=z='min(1.001+0.0018*on,1.12)':x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}"
        )
        line = words if shot_i == 0 else (words[shot_i:shot_i + 1] or words[:1])
        caps = _caption_filters(line, seconds, font)
        if shot.get("split") and n_inputs >= 2:
            chains.append(
                f"[{cursor}:v]scale={W}:{H // 2}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H // 2}:(in_w-{W})/2:(in_h-{H // 2})/2[top];"
                f"[{cursor + 1}:v]scale={W}:{H // 2}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H // 2}:(in_w-{W})/2:(in_h-{H // 2})/2[bot];"
                f"[top][bot]vstack,{zoom},setsar=1,format=yuv420p{caps}[v{shot_i}]"
            )
            cursor += 2
        else:
            src = min(cursor, n_inputs - 1)
            chains.append(
                f"[{src}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
                f"crop={W}:{H}:(in_w-{W})/2:(in_h-{H})/2,{zoom},setsar=1,format=yuv420p{caps}[v{shot_i}]"
            )
            cursor += 1
        labels.append(f"[v{shot_i}]")
    join = "".join(labels) + f"concat=n={len(shots)}:v=1:a=0[v]"
    return ";".join(chains) + ";" + join


def _allow_broll() -> bool:
    """Production tries the video chain. Pytest stays on photos unless a test opts in."""
    flag = os.getenv("FAST_CUT_BROLL", "").strip()
    if flag == "0":
        return False
    if flag == "1":
        return True
    return not os.getenv("PYTEST_CURRENT_TEST")


def _cover(path: str, size: tuple[int, int], dest: str) -> str:
    """Center-crop a real photo onto an exact canvas so ffmpeg never crops short."""
    from PIL import Image
    image = Image.open(path).convert("RGB")
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    resized = image.resize((max(tw, int(image.width * scale)), max(th, int(image.height * scale))), Image.LANCZOS)
    left = max(0, (resized.width - tw) // 2)
    top = max(0, (resized.height - th) // 2)
    resized.crop((left, top, left + tw, top + th)).save(dest, quality=85)
    return dest


def _stack(top: str, bottom: str, dest: str) -> str:
    """Top half is b-roll or a second photo. Bottom half is the real jar."""
    from PIL import Image
    upper = Image.open(top).convert("RGB").resize((W, H // 2), Image.LANCZOS)
    lower = Image.open(bottom).convert("RGB").resize((W, H // 2), Image.LANCZOS)
    frame = Image.new("RGB", (W, H))
    frame.paste(upper, (0, 0))
    frame.paste(lower, (0, H // 2))
    frame.save(dest, quality=85)
    return dest


def broll_stills(label: str, dest_dir: str, on_date: str) -> list[str]:
    """Non-product plates from the provider chain. A miss returns no files."""
    if not _allow_broll():
        return []
    try:
        from content_generator.creative import ai_backgrounds
        choice = {
            "date": on_date,
            "format": "reel",
            "concept": "granule_dissolve",
            "scene": "granules",
            "ai_prompt": (
                "extreme macro of hot water pouring and a spoon scooping dark coffee granules, "
                "steam, amber light, no jar, no bottle, no packaging, no label, no logo, no text"
            ),
        }
        frames, source = ai_backgrounds.fetch_background(choice, f"{label}_broll", (540, 480), 5)
        if not frames or source == "procedural":
            return []
        from PIL import Image
        step = max(1, len(frames) // 4)
        paths = []
        for index, frame in enumerate(frames[::step][:4]):
            dest = os.path.join(dest_dir, f"{label}_broll_{index}.jpg")
            Image.fromarray(frame).convert("RGB").save(dest, quality=85)
            paths.append(dest)
        logger.info("[ken_burns] %s b-roll stills from %s", len(paths), source)
        return paths
    except Exception as exc:
        logger.info("[ken_burns] b-roll skipped: %s", type(exc).__name__)
        return []


def _bed() -> str | None:
    path = os.path.join(os.getenv("MUSIC_LIBRARY_DIR", "music_library"), "lofi_cafe.wav")
    if os.path.isfile(path):
        return path
    if os.path.isfile("music_library/lofi_cafe.wav"):
        return "music_library/lofi_cafe.wav"
    return None


def _assemble(photos: list[str], plates: list[str], plan: list[dict], work: str) -> list[str]:
    """One exact 1080x1920 still per shot. The opening still is a split when asked."""
    inputs = []
    jar = photos[0]
    for shot in plan:
        dest = os.path.join(work, f"shot_{shot['index']}_{len(inputs)}.jpg")
        if shot.get("split"):
            top_src = plates[0] if plates else photos[min(1, len(photos) - 1)]
            top = _cover(top_src, (W, H // 2), os.path.join(work, f"top_{len(inputs)}.jpg"))
            bottom = _cover(jar, (W, H // 2), os.path.join(work, f"bot_{len(inputs)}.jpg"))
            inputs.append(_stack(top, bottom, dest))
            continue
        if plates and shot["index"] % 2 == 0:
            source = plates[shot["index"] % len(plates)]
        else:
            source = photos[shot["index"] % len(photos)]
        inputs.append(_cover(source, (W, H), dest))
    return inputs


def _words(reel: dict) -> list[str]:
    text = ""
    if isinstance(reel, dict):
        text = str(reel.get("chosen_hook") or reel.get("hook") or reel.get("hook_text") or "")
        if not text:
            from content_generator.creative.growth_reel_templates import SPOKEN
            if reel.get("growth_template_id") == "fast_cut_curiosity":
                text = SPOKEN["curiosity"]
    words = [w for w in text.replace("'", "").split() if w][:8]
    return words or ["Watch"]


def render_reel(reel: dict, day: int, label: str, on_date, *, fast: bool = False) -> str | None:
    """Write a 1080x1920 mp4. Returns None when ffmpeg or a real photo is missing."""
    ffmpeg = _ffmpeg()
    if not ffmpeg:
        logger.info("[ken_burns] ffmpeg missing")
        return None
    from content_generator.creative.reel_video import resolve_reel_product
    from content_generator.creative.approved_photos import _norm_sku
    sku = _norm_sku(resolve_reel_product(reel) or "")
    paths = real_product_paths(sku)
    if not paths:
        logger.info("[ken_burns] no approved photo")
        return None
    if fast:
        from content_generator.creative.growth_reel_templates import DURATION_S
        duration = float(os.getenv("KEN_BURNS_FAST_S", str(DURATION_S)))
        split = True
    else:
        duration = float(os.getenv("KEN_BURNS_SECONDS", "8"))
        split = False
    from content_generator.core.ist_dates import today_ist
    if on_date is None:
        date_str = today_ist().isoformat()
    elif hasattr(on_date, "isoformat"):
        date_str = on_date.isoformat()
    else:
        date_str = str(on_date)[:10]
    photos = paths[:8]
    plan = shot_plan(duration, len(photos), split=split and len(photos) >= 2)
    work = tempfile.mkdtemp(prefix="kenburns-")
    plates = broll_stills(label, work, date_str)
    inputs = _assemble(photos, plates, plan, work)
    graph_plan = [{**shot, "split": False} for shot in plan]
    graph = filtergraph(len(inputs), graph_plan, _words(reel), _font())
    if "xfade" in graph:
        logger.info("[ken_burns] refused a crossfade graph")
        shutil.rmtree(work, ignore_errors=True)
        return None
    out_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{label}_day{day}_{date_str}.mp4")
    hold = f"{max(shot['seconds'] for shot in plan) + 0.4:.2f}"
    cmd = [ffmpeg, "-nostdin", "-y", "-loglevel", "error"]
    for path in inputs:
        cmd.extend(["-loop", "1", "-framerate", str(FPS), "-t", hold, "-i", path])
    bed = _bed()
    if bed:
        cmd.extend(["-stream_loop", "-1", "-i", bed])
    else:
        cmd.extend(["-f", "lavfi", "-i", "anoisesrc=color=brown:r=44100:a=0.02"])
    audio_index = len(inputs)
    cmd.extend([
        "-filter_complex", graph,
        "-map", "[v]", "-map", f"{audio_index}:a",
        "-af", "volume=0.18",
        "-t", f"{duration:.2f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", "-movflags", "+faststart", out,
    ])
    try:
        subprocess.run(cmd, check=True, timeout=max(90, int(duration) * 4))
    except Exception as exc:
        logger.info("[ken_burns] encode failed: %s", type(exc).__name__)
        _fail(fast)
        return None
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not os.path.isfile(out) or os.path.getsize(out) < 1000:
        _fail(fast)
        return None
    logger.info("[ken_burns] rendered %s", out)
    return out


def _fail(fast: bool) -> None:
    try:
        from content_generator.core.obstacle_lessons import platform_for, record
        record(
            platform_for("growth_reel"), "growth_reel", "video_fallback", "provider",
            "ken_burns encode failed",
            "The local photo reel did not encode. Do not replace it with an AI jar.",
            fix="Retry ffmpeg on approved cutouts. Keep the 8.0 gate.",
        )
    except Exception:
        return
