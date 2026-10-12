"""Product facts the content gates are allowed to state.

Owner guardrails for Purity Beans copy:
- Prima / Premium Agglomerate is 100% Arabica and agglomerated, not freeze-dried.
- Ultra Blend is 70% coffee and 30% chicory. A lower-caffeine description is allowed for that jar.
- Never call Ultra Blend no-chicory, zero-chicory, or 0% chicory.
- When Ultra Blend or any other chicory blend is featured or named as the solution,
  do not attack chicory or roasted root (filler, muddy, poison, "never drink roasted root",
  "hidden chicory fillers", "chicory fillers").
  Honest 70/30 disclosure, smooth milk coffee, and lower caffeine are allowed.
- Gourmet Duo and Gourmet Duo Mini are 100% coffee and zero chicory. Do not apply Ultra Blend's chicory rules to either duo, and do not call either duo only Arabica or only Robusta.
- Bold and Purista are 100% Robusta. Purica is freeze-dried 100% Arabica.
- Do not invent other product claims, and do not apply a pure-jar claim to Ultra Blend.
"""
from __future__ import annotations

import re

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE = re.compile(r"\b(?:while|whereas|but|unlike|except)\b|;", re.I)
_NEGATION = re.compile(
    r"\b(?:not|never|isn't|aren't|is not|are not|do not|don't|dont)\b",
    re.I,
)
_ULTRA = re.compile(r"ultra[\s-]?blend", re.I)
_PRIMA = re.compile(r"\b(?:prima|premium agglomerate)\b", re.I)
_ARABICA_JARS = re.compile(r"\b(?:purica|prima|premium agglomerate)\b", re.I)
_ROBUSTA_JARS = re.compile(r"\b(?:bold|purista)\b", re.I)
_OTHER_THAN_ULTRA = re.compile(
    r"\b(?:bold|purista|purica|prima|premium agglomerate|gourmet duo(?: mini)?)\b",
    re.I,
)
_DUO_SINGLE_BEAN = re.compile(
    r"\bgourmet\s+duo(?:\s+mini)?\s+is\s+(?:a\s+)?100\s*(?:%|percent)\s*(?:pure\s+)?(arabica|robusta)\b",
    re.I,
)
_PURE_CLAIM = re.compile(
    r"100\s*%\s*(?:pure\s+)?coffee|100\s*percent\s+(?:pure\s+)?coffee|"
    r"zero[\s-]+chicory|(?<!\d)0\s*%\s*chicory|\bno[\s-]+chicory\b|\bwithout chicory\b|"
    r"\bchicory[-\s]?free\b|"
    r"\b(?:does not|doesn't|doesnt)\s+contain\s+chicory\b|"
    r"\bcontains?\s+no\s+chicory\b",
    re.I,
)
_SEGMENT = re.compile(r"[,:;]|\s[-–—]\s")
_HTML_BLOCK_END = re.compile(r"</(?:tr|p|li|h[1-6]|div|blockquote)\s*>|<br\s*/?>", re.I)
_HTML_TAG = re.compile(r"<[^>]+>")
_LOW_CAFFEINE = re.compile(r"\b(?:low(?:er)?|less)[\s-]+caffeine\b", re.I)
_FREEZE = re.compile(r"freeze[\s-]?dried", re.I)
_BRAND_IS_FREEZE_ARABICA = re.compile(
    r"purity beans is freeze[\s-]?dried arabica",
    re.I,
)
_INVENTED = re.compile(
    r"100\s*x\s+purer|lab-tested purity certificate|lab[\s-]?certified|"
    r"single-origin style|"
    r"70\s*[-–]\s*80\s*%\s*chicory|hand-selected chicory|"
    r"\bsmall[\s-]batch(?:es)?\b|"
    r"\borganic\b|india'?s\s+(?:first|only)\b",
    re.I,
)
_PERCENT = re.compile(
    r"\b(\d+)\s*(?:%|percent)\s*(coffee|arabica|robusta|chicory)\b",
    re.I,
)
_ROBUSTA_100 = re.compile(r"\b100\s*(?:%|percent)\s*(?:pure\s+)?robusta\b", re.I)
_ARABICA_100 = re.compile(r"\b100\s*(?:%|percent)\s*(?:pure\s+)?arabica\b", re.I)
# Filler / concealment attacks. Honest ratio copy ("30% chicory") does not match:
# the filler form requires the word filler, and the hidden form requires "hidden chicory".
_HIDDEN_CHICORY = r"\bhidden[\s-]+chicory(?:[\s-]+roots?)?(?:[\s-]+fillers?)?\b"
_CHICORY_FILLER = r"\b(?:roasted[\s-]+)?chicory(?:[\s-]+root)?[\s-]+fillers?\b"
_CHICORY_BULK = r"\bbulk(?:ed|ing)?\s+up\s+with\s+(?:roasted[\s-]+)?chicory(?:[\s-]+roots?)?\b"
_HONEST_BLEND = "70% coffee and 30% chicory"
# Attacks on chicory itself. Honest ratio copy ("30% chicory", "smooth milk coffee")
# does not match. These fail only when a chicory blend is in scope.
_ANTI_CHICORY = re.compile(
    r"roasted[\s-]+root[\s-]+filler"
    r"|never\s+drink\s+roasted\s+root"
    r"|(?:do not|don't|dont)\s+drink\s+roasted\s+root"
    r"|stop\s+drinking\s+roasted\s+root"
    r"|\bit\s+is\s+roasted\s+root\b"
    r"|\broot\s+filler\b"
    r"|paying\s+.{0,48}?roasted\s+chicory"
    r"|cafe\s+prices\s+for\s+roasted\s+chicory"
    r"|chicory\s+is\s+(?:bad|muddy|a\s+filler|filler|poison)"
    r"|muddy\s+taste\b.{0,80}?roasted\s+root"
    r"|\b(?:chicory|roasted\s+root)\b.{0,32}?\b(?:poison|adulterant)\b"
    r"|\b(?:poison|adulterant)\b.{0,32}?\b(?:chicory|roasted\s+root)\b"
    rf"|{_HIDDEN_CHICORY}"
    rf"|{_CHICORY_FILLER}"
    rf"|{_CHICORY_BULK}",
    re.I,
)
_FALSE_PURITY_TOKEN = (
    r"zero[\s-]+chicory|(?<!\d)0\s*%\s*chicory|\bno[\s-]+chicory\b|"
    r"\bchicory[-\s]?free\b|100\s*%\s*(?:pure\s+)?coffee|100\s*percent\s+(?:pure\s+)?coffee"
)
_ULTRA_FALSE_PURITY = re.compile(
    rf"ultra[\s-]?blend[^,.!?\n]{{0,140}}?(?:{_FALSE_PURITY_TOKEN})",
    re.I,
)
HONEST_FOLLOW_CTA = "Follow @puritybeans for Ultra Blend: 70% coffee and 30% chicory."
PURE_JAR_FOLLOW_CTA = "Follow @puritybeans so you never drink roasted root again"
_ANTI_CHICORY_REASON = (
    "anti-chicory attack is not allowed when Ultra Blend or another chicory blend "
    "is featured or named as the solution; disclose 70% coffee and 30% chicory"
)
_SLUG_TOKENS = (
    ("gourmet_duo_mini", ("gourmet duo mini", "gourmet_duo_mini", "gourmet-duo-mini")),
    ("gourmet_duo", ("gourmet duo", "gourmet_duo", "gourmet-duo")),
    ("ultra_blend", ("ultra blend", "ultra_blend", "ultrablend", "ultra-blend")),
    ("variety_box", ("variety box", "variety_box", "variety-box")),
    ("prima", ("premium agglomerate", "prima")),
    ("purista", ("purista",)),
    ("purica", ("purica",)),
    ("bold", ("bold",)),
)
_COPY_KEYS = (
    "hook", "hook_text", "hook_spoken", "headline", "title", "caption", "body",
    "body_html", "intro", "introduction", "conclusion", "meta_description",
    "cta", "primary_cta", "on_screen", "spoken", "text", "content",
    "description", "tagline", "product", "product_slug", "subtext",
    "comment_trigger", "save_trigger", "share_trigger", "hashtags",
)
_REPAIR_SUBS = (
    (re.compile(r"You might be drinking hidden chicory fillers\.?", re.I),
     f"Ultra Blend is {_HONEST_BLEND}."),
    (re.compile(
        r"While legacy brands bulk up commercial jars with hidden chicory fillers to cut costs, smart",
        re.I,
    ), f"Ultra Blend is {_HONEST_BLEND}, printed on the jar. Smart"),
    (re.compile(
        r"yet most commercial jars rely on heavy processing and hidden chicory roots to stretch profits",
        re.I,
    ), f"and Ultra Blend is {_HONEST_BLEND}, printed on the label"),
    (re.compile(
        r"many home drinkers unknowingly compromise because commercial jars are bulked up with roasted chicory root, muting the natural aroma and leaving a muddy aftertaste\.?",
        re.I,
    ), f"the label states the ratio. Ultra Blend is {_HONEST_BLEND}, a smooth milk coffee."),
    (re.compile(r"Some brands bulk up with chicory root\.?", re.I),
     f"Ultra Blend is {_HONEST_BLEND}."),
    (re.compile(_HIDDEN_CHICORY, re.I),
     f"a labeled {_HONEST_BLEND} blend"),
    (re.compile(_CHICORY_FILLER, re.I),
     f"a labeled {_HONEST_BLEND} blend"),
    (re.compile(_CHICORY_BULK, re.I),
     f"state {_HONEST_BLEND}"),
    # Prior repair inverted denials ("do not call it zero chicory" -> "do not call it 30%").
    (re.compile(r"never called 30%\s*chicory or no[\s-]+chicory", re.I),
     _HONEST_BLEND),
    (re.compile(r"Do not call Ultra Blend 30%\s*chicory", re.I),
     f"Call Ultra Blend {_HONEST_BLEND}"),
    (re.compile(r"without any false 30%\s*chicory claims", re.I),
     f"with an honest {_HONEST_BLEND} disclosure"),
    (re.compile(r"Follow @puritybeans so you never drink roasted root again\.?", re.I),
     HONEST_FOLLOW_CTA),
    (re.compile(r"so you never drink roasted root again", re.I),
     "for the honest 70% coffee, 30% chicory cup"),
    (re.compile(r"never drink roasted root", re.I),
     "read the 70% coffee, 30% chicory label"),
    (re.compile(
        r"That muddy taste[^.!?\n]{0,160}?roasted root filler\.?",
        re.I,
    ), "Ultra Blend is 70% coffee and 30% chicory, a smooth milk coffee."),
    (re.compile(r"\bit is roasted root filler\.?", re.I),
     "Ultra Blend is 70% coffee and 30% chicory."),
    (re.compile(r"roasted[\s-]+root[\s-]+filler", re.I),
     "the blend printed on the label"),
    (re.compile(r"You are paying cafe prices for roasted chicory root\.?", re.I),
     "You are paying cafe prices. Ultra Blend is 70% coffee and 30% chicory."),
    (re.compile(r"paying\s+.{0,48}?roasted\s+chicory(?:\s+root)?", re.I),
     "paying cafe prices for a home cup"),
    (re.compile(r"chicory is (?:bad|muddy|a filler|filler|poison)", re.I),
     "chicory is 30% of Ultra Blend and is printed on the label"),
)


