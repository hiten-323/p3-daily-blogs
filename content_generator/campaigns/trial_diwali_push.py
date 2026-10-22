"""Organic Instagram sales push, 21 Oct 2026 through 20 Nov 2026."""
from __future__ import annotations

import datetime as _dt
import json
import logging
import os
import re
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "trial_diwali_push.json"
REEL_CTA = "Link in bio to order at p3online.in"
STORY_CTA = "DM us to order"

_TRIAL_CUTOUTS = {
    "bold": "brand_assets/approved_photos/bold/bold_50g_cutout_front.png",
    "purista": "brand_assets/approved_photos/purista/purista_50g_cutout_front.png",
    "purica": "brand_assets/approved_photos/purica/purica_50g_cutout_front.png",
    "ultra_blend": "brand_assets/approved_photos/ultra_blend/ultra_blend_50g_cutout_front.png",
}
_TRIAL_FACT = {
    "bold": "Bold 50g trial jar. Pure coffee in a glass jar. Rs{price}.",
    "purista": "Purista 50g trial jar. Freeze-dried pure Robusta. Rs{price}.",
    "purica": "Purica 50g trial jar. Freeze-dried pure Arabica. Rs{price}.",
}
_TRIAL_ON = {"bold": "BOLD 50g", "purista": "PURISTA 50g", "purica": "PURICA 50g"}
_TRIAL_SUB = {"bold": "Pure coffee", "purista": "Pure Robusta", "purica": "Pure Arabica"}

_URL = re.compile(r"https?://\S+")
_ORDER_BY_UNTIL = _dt.date(2026, 11, 2)
_CONFIRMED_CODES = ("FREESHIP", "BUNDLE10")
_BANNED = re.compile(
    r"100\s*%|100\s*percent|\bfresh\b|lab[\s-]?tested|zero\s+acidity|"
    r"order\s+by|countdown|only\s+\d+\s+(?:left|units|jars)|"
    r"\bprima\b|variety\s*box|ultra[\s-]*blend|"
    r"gourmet[\s-]+duo(?![\s-]+mini)|"
    r"\b(?:cure|cures|detox|weight\s+loss|immunity)\b",
    re.I,
)


def load_config(path=None) -> dict:
    raw = json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("sales push config must be an object")
    return raw


def _as_date(value) -> _dt.date | None:
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    text = str(value or "").strip()[:10]
    try:
        return _dt.date.fromisoformat(text)
    except ValueError:
        return None


def _handle(slug: str) -> str:
    from content_generator.core.shopify_catalog import get_product
    return str((get_product(str(slug or "")) or {}).get("handle") or "")


def excluded_keys(cfg: dict | None = None) -> set[str]:
    cfg = cfg or load_config()
    from content_generator.core.price_truth import HANDLE_TO_SLUG
    keys: set[str] = set()
    for item in cfg.get("exclude") or []:
        raw = str(item or "").strip().lower()
        if not raw:
            continue
        keys.add(raw)
        keys.add(raw.replace("-", "_"))
        keys.add(raw.replace("_", "-"))
        mapped = HANDLE_TO_SLUG.get(raw)
        if mapped:
            keys.add(mapped)
    return keys


