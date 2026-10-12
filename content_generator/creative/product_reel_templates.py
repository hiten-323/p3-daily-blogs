"""Reusable product-reel templates for the daily creative path.

Hero videos in hero_videos/ are posted once and then retired. A template here
stays in the bank and can be copied into a dated render whenever the piece is
that SKU.

Gourmet Duo Mini has two uses:

- Exact template. When the piece is Gourmet Duo Mini, the dated render is a
  copy of brand_assets/reels/gourmet_duo_mini.mp4.
- Style reference. When the featured SKU is anything else, generation may
  borrow pacing, jar-forward framing, two-mood storytelling, and aesthetic.
  That path does not post the Mini file, its audio, or its SKU.

The committed file is silent store footage. Local library music may be muxed
onto a Mini-day copy, the same way generated reels do. Viral in-app audio is
still an audio_director recommendation, not a track on this file.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess

logger = logging.getLogger(__name__)

TEMPLATE_ID = "gourmet_duo_mini_reel"
TEMPLATE_SLUG = "gourmet_duo_mini"
TEMPLATE_PATH = os.path.join("brand_assets", "reels", "gourmet_duo_mini.mp4")
INSPIRATION_ID = "gourmet_duo_mini_style"

# Transferable craft. No Mini price, jar pair, or chicory claim lives here.
_STYLE_CUES = (
    {
        "id": "pacing",
        "cue": "About ten seconds, beats near two seconds, two moods that resolve before the end.",
    },
    {
        "id": "framing",
        "cue": "Vertical 1080x1920 with the featured jar forward so the glass and label stay readable.",
    },
    {
        "id": "storytelling",
        "cue": (
            "Two moods. A single jar shows two moods of that jar. A duo shows its own two jars. "
            "Do not swap in the Gourmet Duo Mini pair."
        ),
    },
    {
        "id": "aesthetic",
        "cue": "Warm editorial glass-jar photography. The jar is the hero. Not a poster turned into a video.",
    },
)

_MINI = (
    "gourmet duo mini",
    "gourmet_duo_mini",
    "gourmet-duo-mini",
    "pb-gourmet-duo-50",
)
_FULL = (
    "gourmet duo",
    "gourmet_duo",
    "gourmet-duo",
    "pb-gourmet-duo-100",
)
_OTHER = (
    ("ultra_blend", ("ultra blend", "ultra_blend", "ultrablend", "ultra-blend")),
    ("gourmet_duo", _FULL),
    ("variety_box", ("variety box", "variety_box")),
    ("prima", ("prima", "premium agglomerate")),
    ("purista", ("purista",)),
    ("purica", ("purica",)),
    ("bold", ("bold",)),
)


def _norm(value: str) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _is_mini(value: str) -> bool:
    raw = str(value or "").lower()
    folded = _norm(value)
    return any(token in raw or token.replace("-", " ").replace("_", " ") in folded for token in _MINI)


def _slug_from_product(product: str) -> str:
    if not str(product or "").strip():
        return ""
    if _is_mini(product):
        return TEMPLATE_SLUG
    folded = _norm(product)
    raw = str(product).lower()
    for slug, tokens in _OTHER:
        if any(token in raw or _norm(token) in folded for token in tokens):
            return slug
    return ""


def _slug_from_text(text: str) -> str:
    return _slug_from_product(text)


def _stamps_zero_chicory_on_ultra(text: str) -> bool:
    from content_generator.core.product_truth import product_truth_findings
    for item in product_truth_findings(text or ""):
        reason = str(item.get("reason") or "")
        if "Ultra Blend" in reason and "zero-chicory" in reason:
            return True
    return False


def _component_price(slug: str) -> int:
    from content_generator.core.shopify_catalog import get_product
    product = get_product(slug) or {}
    for variant in product.get("variants") or []:
        if str(variant.get("weight")) == "50g":
            return int(variant["price"])
    raise KeyError(slug)


def template_record() -> dict | None:
    """Catalog-backed descriptor for the Gourmet Duo Mini reel, or None if it cannot be reused."""
    from content_generator.core.shopify_catalog import get_product
    product = get_product(TEMPLATE_SLUG)
    if not product or product.get("pure_coffee") is not True:
        return None
    if "0%" not in str(product.get("chicory") or ""):
        return None
    if not os.path.isfile(TEMPLATE_PATH):
        return None
    variant = (product.get("variants") or [{}])[0]
    return {
        "template_id": TEMPLATE_ID,
        "slug": TEMPLATE_SLUG,
        "path": TEMPLATE_PATH.replace("\\", "/"),
        "reusable": True,
        "width": 1080,
        "height": 1920,
        "duration_s": 10,
        "sku": variant.get("sku") or "",
        "price_inr": int(variant.get("price") or 0),
        "compare_at_inr": _component_price("purista") + _component_price("purica"),
        "components": ["purista_50g", "purica_50g"],
        "packaging": product.get("packaging") or "",
        "store": "https://p3online.in",
        "pure_coffee": True,
        "chicory": product.get("chicory") or "",
        "allowed_claims": [
            "100% coffee",
            "no chicory",
            "certified food-grade lead-free glass jars",
        ],
        # The committed file's audio track is digital silence. Render may mux a
        # local library track; viral catalogue audio is not attached here.
        "audio_embedded": False,
        "audio_hook": "audio_director.get_audio_plan",
    }


def allowed_claim_text(record: dict | None = None) -> str:
    """Claim-safe caption for this SKU. Prices come from the catalog."""
    record = record or template_record()
    if not record:
        return ""
    packaging = record.get("packaging") or "certified food-grade lead-free glass jars"
    return (
        f"Gourmet Duo Mini is Purista 50g and Purica 50g, 100% coffee, no chicory, "
        f"in {packaging}. ₹{record['price_inr']} (was ₹{record['compare_at_inr']}). "
        f"Shop at {record['store']}"
    )


def inspiration_record(featured_product: str = "") -> dict | None:
    """Style cues from the Mini reel for a day that is not that SKU.

    The bank filename is named so a person can open the reference. It is not
    a publish path. Pixels, audio, and SKU stay on the Mini template day.
    """
    if _is_mini(featured_product):
        return None
    if template_record() is None:
        return None
    return {
        "inspiration_id": INSPIRATION_ID,
        "mode": "style_cues",
        "source_template_id": TEMPLATE_ID,
        "source_filename": os.path.basename(TEMPLATE_PATH),
        "publish_source_video": False,
        "copied": {"pixels": False, "audio": False, "sku": False},
        "featured_product": str(featured_product or "").strip(),
        "featured_slug": _slug_from_product(featured_product),
        "cues": [dict(item) for item in _STYLE_CUES],
        "audio_note": (
            "The reference file's audio track is digital silence and is not copied. "
            "Viral or in-app audio stays a manual audio_director choice."
        ),
    }


def inspiration_prompt_block(featured_product: str = "") -> str:
    """LLM context: borrow craft from the Mini reel, keep today's product facts."""
    record = inspiration_record(featured_product)
    if not record:
        return ""
    featured = record["featured_product"] or "the product named in this brief"
    cue_lines = "\n".join(f"- {item['id']}: {item['cue']}" for item in record["cues"])
    return (
        "CREATIVE REFERENCE — STYLE ONLY:\n"
        f"The store reel {record['source_filename']} is a reusable reference for pacing, "
        "jar-forward framing, two-mood storytelling, and aesthetic.\n"
        f"Today's featured product is {featured}. Borrow the style for that product.\n"
        "Do not post that file. Do not copy its pixels, its audio, or its SKU.\n"
        "Do not write the reference filename or product name into captions, hooks, "
        "on-screen text, or product fields.\n"
        "Do not move the reference product's identity, price, or claims onto today's SKU.\n"
        "Ultra Blend is 70% coffee and 30% chicory.\n"
        "Growth-track pieces with no jar stay unbranded.\n"
        f"{cue_lines}\n"
        f"{record['audio_note']}"
    )