def _claim_text(text: str) -> str:
    """Split HTML blocks so a comparison table is not one mixed claim."""
    if "<" not in text or ">" not in text:
        return text
    plain = _HTML_BLOCK_END.sub("\n", text)
    return _HTML_TAG.sub(" ", plain)


def _locally_negated(text: str, start: int) -> bool:
    """True when a negation governs this match, not an earlier clause.

    "is not 100% coffee" is negated. "is not a compromise and it is 100%
    coffee" is a new claim after "and", so the earlier "not" does not cover it.
    """
    prefix = text[max(0, start - 80):start]
    tail = _SEGMENT.split(prefix)[-1]
    tail = re.split(r"\b(?:and|but)\b", tail, flags=re.I)[-1]
    return bool(_NEGATION.search(tail))


def _segments(clause: str) -> list[str]:
    parts = [part.strip() for part in _SEGMENT.split(clause) if part and part.strip()]
    return parts or [clause]


def _finding(sentence: str, reason: str) -> dict:
    return {
        "claim": sentence.strip()[:140],
        "type": "product_truth",
        "reason": reason,
    }


def named_slugs(text: str) -> list[str]:
    """Catalog slugs named in `text`, longest token first."""
    raw = str(text or "").lower()
    found: list[str] = []
    for slug, tokens in _SLUG_TOKENS:
        for token in tokens:
            if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", raw):
                found.append(slug)
                break
    return found