def is_excluded(slug: str, cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    keys = excluded_keys(cfg)
    raw = str(slug or "").strip().lower()
    if not raw:
        return True
    if raw in keys or raw.replace("_", "-") in keys or raw.replace("-", "_") in keys:
        return True
    handle = _handle(raw.replace("-", "_"))
    return bool(handle) and handle.lower() in keys


def _in_window(day: _dt.date, cfg: dict) -> bool:
    start, end = _as_date(cfg.get("start")), _as_date(cfg.get("end"))
    return bool(start and end and start <= day <= end)


def active(on, cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    day = _as_date(on)
    return bool(day and _in_window(day, cfg))


def diwali_angle(on, cfg: dict | None = None) -> bool:
    cfg = cfg or load_config()
    day = _as_date(on)
    through = _as_date(cfg.get("diwali_angle_through"))
    return bool(day and through and active(day, cfg) and day <= through)


def _checked_price(spec: dict) -> int | None:
    from content_generator.core.price_truth import load, variant_price
    slug = str(spec.get("slug") or "")
    grams = spec.get("grams")
    live = variant_price(slug, float(grams)) if grams else None
    if live is None:
        rows = (load().get(slug) or {}).get("variants") or []
        if len(rows) == 1:
            live = rows[0].get("price")
    if live is None:
        return None
    got = int(round(float(live)))
    verified = spec.get("verified_price")
    if verified is not None and int(verified) != got:
        logger.warning("[sales-push] holding %s; Shopify price does not match the verified price", slug)
        return None
    return got


def _pool(cfg: dict) -> list[dict]:
    ready = []
    for spec in cfg.get("promote") or []:
        if not isinstance(spec, dict):
            continue
        slug = str(spec.get("slug") or "").strip().lower()
        if not slug or is_excluded(slug, cfg):
            continue
        price = _checked_price(spec)
        handle = _handle(slug)
        if price is None or not handle:
            continue
        ready.append({**spec, "slug": slug, "price": price, "handle": handle})
    return ready


def offer_for(on, cfg: dict | None = None) -> dict | None:
    cfg = cfg or load_config()
    day = _as_date(on)
    start = _as_date(cfg.get("start")) if cfg else None
    if day is None or start is None or not _in_window(day, cfg):
        return None
    items = _pool(cfg)
    trials = [p for p in items if p.get("role") == "trial"]
    gifts = [p for p in items if p.get("role") == "gift"]
    idx = (day - start).days
    if trials and gifts:
        spec = trials[(idx // 2) % len(trials)] if idx % 2 == 0 else gifts[(idx // 2) % len(gifts)]
    else:
        seq = trials or gifts
        if not seq:
            return None
        spec = seq[idx % len(seq)]
    return {
        "slug": spec["slug"], "role": spec.get("role") or "", "grams": spec.get("grams"),
        "price": spec["price"], "handle": spec["handle"], "low_stock_units": spec.get("low_stock_units"),
        "diwali_angle": spec.get("role") == "gift" and diwali_angle(day, cfg), "date": day.isoformat(),
    }


def _entry_price(cfg: dict) -> int | None:
    want = str(cfg.get("entry_price_slug") or "bold")
    pool = _pool(cfg)
    for spec in pool:
        if spec["slug"] == want and spec.get("role") == "trial":
            return int(spec["price"])
    trials = [int(p["price"]) for p in pool if p.get("role") == "trial"]
    return min(trials) if trials else None


def _code_line(cfg: dict) -> str:
    found = []
    for item in cfg.get("codes") or []:
        code = item.get("code") if isinstance(item, dict) else item
        code = str(code or "").strip().upper()
        if code in _CONFIRMED_CODES and code not in found:
            found.append(code)
    return " ".join(f"Use code {code}." for code in found)


def _deadline_line(offer: dict, cfg: dict) -> str:
    spec = cfg.get("order_by") if isinstance(cfg.get("order_by"), dict) else {}
    if offer.get("role") != "gift" or offer.get("slug") != str(spec.get("slug") or ""):
        return ""
    day, through = _as_date(offer.get("date")), _as_date(spec.get("through"))
    if not day or not through or day > through or day > _ORDER_BY_UNTIL:
        return ""
    if str(spec.get("line") or "").strip().rstrip(".").lower() != "order by 2 nov":
        return ""
    return "Order by 2 Nov."


def _body(offer: dict, cfg: dict) -> str:
    price = int(offer["price"])
    slug = offer["slug"]
    if offer.get("role") == "trial":
        template = _TRIAL_FACT.get(slug)
        if not template:
            return ""
        fact = template.format(price=price)
        entry = _entry_price(cfg)
        if entry is None:
            return fact
        return f"{fact}\n\nTrial jars from Rs{entry}."
    if slug != "gourmet_duo_mini":
        return ""
    angle = " A Diwali gift pack." if offer.get("diwali_angle") else ""
    return (
        "Gourmet Duo Mini. Purista 50g and Purica 50g. "
        f"Freeze-dried pure Robusta and pure Arabica.{angle} Rs{price}."
    )


def _stock_line(offer: dict, cfg: dict, body: str) -> str:
    if not cfg.get("limited_stock_copy"):
        return ""
    units = offer.get("low_stock_units")
    if not isinstance(units, int) or units <= 0:
        return ""
    line = "Limited stock."
    if re.search(r"countdown|order\s+by|only\s+\d+|hours|tonight|hurry|\d+\s+left", line, re.I):
        return ""
    from content_generator.core.viral_gate import honesty_issues
    if honesty_issues({"caption": f"{body} {line}"}):
        return ""
    return line


def product_url(slug: str, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    handle = _handle(slug)
    if not handle or is_excluded(slug, cfg):
        return ""
    utm = cfg.get("utm") or {}
    query = urlencode([
        ("utm_source", str(utm.get("utm_source") or "instagram")),
        ("utm_medium", str(utm.get("utm_medium") or "organic")),
        ("utm_campaign", str(utm.get("utm_campaign") or "trial_diwali_push")),
    ])
    return f"https://p3online.in/products/{handle}?{query}"


def _frames(offer: dict, cta: str, entry: int | None) -> list[dict]:
    if offer.get("role") == "gift":
        head = "DIWALI GIFT" if offer.get("diwali_angle") else "GIFT PACK"
        return [
            {"on": head, "sub": "Gourmet Duo Mini"},
            {"on": "TWO 50g JARS", "sub": "Purista and Purica"},
            {"on": f"Rs{offer['price']}", "sub": cta},
        ]
    slug = offer["slug"]
    from_line = f"Trial jars from Rs{entry}" if entry is not None else "Trial jar"
    return [
        {"on": _TRIAL_ON[slug], "sub": _TRIAL_SUB[slug]},
        {"on": f"Rs{offer['price']}", "sub": from_line},
        {"on": "ORDER", "sub": cta},
    ]


def _for_gates(text: str, slug: str | None, on) -> str:
    blob = _URL.sub(" ", str(text or ""))
    day = _as_date(on)
    if slug == "gourmet_duo_mini" and day and day <= _ORDER_BY_UNTIL:
        blob = re.sub(r"\border by 2 nov\.?", " ", blob, flags=re.I)
    return blob


def copy_problems(text: str, slug: str | None = None, on=None) -> list[str]:
    blob = _for_gates(text, slug, on)
    reasons: list[str] = []
    if _BANNED.search(blob):
        reasons.append("banned_phrase")
    if slug and is_excluded(slug):
        reasons.append("excluded_product")
    try:
        from content_generator.core.claim_verifier import verify_claims
        reasons.extend(f"claim:{item.get('type')}" for item in verify_claims(blob))
    except Exception as exc:
        reasons.append(f"claim_verifier:{type(exc).__name__}")
    try:
        from content_generator.core.product_truth import product_truth_findings
        reasons.extend("product_truth" for _ in product_truth_findings(blob, featured=slug))
    except Exception as exc:
        reasons.append(f"product_truth:{type(exc).__name__}")
    try:
        from content_generator.core.viral_gate import honesty_issues
        reasons.extend(f"honesty:{item}" for item in honesty_issues({"caption": blob, "date": str(on or "")[:10]}))
    except Exception as exc:
        reasons.append(f"honesty:{type(exc).__name__}")
    return reasons


def build_piece(on, surface: str, cfg: dict | None = None) -> dict | None:
    cfg = cfg or load_config()
    offer = offer_for(on, cfg)
    if not offer:
        return None
    surface = "story" if str(surface).lower() == "story" else "reel"
    cta = STORY_CTA if surface == "story" else REEL_CTA
    body = _body(offer, cfg)
    if not body:
        return None
    deadline = _deadline_line(offer, cfg)
    if deadline:
        body = f"{body} {deadline}"
    codes = _code_line(cfg)
    if codes:
        body = f"{body}\n\n{codes}"
    stock = _stock_line(offer, cfg, body)
    if stock:
        body = f"{body} {stock}"
    url = product_url(offer["slug"], cfg)
    if not url:
        return None
    caption = f"{body}\n\n{url}\n\n{cta}"
    frames = _frames(offer, cta, _entry_price(cfg) if offer.get("role") == "trial" else None)
    spoken = caption + "\n" + " ".join(f"{fr.get('on','')} {fr.get('sub','')}" for fr in frames)
    if copy_problems(spoken, offer["slug"], offer.get("date")):
        logger.warning("[sales-push] held %s copy for %s", surface, offer["slug"])
        return None
    return {
        "surface": surface, "slug": offer["slug"], "role": offer["role"], "caption": caption,
        "cta": cta, "headline": frames[0]["on"], "sub": frames[-1]["sub"], "product_url": url,
        "frames": frames, "price": offer["price"], "date": offer.get("date"),
        "diwali_angle": bool(offer.get("diwali_angle")),
    }


def attach(content: dict, on, cfg: dict | None = None) -> dict:
    if not isinstance(content, dict):
        return content
    cfg = cfg or load_config()
    base = {
        "campaign": str(cfg.get("id") or "trial_diwali_push"),
        "ends_on": str(cfg.get("end") or ""),
        "organic_only": True,
    }
    if not active(on, cfg):
        content["sales_push"] = {**base, "active": False, "reason": "outside_window"}
        return content
    offer = offer_for(on, cfg)
    reel = build_piece(on, "reel", cfg)
    story = build_piece(on, "story", cfg)
    if not offer or not reel or not story:
        content["sales_push"] = {**base, "active": False, "reason": "no_eligible_offer"}
        return content
    content["sales_push"] = {
        **base, "active": True, "date": offer["date"], "slug": offer["slug"], "role": offer["role"],
        "price": offer["price"], "handle": offer["handle"], "product_url": reel["product_url"],
        "diwali_angle": offer["diwali_angle"], "reel": reel, "story": story,
    }
    return content


def _pack_path(slug: str) -> str:
    return os.path.join("brand_assets", "approved_photos", slug, f"{slug}_pack_cutout.png")


def _ensure_pack(slug: str) -> str | None:
    path = _pack_path(slug)
    if os.path.isfile(path) and os.path.getsize(path) > 1000:
        return path
    from content_generator.core.shopify_catalog import get_product
    url = str((get_product(slug) or {}).get("hero_image") or "")
    if not url.startswith("https://"):
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        urllib.request.urlretrieve(url, path)  # noqa: S310 — Shopify CDN product image
    except Exception as exc:
        logger.warning("[sales-push] pack image unavailable for %s (%s)", slug, type(exc).__name__)
        return None
    return path if os.path.isfile(path) else None


def resolve_asset(slug: str, cfg: dict | None = None) -> str | None:
    cfg = cfg or load_config()
    raw = str(slug or "").strip().lower().replace("-", "_")
    if not raw or is_excluded(raw, cfg):
        return None
    if raw in _TRIAL_CUTOUTS:
        path = _TRIAL_CUTOUTS[raw]
        return path if os.path.isfile(path) else None
    spec = next((p for p in _pool(cfg) if p["slug"] == raw and p.get("role") == "gift"), None)
    if not spec:
        return None
    return _ensure_pack(raw)


def register_source(path: str) -> dict:
    from content_generator.creative.jar_provenance import record_jar_provenance
    return record_jar_provenance(path, jar_asset_id=path, render_source="approved_photo")


def render_assets(content: dict, day_number: int, on_date) -> dict:
    block = content.get("sales_push") if isinstance(content, dict) else None
    if not isinstance(block, dict) or not block.get("active"):
        return {}
    asset = resolve_asset(str(block.get("slug") or ""))
    if not asset:
        block["held"] = "missing_real_asset"
        return {}
    try:
        registered = register_source(asset)
    except Exception as exc:
        logger.warning("[sales-push] provenance register failed (%s)", type(exc).__name__)
        registered = {}
    if not registered.get("asset_real_jar_verified"):
        block["held"] = "provenance"
        return {}
    from content_generator.creative.cinematic_motion import render_cinematic_until_pass
    from content_generator.creative.jar_provenance import record_jar_provenance, verify_jar_provenance
    out_dir = os.getenv("CREATIVE_OUTPUT_DIR", os.path.join("output", "creative"))
    os.makedirs(out_dir, exist_ok=True)
    day = on_date.isoformat() if hasattr(on_date, "isoformat") else str(on_date)[:10]
    rendered = {}
    for surface, fmt in (("reel", "push_reel"), ("story", "push_story")):
        piece = block.get(surface) if isinstance(block.get(surface), dict) else None
        if not piece:
            continue
        out_path = os.path.join(out_dir, f"sales_{surface}_day{day_number}_{day}.mp4")
        try:
            meta = render_cinematic_until_pass(
                block["slug"], piece.get("frames") or [], out_path,
                seconds=10.0, seed=int(day_number or 0), format_type=fmt,
                on_date=day, concepts=True, jar_source=asset, end_cta=piece.get("cta"),
            )
        except Exception as exc:
            logger.warning("[sales-push] %s render failed (%s)", surface, type(exc).__name__)
            piece["held"] = "render_error"
            _note_campaign_obstacle(surface, "render", str(exc)[:200])
            continue
        verdict = (meta or {}).get("visual_gate") or {}
        variety = (meta or {}).get("variety_gate") or {}
        poster = (meta or {}).get("poster")
        if not meta or not verdict.get("passed") or not variety.get("passed") or not poster:
            piece["held"] = "visual_or_variety_gate"
            _note_campaign_obstacle(surface, "aesthetic", "visual_or_variety_gate")
            continue
        record_jar_provenance(poster, jar_asset_id=asset, render_source="cinematic_real_jar")
        if not verify_jar_provenance(poster).get("verified"):
            piece["held"] = "provenance"
            _note_campaign_obstacle(surface, "provenance", "real jar provenance failed")
            continue
        piece["video_path"] = meta.get("path") or out_path
        piece["poster_path"] = poster
        piece["visual_gate"] = verdict
        piece["variety_gate"] = variety
        piece.pop("held", None)
        rendered[surface] = piece["video_path"]
    return rendered


def _note_campaign_obstacle(surface: str, gate: str, reason: str) -> None:
    try:
        from content_generator.core.obstacle_lessons import record
        record("instagram_campaign", f"sales_{surface}", "generation", gate, reason, "")
    except Exception:
        logger.debug("[sales-push] lesson not recorded for %s", surface)


def publish_for_slot(content: dict, slot: str, day: int) -> dict:
    block = content.get("sales_push") if isinstance(content, dict) else None
    if not isinstance(block, dict) or not block.get("active"):
        return {"skipped": True, "reason": "inactive"}
    surface = {"morning": "story", "evening": "reel"}.get(slot)
    if not surface:
        return {"skipped": True, "reason": "slot"}
    piece = block.get(surface) if isinstance(block.get(surface), dict) else {}
    video = str(piece.get("video_path") or "")
    poster = str(piece.get("poster_path") or "")
    if piece.get("held") or not video or not poster:
        return {"skipped": True, "reason": piece.get("held") or "not_rendered"}
    if not (piece.get("visual_gate") or {}).get("passed") or not (piece.get("variety_gate") or {}).get("passed"):
        return {"skipped": True, "reason": "visual_gate"}
    spoken = " ".join(str(piece.get(k) or "") for k in ("caption", "headline", "sub", "cta"))
    if copy_problems(spoken, str(block.get("slug") or ""), block.get("date")):
        return {"skipped": True, "reason": "claim_gate"}
    from content_generator.creative.jar_provenance import verify_jar_provenance
    if not verify_jar_provenance(poster).get("verified"):
        return {"skipped": True, "reason": "provenance"}
    from content_generator.core.publish_bar import quality_block, reason_code
    block = quality_block(piece, f"sales_{surface}")
    if block:
        try:
            from content_generator.core.obstacle_lessons import record
            record("instagram_campaign", f"sales_{surface}", "publish", reason_code(block), block[:300], "")
        except Exception:
            logger.debug("[sales-push] lesson not recorded")
        return {"skipped": True, "reason": reason_code(block)}
    platform = "instagram_sales_story" if surface == "story" else "instagram_sales_reel"

    def _publish() -> dict:
        if surface == "reel":
            from content_generator.publisher.instagram import _post_reel_direct_binary
            return _post_reel_direct_binary(video, str(piece.get("caption") or ""))
        from content_generator.publisher.instagram import post_prepared_story
        return post_prepared_story(poster, video)

    from content_generator.publisher.publishing_ledger import publish_with_ledger
    return publish_with_ledger(platform, content, slot, int(day or 0), _publish)