def visual_style_line(featured_product: str = "") -> str:
    """Short direction for an image or motion prompt. No filename, no Mini claims."""
    if inspiration_record(featured_product) is None:
        return ""
    name = str(featured_product or "").strip() or "the featured jar"
    return (
        f" Style cues only: jar-forward vertical framing, two moods of {name}, "
        "warm editorial glass-jar light, beats near two seconds. "
        "Do not swap in a different product or label."
    )


def select_product_reel(product: str | None = None, text: str = "") -> dict | None:
    """Return the mini reel when the piece is that SKU.

    Ultra Blend never receives it. The full-size Gourmet Duo does not either.
    A zero-chicory claim about Ultra Blend blocks the template even if the duo
    is also named.
    """
    if _stamps_zero_chicory_on_ultra(text):
        return None
    product_slug = _slug_from_product(product or "")
    text_slug = _slug_from_text(text or "")
    if product_slug == "ultra_blend":
        return None
    if product_slug == TEMPLATE_SLUG or (not product_slug and text_slug == TEMPLATE_SLUG):
        return template_record()
    return None


# Style metadata names the reference file. It is not the piece's product copy,
# and a second attach pass must not treat it as a Mini-day caption.
_PIECE_TEXT_SKIP = {
    "audio",
    "reel_inspiration",
    "reference_reel_path",
    "reference_reel_template_id",
    "reference_reel_reusable",
    "reference_reel_audio_embedded",
}