def _catalog_has_chicory(product: dict) -> bool:
    if not product:
        return False
    percent = product.get("chicory_percent")
    if isinstance(percent, (int, float)) and percent > 0:
        return True
    label = str(product.get("chicory") or "")
    return bool(re.search(r"30\s*(?:%|percent)\s*chicory", label, re.I))


def name_contains_chicory(name: str) -> bool:
    """True when `name` is Ultra Blend, the Variety Box, or another chicory SKU."""
    if not str(name or "").strip():
        return False
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, get_product

    slugs = named_slugs(name)
    if not slugs:
        key = str(name).strip().lower().replace("-", "_").replace(" ", "_")
        product = get_product(key)
        if product:
            slugs = [str(product.get("slug") or key)]
    return any(_catalog_has_chicory(SHOPIFY_PRODUCTS.get(slug) or {}) for slug in slugs)


def featured_product_name(content: dict | None) -> str:
    """Day's featured jar. Explicit field wins; otherwise the day rotation."""
    if not isinstance(content, dict):
        return ""
    explicit = str(content.get("featured_product") or "").strip()
    if explicit:
        return explicit
    day = content.get("day_number")
    if day in (None, ""):
        return ""
    try:
        day_number = int(day)
    except (TypeError, ValueError):
        return ""
    from content_generator.rotation import PRODUCTS, pick
    return str(pick(PRODUCTS, day_number))


