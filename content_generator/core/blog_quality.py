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
    r"(https?://(?:www\.)?p3online\.in(?:/[^\s<\"'.,;:)]*)?)([.,;:)]+)(?=(?:\s|<|$))",
    re.I,
)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+){0,7}")
_DATE = re.compile(r"content_(\d{4}-\d{2}-\d{2})\.json$")
_H2 = re.compile(r"^##\s+(.+)$", re.M)
_H3 = re.compile(r"^###\s+\S", re.M)
_QUESTION = re.compile(r"^(what|how|why|which|when|where|does|do|is|are)\b", re.I)
_CATALOG_LINK = re.compile(r"https?://(?:www\.)?p3online\.in/[^\s)\]\"'<]+", re.I)
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INDIA = re.compile(
    r"mumbai|delhi|bengaluru|bangalore|chennai|hyderabad|kolkata|pune|milk coffee|filter coffee",
    re.I,
)
_RUPEE = re.compile(r"₹|\brs\.?\s*\d+", re.I)
_BANNED_CLAIM = re.compile(
    r"\bsingle[\s-]origin\b|100\s*x\s+purer|\borganic\b|"
    r"lab[\s-]?certified|india'?s\s+(?:first|only)\b",
    re.I,
)

MIN_WORDS = 1000
MAX_WORDS = 1500


def normalize_text(text: str) -> str:
    """Drop punctuation that got glued onto p3online.in and breaks the link.

    A parenthesis that closes a markdown link is kept. Any extra punctuation
    after that closer stays in the sentence.
    """
    if not isinstance(text, str) or "p3online.in" not in text.lower():
        return text

    def _repl(match: re.Match) -> str:
        url, punct = match.group(1), match.group(2)
        prefix = text[max(0, match.start() - 2):match.start()]
        if punct.startswith(")") and prefix == "](":
            return url + ")" + punct[1:]
        return url

    return _URL_PUNCT.sub(_repl, text)


def normalize_blog_piece(piece: dict) -> dict:
    if not isinstance(piece, dict):
        return piece
    for key in ("intro", "introduction", "body", "body_html", "conclusion", "meta_description", "tldr", "llms_summary"):
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
    if re.search(r"(?<!\]\()https?://[^\s<\"')]+[.,;:)]+(?:</|\s)", text, re.I):
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
    elif not 20 <= len(title) <= 60:
        issues.append(f"title length {len(title)} is outside 20-60 characters")
    if not meta:
        issues.append("meta description is missing")
    elif not 150 <= len(meta) <= 160:
        issues.append(f"meta description length {len(meta)} is outside 150-160 characters")
    if not slug:
        issues.append("slug is missing")
    elif not _SLUG.fullmatch(slug):
        issues.append("slug must be 1-8 lowercase hyphenated words")
    return issues


def word_count(text: str) -> int:
    return len(str(text or "").split())


def article_word_count(piece: dict) -> int:
    return sum(
        word_count(piece.get(key))
        for key in ("introduction", "intro", "body", "conclusion")
        if not (key == "intro" and piece.get("introduction"))
    )


def _catalog_links(text: str) -> list[str]:
    from content_generator.core.shopify_catalog import catalog_page_urls
    allowed = {url.rstrip("/") for url in catalog_page_urls()}
    found: list[str] = []
    for raw in _CATALOG_LINK.findall(text or ""):
        url = raw.rstrip(".,;:)").replace("://www.p3online.in", "://p3online.in").rstrip("/")
        if url in allowed and url not in found:
            found.append(url)
    return found


def _json_ld(piece: dict):
    data = piece.get("json_ld")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            return None, ["json_ld is not valid JSON"]
    if not isinstance(data, dict):
        return None, ["json_ld is missing"]
    try:
        json.loads(json.dumps(data))
    except (TypeError, ValueError):
        return None, ["json_ld is not valid JSON"]
    return data, []


def schema_issues(piece: dict) -> list[str]:
    """Article, FAQPage, and BreadcrumbList must be present. Product nodes use catalog data only."""
    data, issues = _json_ld(piece)
    if data is None:
        return issues
    graph = data.get("@graph")
    nodes = graph if isinstance(graph, list) else [data]
    types: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            issues.append("json_ld node is not an object")
            continue
        kind = node.get("@type")
        if isinstance(kind, list):
            types.update(str(item) for item in kind)
        elif kind:
            types.add(str(kind))
        if kind == "Product" or (isinstance(kind, list) and "Product" in kind):
            issues.extend(_product_node_issues(node))
    for required in ("Article", "FAQPage", "BreadcrumbList"):
        if required not in types:
            issues.append(f"json_ld missing {required}")
    if "https://schema.org" not in str(data.get("@context") or ""):
        issues.append("json_ld @context must be schema.org")
    return issues


