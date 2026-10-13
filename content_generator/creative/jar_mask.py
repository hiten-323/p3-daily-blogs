"""Full-jar alpha. The label is never threshold-cut.

A tight border flood-fill removes only the near-white studio sweep. rembg
may add a soft outer edge when it is installed; it cannot delete a pixel the
conservative mask kept. Near-white fringe that touches transparency is peeled.
The alpha is feathered only after a silhouette check passes.
"""
from __future__ import annotations

import hashlib
import logging

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

_WHITE_SUM = 6
_FRINGE_MIN = 242
_FRINGE_SPREAD = 18
_MISSING_RATIO = 0.005
_HOLE_PX = 30
_ROUGH_FACTOR = 1.35
_cache: dict[str, Image.Image] = {}
_rembg_session = None
_rembg_unavailable = False


class MaskIntegrityError(ValueError):
    """The cutout ate jar pixels, opened a hole, or left a jagged silhouette."""


def segment_product(img: Image.Image, cache_key: str | None = None) -> Image.Image:
    """RGBA jar, cropped to the product, or raise MaskIntegrityError."""
    source = img.convert("RGBA")
    key = cache_key or hashlib.sha1(source.tobytes()).hexdigest()
    cached = _cache.get(key)
    if cached is not None:
        return cached.copy()
    rgb = np.asarray(source.convert("RGB"))
    reference = _conservative_alpha(source)
    candidates = []
    learned = _rembg_alpha(source)
    if learned is not None and learned.shape == reference.shape:
        candidates.append(np.maximum(reference, learned))
    candidates.append(reference)
    issues = ["mask_empty"]
    chosen = reference
    for alpha in candidates:
        peeled = _peel_fringe(rgb, alpha)
        issues = mask_issues(peeled, reference, rgb)
        if not issues:
            chosen = peeled
            break
    else:
        raise MaskIntegrityError(", ".join(issues))
    chosen = _trim_floor_disc(rgb, chosen)
    rows = np.where((chosen > 16).any(axis=1))[0]
    cols = np.where((chosen > 16).any(axis=0))[0]
    if len(rows) == 0 or len(cols) == 0:
        raise MaskIntegrityError("mask_empty")
    chosen = chosen[rows[0]:rows[-1] + 1, cols[0]:cols[-1] + 1]
    source = source.crop((int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1))
    cut = _feather(_apply_alpha(source, chosen))
    _cache[key] = cut
    return cut.copy()


def mask_issues(alpha: np.ndarray, reference: np.ndarray, rgb: np.ndarray) -> list[str]:
    """Fail when label or jar pixels are gone, holed, or the edge is ragged."""
    issues: list[str] = []
    if int((alpha > 16).sum()) < 64:
        return ["mask_empty"]
    chromatic = (reference >= 200) & (rgb.min(axis=2) < 236)
    total = int(chromatic.sum())
    if total:
        missing = int((chromatic & (alpha < 16)).sum())
        if missing / total > _MISSING_RATIO:
            issues.append("jar_pixels_missing")
    if _hole_pixels(alpha) > _HOLE_PX:
        issues.append("mask_holes")
    ref_rough = _roughness(reference)
    got_rough = _roughness(alpha)
    if got_rough > max(8.0, ref_rough * _ROUGH_FACTOR):
        issues.append("jagged_edge")
    return issues