def chicory_in_scope(text: str, featured: str | None = None) -> bool:
    """Featured chicory SKU, or a chicory SKU named in this copy as the solution."""
    if name_contains_chicory(str(featured or "")):
        return True
    return any(name_contains_chicory(slug) for slug in named_slugs(text))


def follow_cta_for(featured: str | None = None, text: str = "") -> str:
    """Follower CTA. Chicory blends get the honest 70/30 line."""
    if chicory_in_scope(text, featured):
        return HONEST_FOLLOW_CTA
    return PURE_JAR_FOLLOW_CTA


def piece_copy_text(piece: dict) -> str:
    """Every spoken, on-screen, and CTA field the gates are allowed to read."""
    if not isinstance(piece, dict):
        return ""
    parts: list[str] = []

    def add(value) -> None:
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    for key in _COPY_KEYS:
        add(piece.get(key))
    for list_key in ("slides", "frames", "script", "scenes", "hook_options"):
        for item in piece.get(list_key) or []:
            if isinstance(item, str):
                add(item)
            elif isinstance(item, dict):
                for key in _COPY_KEYS:
                    add(item.get(key))
    return "\n".join(parts)


def asset_product_truth_findings(piece: dict, featured: str | None = None) -> list[dict]:
    """Product-truth findings for one asset, including fields outside the caption."""
    if not isinstance(piece, dict):
        return []
    scope = str(featured or piece.get("featured_product") or piece.get("product") or "")
    return product_truth_findings(piece_copy_text(piece), featured=scope)