def _product_node_issues(node: dict) -> list[str]:
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, product_page_url
    url = str(node.get("url") or "").rstrip("/")
    known = {product_page_url(product).rstrip("/"): product for product in SHOPIFY_PRODUCTS.values()}
    product = known.get(url)
    if product is None:
        return [f"Product schema URL is not in the catalog: {url[:80]}"]
    offer = node.get("offers") if isinstance(node.get("offers"), dict) else {}
    try:
        price = int(float(offer.get("price")))
    except (TypeError, ValueError):
        return ["Product schema price is not catalog data"]
    prices = {int(variant["price"]) for variant in product.get("variants") or [] if "price" in variant}
    if price not in prices:
        return [f"Product schema price {price} is not a catalog price"]
    if str(offer.get("priceCurrency") or "") != "INR":
        return ["Product schema currency must be INR"]
    return []


def structure_issues(piece: dict) -> list[str]:
    """SEO and GEO shape: length, FAQ, TL;DR, headings, links, India context."""
    issues: list[str] = []
    words = article_word_count(piece)
    if not MIN_WORDS <= words <= MAX_WORDS:
        issues.append(f"word count {words} is outside {MIN_WORDS}-{MAX_WORDS}")
    tldr_words = word_count(piece.get("tldr"))
    if not 40 <= tldr_words <= 60:
        issues.append(f"tldr length {tldr_words} is outside 40-60 words")
    faq = piece.get("faq")
    if not isinstance(faq, list) or not 4 <= len(faq) <= 6:
        issues.append("faq must contain 4-6 items")
    else:
        for item in faq:
            if not isinstance(item, dict) or not str(item.get("question") or "").strip() or not str(item.get("answer") or "").strip():
                issues.append("faq item missing question or answer")
                break
            if word_count(item.get("answer")) > 80:
                issues.append("faq answers must stay concise")
                break
    primary = str(piece.get("primary_keyword") or piece.get("focus_keyword") or "").strip()
    intro = str(piece.get("introduction") or piece.get("intro") or "")
    body = str(piece.get("body") or "")
    h2s = [match.strip() for match in _H2.findall(body)]
    if not primary:
        issues.append("primary keyword is missing")
    else:
        if primary.lower() not in intro.lower():
            issues.append("primary keyword missing from the introduction")
        if not any(primary.lower() in heading.lower() for heading in h2s):
            issues.append("primary keyword missing from an H2")
    secondaries = piece.get("secondary_keywords")
    if not isinstance(secondaries, list) or not secondaries:
        issues.append("secondary keywords are missing")
    questions = [heading for heading in h2s if heading.rstrip().endswith("?") or _QUESTION.match(heading)]
    if len(questions) < 2:
        issues.append("question-style H2s are missing")
    if not _H3.search(body):
        issues.append("H3 subheading is missing")
    if body.count("| ---") < 1 and "|---" not in body:
        issues.append("comparison table is missing")
    blob = "\n".join([intro, body, str(piece.get("conclusion") or "")])
    links = _catalog_links(blob)
    if not 2 <= len(links) <= 4:
        issues.append(f"internal catalog links {len(links)} is outside 2-4")
    alt = str(piece.get("image_alt") or "").strip()
    if not alt:
        issues.append("image alt text is missing")
    elif len(alt) > 125:
        issues.append("image alt text is over 125 characters")
    if str(piece.get("author") or "").strip() != "Purity Beans":
        issues.append("author must be Purity Beans")
    if not _ISO_DATE.fullmatch(str(piece.get("last_updated") or "").strip()):
        issues.append("last_updated must be an IST YYYY-MM-DD date")
    if not _RUPEE.search(blob) or not _INDIA.search(blob):
        issues.append("India context is missing (₹ prices and a city or brew habit)")
    summary = str(piece.get("llms_summary") or "").strip()
    if word_count(summary) < 40:
        issues.append("llms summary is missing")
    if str(piece.get("hold_reason") or "").strip():
        issues.append(f"held: {piece['hold_reason']}")
    if _BANNED_CLAIM.search(blob):
        issues.append("banned claim: unverified superlative or certificate")
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
    if any(str(piece.get(key) or "").strip() for key in ("introduction", "intro", "body", "body_html", "title")):
        issues.extend(structure_issues(piece))
        issues.extend(schema_issues(piece))
    faq_text = []
    for item in piece.get("faq") or []:
        if isinstance(item, dict):
            faq_text.append(str(item.get("question") or ""))
            faq_text.append(str(item.get("answer") or ""))
    blob = "\n".join(
        [str(piece.get(key) or "") for key in (
            "title", "intro", "introduction", "body", "conclusion",
            "meta_description", "tldr", "llms_summary",
        )] + faq_text
    )
    issues.extend(link_issues(blob))
    from content_generator.core.product_truth import product_truth_findings
    for finding in product_truth_findings(blob):
        issues.append(f"{finding['reason']}: {finding['claim']}")
    duplicate = duplicate_slug_issue(str(piece.get("slug") or ""), on_date=on_date, output_dir=output_dir)
    if duplicate:
        issues.append(duplicate)
    return issues
