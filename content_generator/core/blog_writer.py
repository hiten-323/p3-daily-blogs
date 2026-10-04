"""Sectioned long-form blog generation.

Outline first, then expand each section. A short section is retried and, if
the model stays short, filled from catalog facts. A provider failure does not
delete the draft: the piece is kept and marked held.
"""
from __future__ import annotations

import logging

from content_generator.core.blog_plan import (
    choose_topic,
    comparison_table,
    conclusion_for,
    faqs_for,
    fit_meta,
    h3_prose,
    headings_for,
    image_alt_for,
    introduction_for,
    link_targets,
    links_paragraph,
    llms_summary_for,
    section_prose,
    tldr_for,
)
from content_generator.core.blog_quality import MIN_WORDS, MAX_WORDS, assess, word_count
from content_generator.core.blog_render import build_json_ld, render_html_fragment, write_blog_files
from content_generator.core.shopify_catalog import format_catalog_for_prompt

logger = logging.getLogger(__name__)

SECTION_MIN_WORDS = 120
_SECTION_ATTEMPTS = 3


def _copy_ok(text: str) -> bool:
    if not str(text or "").strip():
        return False
    from content_generator.core.product_truth import product_truth_findings
    if product_truth_findings(text):
        return False
    from content_generator.scheduler.daily import _strip_unsupported_stats
    scrubbed = _strip_unsupported_stats(text)
    return word_count(scrubbed) >= max(1, word_count(text) - 2)


def expand_section(spec: dict, llm_call, prompt: str, *, min_words: int = SECTION_MIN_WORDS,
                   attempts: int = _SECTION_ATTEMPTS) -> tuple[str, int, Exception | None]:
    """Write one section. Short drafts are expanded. Provider errors are returned, not swallowed."""
    best = ""
    calls = 0
    failure: Exception | None = None
    for attempt in range(max(1, attempts)):
        extra = ""
        if attempt:
            extra = (
                "\n\nThe previous section was under the word minimum. "
                "Expand it with catalog facts only. Do not invent prices, percentages, certificates, "
                "or a chicory figure other than 30% for Ultra Blend. "
                'Return JSON {"body": "..."}.'
            )
        try:
            data = llm_call(prompt + extra, label=f"blog_section_{spec.get('id') or attempt}", max_tokens=900)
        except Exception as exc:
            failure = exc
            logger.error(
                "[blog] provider failed during section %s attempt %d: %s",
                spec.get("id"), attempt + 1, exc,
            )
            break
        calls += 1
        chunk = ""
        if isinstance(data, dict):
            chunk = str(data.get("body") or data.get("text") or "")
        if not _copy_ok(chunk):
            logger.warning("[blog] section %s rejected by product truth; expanding", spec.get("id"))
            continue
        if word_count(chunk) > word_count(best):
            best = chunk.strip()
        if word_count(best) >= min_words:
            return best, calls, None
        logger.warning(
            "[blog] section %s is %d words (need %d); expanding instead of failing the post",
            spec.get("id"), word_count(best), min_words,
        )
    return best, calls, failure


def _section_prompt(topic: dict, spec: dict, catalog: str) -> str:
    return (
        f"{catalog}\n\n"
        "Write one blog section for Purity Beans. Return JSON only: {\"body\": \"plain prose\"}.\n"
        f"TOPIC: {topic['title']}\n"
        f"PRIMARY KEYWORD: {topic['primary']}\n"
        f"H2: {spec['heading']}\n"
        f"Write {SECTION_MIN_WORDS} to 170 words. Mention Purity Beans. "
        "Ultra Blend is 70% coffee and 30% chicory. Never call Ultra Blend zero chicory or no chicory. "
        "Prima / Premium Agglomerate is 100% Arabica and is not freeze-dried. "
        "Use only catalog prices. No India's first, India's only, 100x purer, organic, lab certified, or single-origin."
    )


def _article_words(intro: str, sections: list[dict], conclusion: str, table: str, links: str) -> int:
    total = word_count(intro) + word_count(conclusion) + word_count(table) + word_count(links)
    for section in sections:
        total += word_count(section.get("body"))
        total += word_count((section.get("h3_body") or ""))
    return total


def _render_body(sections: list[dict], table: str, links: str) -> str:
    chunks = []
    for section in sections:
        chunks.append(f"## {section['heading']}\n\n{section['body'].strip()}")
        if section.get("h3") and section.get("h3_body"):
            chunks.append(f"### {section['h3']}\n\n{section['h3_body'].strip()}")
    chunks.append(table)
    chunks.append(links)
    return "\n\n".join(chunks).strip()


def _fit_length(intro: str, sections: list[dict], conclusion: str, table: str, links: str,
                topic: dict) -> None:
    guard = 0
    while _article_words(intro, sections, conclusion, table, links) < MIN_WORDS and guard < 12:
        shortest = min(sections, key=lambda item: word_count(item.get("body")))
        shortest["body"] = (shortest["body"].rstrip() + "\n\n" + section_prose(topic, guard + 3)).strip()
        guard += 1
    guard = 0
    while _article_words(intro, sections, conclusion, table, links) > MAX_WORDS and guard < 60:
        longest = max(sections, key=lambda item: word_count(item.get("body")))
        words = longest["body"].split()
        overflow = _article_words(intro, sections, conclusion, table, links) - MAX_WORDS
        if len(words) <= 70:
            if word_count(longest.get("h3_body")) > 12:
                longest["h3_body"] = ""
                guard += 1
                continue
            break
        cut = max(15, min(len(words) - 70, overflow))
        longest["body"] = " ".join(words[:-cut]).rstrip(",;:") + "."
        guard += 1


