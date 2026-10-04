"""Markdown, HTML, JSON-LD, and llms.txt for one blog post."""
from __future__ import annotations

import html
import json
import os
import re

from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, product_page_url

_MD_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_H3 = re.compile(r"^###\s+(.+)$", re.M)
_H2 = re.compile(r"^##\s+(.+)$", re.M)


def _product_nodes() -> list[dict]:
    nodes = []
    for product in SHOPIFY_PRODUCTS.values():
        url = product_page_url(product)
        if not url:
            continue
        variant = (product.get("variants") or [{}])[0]
        price = variant.get("price")
        if price in (None, ""):
            continue
        availability = "https://schema.org/InStock" if product.get("in_stock") else "https://schema.org/OutOfStock"
        nodes.append({
            "@type": "Product",
            "name": product.get("short_name") or product.get("title"),
            "url": url,
            "sku": variant.get("sku") or "",
            "brand": {"@type": "Brand", "name": "Purity Beans"},
            "offers": {
                "@type": "Offer",
                "priceCurrency": "INR",
                "price": str(price),
                "availability": availability,
                "url": url,
            },
        })
    return nodes


def build_json_ld(piece: dict) -> dict:
    title = str(piece.get("title") or "").strip()
    slug = str(piece.get("slug") or "").strip()
    meta = str(piece.get("meta_description") or "").strip()
    updated = str(piece.get("last_updated") or "").strip()
    page = f"https://p3online.in/blogs/news/{slug}" if slug else "https://p3online.in/blogs/news"
    faq_nodes = []
    for item in piece.get("faq") or []:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if question and answer:
            faq_nodes.append({
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer},
            })
    graph = [
        {
            "@type": "Article",
            "headline": title,
            "description": meta,
            "inLanguage": "en-IN",
            "dateModified": updated,
            "datePublished": updated,
            "author": {"@type": "Organization", "name": "Purity Beans", "url": "https://p3online.in"},
            "publisher": {"@type": "Organization", "name": "Purity Beans", "url": "https://p3online.in"},
            "mainEntityOfPage": page,
        },
        {"@type": "FAQPage", "mainEntity": faq_nodes},
        {
            "@type": "BreadcrumbList",
            "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": "https://p3online.in"},
                {"@type": "ListItem", "position": 2, "name": "Blog", "item": "https://p3online.in/blogs/news"},
                {"@type": "ListItem", "position": 3, "name": title or "Article", "item": page},
            ],
        },
        *_product_nodes(),
    ]
    return {"@context": "https://schema.org", "@graph": graph}


def render_markdown(piece: dict) -> str:
    title = str(piece.get("title") or "").strip()
    updated = str(piece.get("last_updated") or "").strip()
    lines = [
        f"# {title}",
        "",
        f"**TL;DR.** {str(piece.get('tldr') or '').strip()}",
        "",
        f"*By Purity Beans. Last updated {updated} (IST).*",
        "",
        str(piece.get("introduction") or "").strip(),
        "",
        str(piece.get("body") or "").strip(),
        "",
        "## Frequently asked questions",
        "",
    ]
    for item in piece.get("faq") or []:
        if not isinstance(item, dict):
            continue
        lines.append(f"### {item.get('question', '').strip()}")
        lines.append("")
        lines.append(str(item.get("answer") or "").strip())
        lines.append("")
    lines.append(str(piece.get("conclusion") or "").strip())
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _inline(text: str) -> str:
    escaped = html.escape(text)
    def _link(match: re.Match) -> str:
        label = html.escape(match.group(1))
        url = html.escape(match.group(2), quote=True)
        return f'<a href="{url}">{label}</a>'
    return _MD_LINK.sub(_link, escaped)


def _table_html(block: str) -> str:
    rows = [line.strip() for line in block.splitlines() if line.strip().startswith("|")]
    if len(rows) < 2:
        return ""
    parsed = []
    for row in rows:
        if re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", row):
            continue
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        parsed.append(cells)
    if not parsed:
        return ""
    head, body = parsed[0], parsed[1:]
    thead = "".join(f"<th>{_inline(cell)}</th>" for cell in head)
    body_html = []
    for row in body:
        body_html.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
    return "<table><thead><tr>" + thead + "</tr></thead><tbody>" + "".join(body_html) + "</tbody></table>"


