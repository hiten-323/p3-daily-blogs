"""
Shared prompt blocks injected into every module prompt:
- brand_block()       — brand context + psychology frames + banned phrases
- build_avoid_block() — last-14-day repetition guard
"""
import logging
from content_generator.rotation import WEBSITE_URL

logger = logging.getLogger(__name__)

# Imported at call time to avoid circular imports at module load
def _get_brand_config():
    from config.brand_config import BRAND, POSITIONING, HASHTAG_SETS
    return BRAND, POSITIONING, HASHTAG_SETS


def brand_block() -> str:
    BRAND, POSITIONING, _ = _get_brand_config()
    try:
        from content_generator.core.coffee_psychology import frame_prompt_block
        psych = frame_prompt_block()
    except Exception:
        psych = ""

    try:
        from content_generator.core.shopify_catalog import format_catalog_for_prompt
        catalog_block = format_catalog_for_prompt()
    except Exception:
        catalog_block = ""

    return (
        f"BRAND: {BRAND['name']} (by {BRAND.get('company', 'Pure Pantry Provisions')}) — premium pure instant coffee, India.\n"
        f"USP: {POSITIONING['usp']}\n"
        f"Price: Rs{POSITIONING['price_per_cup']}/cup vs Rs{POSITIONING['cafe_price']} at cafes.\n"
        f"Website: {WEBSITE_URL} | Tagline: \"{BRAND['tagline']}\"\n"
        f"Tone: Premium but human. Honest, not corporate. Indian in DNA.\n"
        f"\n"
        f"{catalog_block}\n"
        f"\n"
        f"MANDATORY BRAND RULES — these are non-negotiable:\n"
        f"1. The brand name 'Purity Beans' MUST appear at least once in every caption, hook, body, and CTA.\n"
        f"2. The website '{WEBSITE_URL}' MUST appear in every caption and CTA.\n"
        f"3. Bold, Purista, Purica, and Prima may be called 100% coffee and zero chicory. "
        f"Prima / Premium Agglomerate is 100% Arabica and agglomerated, not freeze-dried. "
        f"Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta.\n"
        f"4. Ultra Blend is 70% coffee and 30% chicory. You may describe only that jar as lower caffeine. "
        f"Never call Ultra Blend 100% coffee, zero chicory, no chicory, chicory-free, or 0% chicory.\n"
        f"5. Do not invent prices, percentages, health outcomes, certificates, sourcing, or competitor recipes. "
        f"Do not write \"India's cleanest\", \"India's first\", or \"India's only\".\n"
        f"6. Never use generic phrases. Every line must be specific to Purity Beans.\n"
        f"\n"
        f"{psych}\n"
        f"\n"
        f"BANNED PHRASES: \"transform your mornings\" / \"elevate your experience\" / "
        f"\"perfect cup\" / \"fuel your day\" / \"game changer\" / \"level up\" / "
        f"\"discover the difference\" / \"premium quality\"\n"
        f"Return ONLY valid JSON — no markdown fences, no text outside the JSON object."
    )


def _recent_saved_content(days: int = 14) -> list[dict]:
    """Last N days of committed content files. There is no engine.database."""
    import datetime
    import json
    import re
    from pathlib import Path

    from content_generator.core.ist_dates import today_ist

    cutoff = today_ist() - datetime.timedelta(days=days)
    history: list[dict] = []
    root = Path("output")
    if not root.is_dir():
        return history
    for path in sorted(root.glob("content_*.json")):
        found = re.search(r"content_(\d{4}-\d{2}-\d{2})\.json$", path.name)
        if not found:
            continue
        try:
            stamped = datetime.date.fromisoformat(found.group(1))
        except ValueError:
            continue
        if stamped < cutoff:
            continue
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(content, dict):
            history.append({"date": found.group(1), "content": content})
    return history


def build_avoid_block() -> str:
    """
    Last 14 days of saved content, so today's post does not repeat a slug,
    title, hook, or angle. Returns empty string when nothing has been saved.
    """
    history = _recent_saved_content(days=14)
    if not history:
        return ""

    reel_hooks: list[str]      = []
    reel_archetypes: list[str] = []
    carousel_titles: list[str] = []
    save_mechs: list[str]      = []
    li_angles: list[str]       = []
    blog_posts: list[str]      = []

    for entry in history:
        c    = entry.get("content", {})
        date = entry.get("date", "")
        for reel in c.get("reels", []):
            h = (reel.get("hook_text") or "").strip()
            a = (reel.get("hook_archetype") or "").strip()
            if h: reel_hooks.append(f"[{date}] {h}")
            if a: reel_archetypes.append(f"[{date}] {a[:80]}")
        for car in c.get("carousels", []) + ([c.get("carousel")] if c.get("carousel") else []):
            t = (car.get("title") or "").strip()
            m = (car.get("save_mechanic") or "").strip()
            if t: carousel_titles.append(f"[{date}] {t}")
            if m: save_mechs.append(f"[{date}] {m[:80]}")
        li = (c.get("linkedin_post") or {})
        ag = (li.get("angle") or li.get("linkedin_angle") or "").strip()
        if ag: li_angles.append(f"[{date}] {ag[:80]}")
        blog = c.get("blog_post") or {}
        if isinstance(blog, dict):
            title = str(blog.get("title") or "").strip()
            slug = str(blog.get("slug") or "").strip()
            if title or slug:
                blog_posts.append(f"[{date}] {title} (slug: {slug})")

    if not any([reel_hooks, reel_archetypes, carousel_titles, blog_posts]):
        return ""

    lines = [
        "DO NOT REPEAT — 14-DAY CONTENT MEMORY",
        "Use a completely different archetype, angle, and trigger for every piece today.",
        "",
    ]
    if reel_archetypes:
        lines.append("REEL ARCHETYPES USED (pick a different category):")
        lines += [f"  - {a}" for a in reel_archetypes[-8:]]
        lines.append("")
    if reel_hooks:
        lines.append("REEL HOOKS USED (completely new wording AND new trigger required):")
        lines += [f"  - {h}" for h in reel_hooks[-6:]]
        lines.append("")
    if carousel_titles:
        lines.append("CAROUSEL TITLES USED:")
        lines += [f"  - {t}" for t in carousel_titles[-6:]]
        lines.append("")
    if save_mechs:
        lines.append("SAVE MECHANICS USED (use a different mechanic today):")
        lines += [f"  - {m}" for m in save_mechs[-4:]]
        lines.append("")
    if li_angles:
        lines.append("LINKEDIN ANGLES USED (use a completely different POV):")
        lines += [f"  - {a}" for a in li_angles[-4:]]
        lines.append("")
    if blog_posts:
        lines.append("BLOG TITLES AND SLUGS ALREADY USED (write a new slug and a new angle):")
        lines += [f"  - {b}" for b in blog_posts[-14:]]
    return "\n".join(lines)