def repair_text(text: str, *, chicory_scope: bool) -> str:
    """Replace anti-chicory attacks with honest 70/30 wording. No other edits."""
    if not chicory_scope or not isinstance(text, str) or not text:
        return text
    updated = text
    for pattern, replacement in _REPAIR_SUBS:
        updated = pattern.sub(replacement, updated)

    def _strip_false_purity(match: re.Match) -> str:
        span = match.group(0)
        if _OTHER_THAN_ULTRA.search(span):
            return span
        purity = re.search(_FALSE_PURITY_TOKEN, span, flags=re.I)
        # "Do not call Ultra Blend zero chicory" is a denial, not a false claim.
        if purity and (
            _locally_negated(match.string, match.start() + purity.start())
            or re.search(r"\bfalse\b", span[:purity.start()], re.I)
        ):
            return span
        span = re.sub(
            r"zero[\s-]+chicory|(?<!\d)0\s*%\s*chicory|\bno[\s-]+chicory\b|"
            r"\bchicory[-\s]?free\b",
            "30% chicory",
            span,
            flags=re.I,
        )
        span = re.sub(
            r"100\s*%\s*(?:pure\s+)?coffee|100\s*percent\s+(?:pure\s+)?coffee",
            "70% coffee",
            span,
            flags=re.I,
        )
        return span

    return _ULTRA_FALSE_PURITY.sub(_strip_false_purity, updated)


def repair_content(content: dict) -> dict:
    """Rewrite chicory-scope attacks in a content payload. Does not publish."""
    featured = featured_product_name(content)
    day_scope = name_contains_chicory(featured)

    def walk(node, inherited: bool):
        if isinstance(node, dict):
            blob = " ".join(
                str(node.get(key) or "")
                for key in ("product", "product_slug", "featured_product", "caption", "hook", "hook_text", "body", "primary_cta", "cta")
                if isinstance(node.get(key), str)
            )
            local = inherited or chicory_in_scope(blob, str(node.get("featured_product") or node.get("product") or ""))
            out = {}
            for key, value in node.items():
                if isinstance(value, str):
                    out[key] = repair_text(value, chicory_scope=local or day_scope)
                else:
                    out[key] = walk(value, local or day_scope)
            if featured and "featured_product" not in out and node is content:
                out["featured_product"] = featured
            return out
        if isinstance(node, list):
            return [walk(item, inherited) for item in node]
        if isinstance(node, str):
            return repair_text(node, chicory_scope=inherited)
        return node

    repaired = walk(content, day_scope)
    if isinstance(repaired, dict) and featured and not repaired.get("featured_product"):
        repaired["featured_product"] = featured
    return repaired


