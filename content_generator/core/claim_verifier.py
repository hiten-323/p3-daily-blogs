"""
Claim verification — the layer `require_claim_verification` was supposed to call.

The psychology registry tags frames with a risk level, and governance said:

    medium risk -> claim verification mandatory
    high risk   -> claim verification + source backing + manual review

The implementation was literally:

    if psychology_governance.get("require_claim_verification"):
        pass

So the architecture claimed a verification step that did not exist. Anything a
medium-risk frame produced went out unchecked. This module makes the rule real.

WHAT COUNTS AS A CLAIM
  Not every sentence is a claim. A question, an instruction ("read the label"),
  or an observation about our own product is fine. What needs backing is an
  assertion of fact that a reader could act on and we could be held to:

    statistic          "50 percent of X"          -> needs a source
    competitor claim   "other brands add chicory" -> needs a source
    health claim       "lowers cholesterol"       -> needs a source, and is
                                                     prohibited outright
    offer              "first cup free"           -> needs a real campaign
    superlative        "India's cleanest coffee"  -> needs substantiation

VERIFIED FACTS come from the brand constitution, never from the LLM and never
from the psychology layer. Psychology decides how to say something; it is not a
source of truth about what is true.
"""
from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

# Facts Purity Beans can state without a citation because they are verifiable
# from its own product and label. Kept deliberately short — everything outside
# this set needs backing.
VERIFIED_FACTS = (
    "100% coffee", "100 percent coffee", "zero chicory", "0% chicory",
    "no chicory", "without chicory", "nothing added", "no additives",
    "no added sugar", "no preservatives", "freeze dried", "freeze-dried",
    "premium instant coffee", "arabica", "robusta", "p3online.in",
    "70% coffee", "70 percent coffee", "30% chicory", "30 percent chicory",
)

# Claims that are prohibited outright — no source makes these publishable for
# an FMCG coffee brand without regulatory sign-off.
_HEALTH_CLAIM = re.compile(
    r"\b(cure|cures|treat|treats|heal|heals|prevent|prevents|"
    r"weight\s+loss|lose\s+weight|burn\s+fat|fat\s+burning|"
    r"cholesterol|diabetes|blood\s+pressure|detox|immunity|"
    r"clinically\s+proven|doctor\s+recommended)\b", re.I)

# Match verified facts on WORD BOUNDARIES, never as bare substrings.
#
# `"0% chicory" in "40% chicory"` is True, so a plain `in` check marked the
# fabricated "40% chicory" claim — the one that actually published — as a
# verified brand fact and waved it through. The same bug was fixed once in the
# scrubber's whitelist and reintroduced here. The lookbehind rejects a match
# whose preceding character is part of a longer token.
_VERIFIED_RE = re.compile(
    "|".join(r"(?<!\w)" + re.escape(f) for f in VERIFIED_FACTS), re.I)


def _is_supported(sentence: str, allowed_re) -> bool:
    return bool(_VERIFIED_RE.search(sentence)) or bool(allowed_re.search(sentence))


_SUPERLATIVE = re.compile(
    r"\b(india'?s|world'?s|market'?s)\s+(best|cleanest|purest|finest|"
    r"strongest|healthiest|number\s+one|no\.?\s*1)\b"
    r"|\b(the\s+)?(best|cleanest|purest)\s+(coffee|instant\s+coffee)\s+in\s+india\b",
    re.I)


def _shared_patterns():
    """
    Reuse the scrubber's patterns so there is ONE definition of what a
    fabricated statistic or competitor claim looks like. Two copies would drift,
    and the copy that drifts is the one that lets a claim through.
    """
    from content_generator.scheduler.daily import (
        _STAT_PATTERNS, _ALLOWED_NUMERIC, _COMPETITOR_SUBJECT, _COMPOSITION_VERB,
        _INVENTED_OFFER,
    )
    return (_STAT_PATTERNS, _ALLOWED_NUMERIC, _COMPETITOR_SUBJECT,
            _COMPOSITION_VERB, _INVENTED_OFFER)


def verify_claims(text: str) -> list[dict]:
    """
    Return every unsupported claim in `text`.
    Empty list means nothing needing backing was found.

    Each finding: {"claim": str, "type": str, "reason": str}
    """
    if not text or not str(text).strip():
        return []
    try:
        stat_re, allowed_re, comp_re, verb_re, offer_re = _shared_patterns()
    except Exception as e:
        # Fail CLOSED: if the patterns cannot be loaded we cannot verify, and an
        # unverifiable claim must not be treated as verified.
        logger.error("[claims] verification patterns unavailable: %s", e)
        return [{"claim": str(text)[:120], "type": "verifier_unavailable",
                 "reason": "claim patterns could not be loaded — failing closed"}]

    findings = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(text)):
        s = sentence.strip()
        if not s:
            continue
        supported = _is_supported(s, allowed_re)

        if _HEALTH_CLAIM.search(s):
            findings.append({"claim": s[:140], "type": "health_claim",
                             "reason": "medical/health claims are prohibited for this brand"})
            continue
        # Competitor claims are checked BEFORE statistics so they carry the more
        # specific label — a fabricated number about a rival is a competitor
        # claim first, and that is the classification the risk rules care about.
        if comp_re.search(s) and verb_re.search(s):
            findings.append({"claim": s[:140], "type": "competitor_claim",
                             "reason": "assertion about another brand's contents, unverifiable"})
            continue
        from content_generator.scheduler.daily import sentence_has_unsupported_statistic
        if sentence_has_unsupported_statistic(s):
            findings.append({"claim": s[:140], "type": "statistic",
                             "reason": "numeric claim with no verified source"})
            continue
        if offer_re.search(s):
            findings.append({"claim": s[:140], "type": "offer",
                             "reason": "promotional offer not backed by a real campaign"})
            continue
        if _SUPERLATIVE.search(s) and not supported:
            findings.append({"claim": s[:140], "type": "superlative",
                             "reason": "unsubstantiated superlative"})
    from content_generator.core.product_truth import product_truth_findings
    findings.extend(product_truth_findings(str(text)))
    return findings


def verify_piece(piece: dict) -> list[dict]:
    """Run verification across every copy field of one content asset."""
    if not isinstance(piece, dict):
        return []
    parts = []
    for k in ("hook", "hook_text", "headline", "title", "caption", "body",
              "body_html", "intro", "introduction", "conclusion",
              "meta_description", "cta", "on_screen", "spoken"):
        v = piece.get(k)
        if isinstance(v, str):
            parts.append(v)
    for lst in ("slides", "frames", "script", "scenes"):
        for item in (piece.get(lst) or []):
            if isinstance(item, dict):
                for k in ("heading", "headline", "body", "on_screen", "spoken", "voiceover"):
                    v = item.get(k)
                    if isinstance(v, str):
                        parts.append(v)
            elif isinstance(item, str):
                parts.append(item)
    findings = []
    for part in parts:
        findings.extend(verify_claims(part))
    # De-duplicate — the same claim often appears in caption and on-screen copy.
    seen, unique = set(), []
    for f in findings:
        key = (f["type"], f["claim"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def requires_source_backing(findings: list[dict]) -> list[dict]:
    """Findings that a citation could rescue — health claims never qualify."""
    return [f for f in findings if f["type"] != "health_claim"]
