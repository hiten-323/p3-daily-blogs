"""SEO, link, duplicate, and product-truth checks for a blog asset.

The Shopify publisher stays off unless SHOPIFY_BLOG_ENABLED=true. These checks
still run before a post can be treated as valid, so a bad article is not
saved as if it were ready to publish.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_URL_PUNCT = re.compile(
    r"(https?://(?:www\.)?p3online\.in(?:/[^\s<\"']*)?)[.,;:)]+(?=(\s|<|$))",
    re.I,
)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,7}")
_DATE = re.compile(r"content_(\d{4}-\d{2}-\d{2})\.json$")


def normalize_text(text: str) -> str:
    """Drop punctuation that got glued onto p3online.in and breaks the link."""
    if not isinstance(text, str) or "p3online.in" not in text.lower():
        return text
    return _URL_PUNCT.sub(r"\1", text)


def normalize_blog_piece(piece: dict) -> dict:
    if not isinstance(piece, dict):
        return piece
    for key in ("intro", "introduction", "body", "body_html", "conclusion", "meta_description"):
        value = piece.get(key)
        if isinstance(value, str):
            piece[key] = normalize_text(value)
    return piece


def link_issues(text: str) -> list[str]:
    if not text:
        return []
    issues: list[str] = []
    for href in re.findall(r"href\s*=\s*[\"']([^\"']+)", text, re.I):
        if re.search(r"[.,;:)]$", href):
            issues.append(f"href ends with punctuation: {href[:80]}")
        if " " in href:
            issues.append(f"href contains whitespace: {href[:80]}")
    lowered = text.lower()
    if lowered.count("<a") != lowered.count("</a"):
        issues.append("unbalanced anchor tags")
    if re.search(r"https?://[^\s<\"']+[.,;:)](?:</|\s)", text, re.I):
        issues.append("bare URL still has trailing punctuation")
    return issues


def seo_issues(piece: dict) -> list[str]:
    title = str(piece.get("title") or "").strip()
    meta = str(piece.get("meta_description") or "").strip()
    slug = str(piece.get("slug") or "").strip()
    has_copy = any(
        str(piece.get(key) or "").strip()
        for key in ("introduction", "intro", "body", "body_html", "conclusion", "title")
    )
    issues: list[str] = []
    if not has_copy:
        return issues
    if not title:
        issues.append("title is missing")
    elif not 20 <= len(title) <= 80:
        issues.append(f"title length {len(title)} is outside 20-80 characters")
    if not meta:
        issues.append("meta description is missing")
    elif not 110 <= len(meta) <= 170:
        issues.append(f"meta description length {len(meta)} is outside 110-170 characters")
    if not slug:
        issues.append("slug is missing")
    elif not _SLUG.fullmatch(slug):
        issues.append("slug must be 1-8 lowercase hyphenated words")
    return issues


def duplicate_slug_issue(slug: str, on_date: str | None = None, output_dir: str = "output") -> str | None:
    """A slug already used on an earlier day is a duplicate post."""
    slug = str(slug or "").strip().lower()
    if not slug:
        return None
    root = Path(output_dir)
    if not root.is_dir():
        return None
    for path in sorted(root.glob("content_*.json")):
        found = _DATE.search(path.name)
        if not found:
            continue
        stamped = found.group(1)
        if on_date and stamped >= on_date:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        blog = data.get("blog_post") if isinstance(data, dict) else None
        if not isinstance(blog, dict):
            continue
        prior = str(blog.get("slug") or "").strip().lower()
        if prior and prior == slug:
            return f"slug {slug} already used on {stamped}"
    return None


def assess(piece: dict, on_date: str | None = None, output_dir: str = "output") -> list[str]:
    """Actionable blog defects. Empty means the asset can be saved.

    Slugs already used on an earlier IST day are duplicates. The file for
    `on_date` itself is not, so re-checking today's draft is not a duplicate.
    """
    if not isinstance(piece, dict):
        return ["blog asset is not an object"]
    if on_date is None:
        from content_generator.core.ist_dates import today_ist
        on_date = today_ist().isoformat()
    issues = seo_issues(piece)
    blob = "\n".join(
        str(piece.get(key) or "")
        for key in ("title", "intro", "introduction", "body", "body_html", "conclusion", "meta_description")
    )
    issues.extend(link_issues(blob))
    from content_generator.core.product_truth import product_truth_findings
    for finding in product_truth_findings(blob):
        issues.append(f"{finding['reason']}: {finding['claim']}")
    duplicate = duplicate_slug_issue(str(piece.get("slug") or ""), on_date=on_date, output_dir=output_dir)
    if duplicate:
        issues.append(duplicate)
    return issues