def render_html_fragment(piece: dict) -> str:
    """Article HTML plus JSON-LD, suitable for a Shopify article body."""
    chunks = [
        f"<p><strong>TL;DR.</strong> {html.escape(str(piece.get('tldr') or '').strip())}</p>",
        (
            "<p><em>By Purity Beans. Last updated "
            f"{html.escape(str(piece.get('last_updated') or ''))} (IST).</em></p>"
        ),
        f"<p>{_inline(str(piece.get('introduction') or '').strip())}</p>",
    ]
    body = str(piece.get("body") or "")
    blocks = re.split(r"\n\s*\n", body)
    for block in blocks:
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("|"):
            table = _table_html(stripped)
            if table:
                chunks.append(table)
            continue
        heading = _H3.match(stripped) or _H2.match(stripped)
        if heading and "\n" not in stripped:
            tag = "h3" if stripped.startswith("###") else "h2"
            chunks.append(f"<{tag}>{html.escape(heading.group(1).strip())}</{tag}>")
            continue
        if stripped.startswith("## ") or stripped.startswith("### "):
            first, _, rest = stripped.partition("\n")
            tag = "h3" if first.startswith("###") else "h2"
            chunks.append(f"<{tag}>{html.escape(first.lstrip('#').strip())}</{tag}>")
            if rest.strip():
                chunks.append(f"<p>{_inline(rest.strip())}</p>")
            continue
        chunks.append(f"<p>{_inline(stripped)}</p>")
    chunks.append("<h2>Frequently asked questions</h2>")
    for item in piece.get("faq") or []:
        if not isinstance(item, dict):
            continue
        chunks.append(f"<h3>{html.escape(str(item.get('question') or '').strip())}</h3>")
        chunks.append(f"<p>{html.escape(str(item.get('answer') or '').strip())}</p>")
    chunks.append(f"<p>{_inline(str(piece.get('conclusion') or '').strip())}</p>")
    payload = json.dumps(piece.get("json_ld") or {}, ensure_ascii=False).replace("</", "<\\/")
    chunks.append(f'<script type="application/ld+json">{payload}</script>')
    return "\n".join(chunks)


def render_html_document(piece: dict) -> str:
    title = html.escape(str(piece.get("title") or ""))
    meta = html.escape(str(piece.get("meta_description") or ""), quote=True)
    slug = str(piece.get("slug") or "").strip()
    canonical = f"https://p3online.in/blogs/news/{slug}" if slug else "https://p3online.in/blogs/news"
    return (
        "<!DOCTYPE html>\n<html lang=\"en-IN\">\n<head>\n"
        "<meta charset=\"utf-8\">\n"
        f"<title>{title}</title>\n"
        f"<meta name=\"description\" content=\"{meta}\">\n"
        f"<link rel=\"canonical\" href=\"{html.escape(canonical, quote=True)}\">\n"
        "</head>\n<body>\n<article>\n"
        f"<h1>{title}</h1>\n"
        f"{render_html_fragment(piece)}\n"
        "</article>\n</body>\n</html>\n"
    )


def render_llms_txt(piece: dict) -> str:
    lines = [
        f"# {str(piece.get('title') or '').strip()}",
        f"> {str(piece.get('tldr') or '').strip()}",
        "",
        str(piece.get("llms_summary") or "").strip(),
        "",
        f"Author: {piece.get('author') or 'Purity Beans'}",
        f"Updated: {piece.get('last_updated') or ''} IST",
        f"Canonical: https://p3online.in/blogs/news/{piece.get('slug') or ''}",
    ]
    return "\n".join(lines).strip() + "\n"


def write_blog_files(piece: dict, output_dir: str, date_str: str) -> dict[str, str]:
    os.makedirs(output_dir, exist_ok=True)
    paths = {
        "json": os.path.join(output_dir, f"blog_{date_str}.json"),
        "markdown": os.path.join(output_dir, f"blog_{date_str}.md"),
        "html": os.path.join(output_dir, f"blog_{date_str}.html"),
        "llms": os.path.join(output_dir, f"blog_{date_str}.llms.txt"),
    }
    payload = dict(piece)
    payload["markdown_path"] = paths["markdown"]
    payload["html_path"] = paths["html"]
    payload["llms_path"] = paths["llms"]
    with open(paths["json"], "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    with open(paths["markdown"], "w", encoding="utf-8") as handle:
        handle.write(render_markdown(piece))
    with open(paths["html"], "w", encoding="utf-8") as handle:
        handle.write(render_html_document(piece))
    with open(paths["llms"], "w", encoding="utf-8") as handle:
        handle.write(render_llms_txt(piece))
    return paths