def _conservative_alpha(img: Image.Image) -> np.ndarray:
    """Studio white connected to the border becomes transparent. The jar stays."""
    work = img.convert("RGBA")
    width, height = work.size
    seeds = (
        (0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1),
        (width // 2, 0), (width // 2, height - 1), (0, height // 2), (width - 1, height // 2),
    )
    for seed in seeds:
        try:
            ImageDraw.floodfill(work, seed, (0, 0, 0, 0), thresh=_WHITE_SUM)
        except Exception as exc:
            logger.debug("[jar_mask] floodfill %s skipped: %s", seed, exc)
    return np.asarray(work.split()[-1])


def _peel_fringe(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Drop the near-white halo that touches transparency. Interior label white stays."""
    spread = rgb.max(axis=2).astype(np.int16) - rgb.min(axis=2).astype(np.int16)
    neutral = (rgb.min(axis=2) >= _FRINGE_MIN) & (spread < _FRINGE_SPREAD)
    out = alpha.copy()
    for _ in range(12):
        clear = out < 16
        touch = np.zeros(clear.shape, dtype=bool)
        touch[1:, :] |= clear[:-1, :]
        touch[:-1, :] |= clear[1:, :]
        touch[:, 1:] |= clear[:, :-1]
        touch[:, :-1] |= clear[:, 1:]
        kill = neutral & touch & (out > 0)
        if not bool(kill.any()):
            break
        out[kill] = 0
    return out


def _hole_pixels(alpha: np.ndarray) -> int:
    """Transparent pixels that do not touch the canvas edge."""
    from scipy import ndimage

    clear = alpha < 16
    labels, _count = ndimage.label(clear)
    if labels.max() == 0:
        return 0
    border = np.unique(np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    ]))
    border = border[border != 0]
    holes = clear & ~np.isin(labels, border)
    return int(holes.sum())


def _roughness(alpha: np.ndarray) -> float:
    opaque = alpha >= 128
    area = int(opaque.sum())
    if area < 16:
        return 99.0
    up = np.ones_like(opaque)
    down = np.ones_like(opaque)
    left = np.ones_like(opaque)
    right = np.ones_like(opaque)
    up[1:, :] = opaque[:-1, :]
    down[:-1, :] = opaque[1:, :]
    left[:, 1:] = opaque[:, :-1]
    right[:, :-1] = opaque[:, 1:]
    edge = opaque & ~(up & down & left & right)
    return float(edge.sum()) / (area ** 0.5)


def _trim_floor_disc(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Remove the studio-floor ellipse under the glass. The label stays."""
    out = alpha.copy()
    dark = rgb.min(axis=2)
    cols = np.where((out > 16).any(axis=0))[0]
    if len(cols) == 0:
        return out
    center_x = int((int(cols[0]) + int(cols[-1])) / 2)
    cx0 = max(0, center_x - 28)
    cx1 = min(out.shape[1], center_x + 28)
    for y in range(out.shape[0] - 1, int(out.shape[0] * 0.55), -1):
        opaque = out[y] > 16
        if int(opaque.sum()) < 8:
            continue
        center = opaque[cx0:cx1]
        if int(center.sum()) < 4:
            continue
        if float(np.median(dark[y, cx0:cx1][center])) < 70:
            break
        out[y, opaque] = 0
    return out


def _apply_alpha(img: Image.Image, alpha: np.ndarray) -> Image.Image:
    out = img.convert("RGBA")
    out.putalpha(Image.fromarray(alpha.astype(np.uint8), "L"))
    return out


def _feather(img: Image.Image) -> Image.Image:
    bands = img.convert("RGBA").split()
    soft = bands[3].filter(ImageFilter.GaussianBlur(radius=0.8))
    merged = Image.merge("RGBA", (*bands[:3], soft))
    return merged


def _rembg_alpha(img: Image.Image) -> np.ndarray | None:
    global _rembg_session, _rembg_unavailable
    if _rembg_unavailable:
        return None
    try:
        from rembg import new_session, remove
    except Exception as exc:
        _rembg_unavailable = True
        logger.info("[jar_mask] rembg unavailable, using the conservative mask: %s", exc)
        return None
    try:
        if _rembg_session is None:
            _rembg_session = new_session("u2net")
        cut = remove(img.convert("RGB"), session=_rembg_session)
        return np.asarray(cut.convert("RGBA").split()[-1])
    except Exception as exc:
        logger.info("[jar_mask] rembg skipped: %s", exc)
        return None