def _piece_text(piece: dict) -> str:
    parts: list[str] = []

    def walk(node, skip_keys: bool = False) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if skip_keys and key in _PIECE_TEXT_SKIP:
                    continue
                walk(value, skip_keys=True)
        elif isinstance(node, list):
            for item in node:
                walk(item, skip_keys=skip_keys)
        elif isinstance(node, str):
            parts.append(node)

    walk(piece, skip_keys=True)
    return "\n".join(parts)


def _is_template_path(path) -> bool:
    if not path:
        return False
    return os.path.basename(str(path)) == os.path.basename(TEMPLATE_PATH)


def _strip_template(piece: dict) -> None:
    if piece.get("reference_reel_template_id") == TEMPLATE_ID or _is_template_path(piece.get("reference_reel_path")):
        piece.pop("reference_reel_template_id", None)
        piece.pop("reference_reel_path", None)
        piece.pop("reference_reel_reusable", None)
        piece.pop("reference_reel_audio_embedded", None)
    explicit = _slug_from_product(str(piece.get("product") or ""))
    if piece.get("product_slug") == TEMPLATE_SLUG and (
        explicit in {"ultra_blend", "gourmet_duo"} or _stamps_zero_chicory_on_ultra(_piece_text(piece))
    ):
        piece.pop("product_slug", None)


def _has_creative_body(piece: dict) -> bool:
    return any(key != "reel_inspiration" for key in piece)


def attach_product_reel(
    piece: dict,
    featured_product: str = "",
    *,
    allow_inspiration: bool = True,
) -> dict | None:
    """Attach the Mini file only when this piece is that SKU.

    Other pieces may receive style cues. Those cues never set the publish path.
    """
    if not isinstance(piece, dict) or not _has_creative_body(piece):
        return None
    selected = select_product_reel(
        product=str(piece.get("product") or piece.get("product_slug") or ""),
        text=_piece_text(piece),
    )
    if selected:
        piece.pop("reel_inspiration", None)
        piece["reference_reel_template_id"] = selected["template_id"]
        piece["reference_reel_path"] = selected["path"]
        piece["reference_reel_reusable"] = True
        piece["reference_reel_audio_embedded"] = False
        piece["product_slug"] = selected["slug"]
        try:
            from content_generator.core.brand_guard import get_product_references
            jars = get_product_references("Gourmet Duo Mini")
            if jars:
                piece["reference_jar_paths"] = jars
        except Exception as exc:
            logger.debug("[product_reel] jar references skipped: %s", exc)
        return selected
    _strip_template(piece)
    if not allow_inspiration:
        piece.pop("reel_inspiration", None)
        return None
    subject = str(piece.get("product") or featured_product or "").strip()
    record = None if _is_mini(subject) else inspiration_record(subject)
    if record:
        piece["reel_inspiration"] = record
    else:
        piece.pop("reel_inspiration", None)
    return None