def _default_llm(prompt: str, label: str = "", max_tokens: int = 900) -> dict:
    from content_generator.providers.llm_router import call as llm_call
    return llm_call(prompt, label=label, max_tokens=max_tokens)


def generate_blog_post(
    day_number: int,
    *,
    llm_call=None,
    output_dir: str = "output",
    on_date: str | None = None,
    context_suffix: str = "",
    write_files: bool = False,
) -> dict:
    """Build one post. Provider failures keep the draft and set hold_reason."""
    from content_generator.core.ist_dates import today_ist

    llm = llm_call or _default_llm
    on_date = on_date or today_ist().isoformat()
    topic = choose_topic(int(day_number), output_dir=output_dir, on_date=on_date)
    catalog = format_catalog_for_prompt()
    notes: list[str] = []
    hold_reason = ""

    outline_prompt = (
        f"Return JSON {{\"sections\": [{{\"id\": \"s0\", \"heading\": \"question?\"}}]}} "
        f"with 6 question headings for: {topic['title']}. Primary keyword: {topic['primary']}."
        f"\n{context_suffix or ''}"
    )
    try:
        llm(outline_prompt, label="blog_outline", max_tokens=700)
    except Exception as exc:
        notes.append(f"outline provider failed: {exc}")
        logger.warning("[blog] outline provider failed (%s); using the topic plan", exc)

    sections = []
    for index, spec in enumerate(headings_for(topic)):
        prompt = _section_prompt(topic, spec, catalog)
        if context_suffix:
            prompt += "\n\n" + context_suffix
        prose, _calls, failure = expand_section(spec, llm, prompt)
        if failure is not None and not hold_reason:
            hold_reason = f"provider_failure during {spec['id']}: {failure}"
            logger.error("[blog] HELD blog_post: %s", hold_reason)
        elif failure is not None:
            logger.warning("[blog] later section %s also lost its provider: %s", spec["id"], failure)
        if word_count(prose) < SECTION_MIN_WORDS or not _copy_ok(prose):
            logger.warning(
                "[blog] section %s still short after retries (%d words); using catalog expansion",
                spec["id"], word_count(prose),
            )
            prose = section_prose(topic, index)
        sections.append({
            "id": spec["id"],
            "heading": spec["heading"],
            "body": prose,
            "h3": spec["h3"],
            "h3_body": h3_prose(topic),
        })

    intro = introduction_for(topic)
    conclusion = conclusion_for(topic)
    table = comparison_table()
    links = links_paragraph()
    _fit_length(intro, sections, conclusion, table, links, topic)
    body = _render_body(sections, table, links)
    # Headings add words the section counter does not see. Trim until the
    # rendered article, the same text the gate counts, is inside the window.
    guard = 0
    while word_count(intro) + word_count(body) + word_count(conclusion) > MAX_WORDS and guard < 80:
        longest = max(sections, key=lambda item: word_count(item.get("body")))
        words = longest["body"].split()
        overflow = word_count(intro) + word_count(body) + word_count(conclusion) - MAX_WORDS
        if len(words) <= 40:
            break
        longest["body"] = " ".join(words[: max(40, len(words) - overflow)]).rstrip(",;:") + "."
        body = _render_body(sections, table, links)
        guard += 1
    guard = 0
    while word_count(intro) + word_count(body) + word_count(conclusion) < MIN_WORDS and guard < 8:
        sections[guard % len(sections)]["body"] += "\n\n" + section_prose(topic, guard + 1)
        body = _render_body(sections, table, links)
        guard += 1
    tldr = tldr_for(topic)
    piece = {
        "title": topic["title"],
        "slug": topic["slug"],
        "meta_description": fit_meta(topic["meta_lead"]),
        "primary_keyword": topic["primary"],
        "focus_keyword": topic["primary"],
        "secondary_keywords": list(topic["secondary"]),
        "topic_id": topic["id"],
        "tldr": tldr,
        "introduction": intro,
        "body": body,
        "conclusion": conclusion,
        "faq": faqs_for(topic),
        "image_alt": image_alt_for(topic),
        "author": "Purity Beans",
        "last_updated": on_date,
        "tags": ["instant coffee", "purity beans", "india", topic["primary"]],
        "internal_links": [item["url"] for item in link_targets()],
        "llms_summary": llms_summary_for(topic, tldr),
        "sections": [
            {"heading": section["heading"], "level": "h2", "body": section["body"]}
            for section in sections
        ],
        "generation_notes": notes,
    }
    piece["json_ld"] = build_json_ld(piece)
    piece["body_html"] = render_html_fragment(piece)
    from content_generator.core.blog_quality import normalize_blog_piece
    normalize_blog_piece(piece)
    if hold_reason:
        piece["hold_reason"] = hold_reason
        piece["held"] = True
        logger.error("[blog] HELD blog_post — draft kept, not dropped: %s", hold_reason)
    else:
        issues = assess(piece, on_date=on_date, output_dir=output_dir)
        if issues:
            piece["hold_reason"] = "blog gates failed: " + "; ".join(issues[:6])
            piece["held"] = True
            logger.error("[blog] HELD blog_post — draft kept, gates failed: %s", piece["hold_reason"])
    if write_files and piece.get("title") and piece.get("body"):
        write_blog_files(piece, output_dir, on_date)
    return piece