def product_truth_findings(text: str, featured: str | None = None) -> list[dict]:
    """Unsupported or contradicted product claims in `text`."""
    if not text or not str(text).strip():
        return []
    source = _claim_text(str(text))
    findings: list[dict] = []
    for sentence in _SENTENCE.split(source):
        s = sentence.strip()
        if not s:
            continue
        if _BRAND_IS_FREEZE_ARABICA.search(s):
            findings.append(_finding(
                s,
                "the brand is not one freeze-dried Arabica jar; name Purica, Prima, Bold, or Purista",
            ))
        if _INVENTED.search(s):
            findings.append(_finding(s, "invented product claim"))
        for clause in _CLAUSE.split(s):
            clause = clause.strip()
            if not clause:
                continue
            for segment in _segments(clause):
                if _ULTRA.search(segment):
                    for match in _PURE_CLAIM.finditer(segment):
                        if not _locally_negated(segment, match.start()):
                            findings.append(_finding(
                                segment,
                                "Ultra Blend is 70% coffee and 30% chicory and is not a zero-chicory jar",
                            ))
                            break
                if (_LOW_CAFFEINE.search(segment) and _OTHER_THAN_ULTRA.search(segment)
                        and not _ULTRA.search(segment)
                        and not _locally_negated(segment, _LOW_CAFFEINE.search(segment).start())):
                    findings.append(_finding(
                        segment,
                        "a lower-caffeine description is allowed only for Ultra Blend",
                    ))
                freeze = _FREEZE.search(segment)
                if _PRIMA.search(segment) and freeze and not _locally_negated(segment, freeze.start()):
                    findings.append(_finding(
                        segment,
                        "Prima / Premium Agglomerate is agglomerated 100% Arabica, not freeze-dried",
                    ))
                robusta = _ROBUSTA_100.search(segment)
                if (_ARABICA_JARS.search(segment) and not _ROBUSTA_JARS.search(segment)
                        and robusta and not _locally_negated(segment, robusta.start())):
                    findings.append(_finding(segment, "Purica and Prima are 100% Arabica, not Robusta"))
                arabica = _ARABICA_100.search(segment)
                if (_ROBUSTA_JARS.search(segment) and not _ARABICA_JARS.search(segment)
                        and arabica and not _locally_negated(segment, arabica.start())):
                    findings.append(_finding(segment, "Bold and Purista are 100% Robusta, not Arabica"))
                duo_bean = _DUO_SINGLE_BEAN.search(segment)
                if duo_bean and not _locally_negated(segment, duo_bean.start()):
                    findings.append(_finding(
                        segment,
                        "Gourmet Duo is Purista (100% Robusta) and Purica (100% Arabica); "
                        "do not call the bundle only " + duo_bean.group(1),
                    ))
                for match in _PERCENT.finditer(segment):
                    if _locally_negated(segment, match.start()):
                        continue
                    number = int(match.group(1))
                    kind = match.group(2).lower()
                    if _ULTRA.search(segment) and kind == "coffee" and number != 70:
                        findings.append(_finding(
                            segment,
                            "Ultra Blend is 70% coffee and 30% chicory; do not invent a different coffee percentage",
                        ))
                    if _ULTRA.search(segment) and kind == "chicory" and number != 30:
                        findings.append(_finding(
                            segment,
                            "Ultra Blend is 30% chicory; do not invent a different chicory percentage",
                        ))
                    if (_ULTRA.search(segment) and kind in {"arabica", "robusta"} and number == 100):
                        findings.append(_finding(
                            segment,
                            "Ultra Blend is 70% coffee and 30% chicory, not a 100% Arabica or 100% Robusta jar",
                        ))
                    if (kind == "chicory" and number not in (0, 30)
                            and not _ULTRA.search(segment)):
                        findings.append(_finding(
                            segment,
                            "chicory is 0% on the pure jars and 30% only in Ultra Blend",
                        ))
                    if (kind == "chicory" and number == 30
                            and _OTHER_THAN_ULTRA.search(segment)
                            and not _ULTRA.search(segment)):
                        findings.append(_finding(
                            segment,
                            "only Ultra Blend is 30% chicory",
                        ))
                    if _PRIMA.search(segment) and kind == "arabica" and number != 100:
                        findings.append(_finding(segment, "Prima / Premium Agglomerate is 100% Arabica"))
        if chicory_in_scope(s, featured) and _ANTI_CHICORY.search(s):
            findings.append(_finding(s, _ANTI_CHICORY_REASON))
    if chicory_in_scope(source, featured):
        # A hook can attack chicory in one sentence and name Ultra Blend in the next.
        for sentence in _SENTENCE.split(source):
            s = sentence.strip()
            if s and _ANTI_CHICORY.search(s):
                findings.append(_finding(s, _ANTI_CHICORY_REASON))
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for item in findings:
        key = (item["type"], item["claim"], item["reason"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