def attach_product_reels(content: dict, featured_product: str = "") -> None:
    """Exact Mini template, or style cues when the featured SKU is not Mini.

    Growth-track pieces stay unbranded: stolen template fields are removed and
    no jar-forward inspiration is added.
    """
    if not isinstance(content, dict):
        return
    featured = str(featured_product or content.get("featured_product") or "").strip()
    if featured:
        content["featured_product"] = featured
    for reel in content.get("reels") or []:
        if isinstance(reel, dict):
            attach_product_reel(reel, featured_product=featured)
    for key in ("yt_short", "instagram_post"):
        piece = content.get(key)
        if isinstance(piece, dict):
            attach_product_reel(piece, featured_product=featured)
    growth = content.get("growth_reel")
    if isinstance(growth, dict):
        attach_product_reel(growth, featured_product=featured, allow_inspiration=False)
    stories = content.get("stories")
    if isinstance(stories, dict):
        for sub in stories.values():
            if isinstance(sub, dict):
                attach_product_reel(sub, featured_product=featured)
    if featured and inspiration_record(featured):
        content["reel_inspiration"] = inspiration_record(featured)
    elif featured and _is_mini(featured):
        content.pop("reel_inspiration", None)


def resolve_reusable_reel(piece: dict) -> str | None:
    """Filesystem path of the template when this piece may reuse it."""
    selected = attach_product_reel(piece) if isinstance(piece, dict) else None
    if not selected:
        return None
    path = selected["path"]
    return path if os.path.isfile(path) else None


def _date_str(on_date) -> str:
    if on_date is None:
        from content_generator.core.ist_dates import today_ist
        return today_ist().isoformat()
    if hasattr(on_date, "isoformat"):
        return on_date.isoformat()
    return str(on_date)[:10]


def _mux_local_audio(source: str, dest: str, day: int, hook_text: str) -> bool:
    """Mux a royalty-free library track. Viral catalogue audio is never implied."""
    music = os.getenv("REEL_MUSIC_FILE")
    if not (music and os.path.exists(music)):
        try:
            from content_generator.creative.audio_director import get_audio_plan
            music = (get_audio_plan(hook_text, day) or {}).get("local_track")
        except Exception as exc:
            logger.debug("[product_reel] audio plan skipped: %s", exc)
            music = None
    if not music or not os.path.exists(str(music)):
        return False
    cmd = [
        "ffmpeg", "-y", "-i", source, "-i", str(music),
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "copy", "-c:a", "aac", "-shortest",
        dest,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=60)
    except Exception as exc:
        logger.info("[product_reel] local audio mux unavailable (%s)", type(exc).__name__)
        return False
    if proc.returncode != 0 or not os.path.isfile(dest) or os.path.getsize(dest) < 10_000:
        if os.path.isfile(dest):
            os.remove(dest)
        logger.info("[product_reel] local audio mux failed (code %s); visual template copied silent", proc.returncode)
        return False
    logger.info("[product_reel] muxed local library audio onto %s", os.path.basename(dest))
    return True


def materialize_template(
    source: str,
    day: int,
    label: str,
    on_date=None,
    out_dir: str | None = None,
    hook_text: str = "",
) -> str:
    """Copy the reusable template into today's dated creative path. Never consumes the source."""
    directory = out_dir or os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    os.makedirs(directory, exist_ok=True)
    dest = os.path.join(directory, f"{label}_day{day}_{_date_str(on_date)}.mp4")
    if os.path.abspath(source) == os.path.abspath(dest):
        return dest
    if _mux_local_audio(source, dest, day, hook_text):
        return dest
    shutil.copyfile(source, dest)
    return dest
