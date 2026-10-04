"""Product facts the content gates are allowed to state.

Owner guardrails for Purity Beans copy:
- Prima / Premium Agglomerate is 100% Arabica and agglomerated, not freeze-dried.
- Ultra Blend is 70% coffee. A lower-caffeine description is allowed for that jar.
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
    r"\b(?:bold|purista|purica|prima|premium agglomerate)\b",
    re.I,
)
_PURE_CLAIM = re.compile(
    r"100\s*%\s*(?:pure\s+)?coffee|100\s*percent\s+(?:pure\s+)?coffee|"
    r"zero\s+chicory|0\s*%\s*chicory|\bno chicory\b|\bwithout chicory\b|"
    r"\bchicory[-\s]?free\b|"
    r"\b(?:does not|doesn't|doesnt)\s+contain\s+chicory\b|"
    r"\bcontains?\s+no\s+chicory\b",
    re.I,
)
_SEGMENT = re.compile(r"[,:;]|\s[-–—]\s")
_LOW_CAFFEINE = re.compile(r"\b(?:low(?:er)?|less)[\s-]+caffeine\b", re.I)
_FREEZE = re.compile(r"freeze[\s-]?dried", re.I)
_BRAND_IS_FREEZE_ARABICA = re.compile(
    r"purity beans is freeze[\s-]?dried arabica",
    re.I,
)
_INVENTED = re.compile(
    r"100\s*x\s+purer|lab-tested purity certificate|single-origin style|"
    r"70\s*[-–]\s*80\s*%\s*chicory|hand-selected chicory|"
    r"\bsmall[\s-]batch(?:es)?\b",
    re.I,
)
_PERCENT = re.compile(
    r"\b(\d+)\s*(?:%|percent)\s*(coffee|arabica|robusta|chicory)\b",
    re.I,
)
_ROBUSTA_100 = re.compile(r"\b100\s*(?:%|percent)\s*(?:pure\s+)?robusta\b", re.I)
_ARABICA_100 = re.compile(r"\b100\s*(?:%|percent)\s*(?:pure\s+)?arabica\b", re.I)


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


def product_truth_findings(text: str) -> list[dict]:
    """Unsupported or contradicted product claims in `text`."""
    if not text or not str(text).strip():
        return []
    findings: list[dict] = []
    for sentence in _SENTENCE.split(str(text)):
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
                                "Ultra Blend is 70% coffee and is not a zero-chicory jar",
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
                for match in _PERCENT.finditer(segment):
                    if _locally_negated(segment, match.start()):
                        continue
                    number = int(match.group(1))
                    kind = match.group(2).lower()
                    if _ULTRA.search(segment) and kind == "coffee" and number != 70:
                        findings.append(_finding(
                            segment,
                            "Ultra Blend is 70% coffee; do not invent a different coffee percentage",
                        ))
                    if _ULTRA.search(segment) and kind in {"arabica", "robusta"} and number == 100:
                        findings.append(_finding(
                            segment,
                            "Ultra Blend is 70% coffee, not a 100% Arabica or 100% Robusta jar",
                        ))
                    if _PRIMA.search(segment) and kind == "arabica" and number != 100:
                        findings.append(_finding(segment, "Prima / Premium Agglomerate is 100% Arabica"))
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for item in findings:
        key = (item["type"], item["claim"], item["reason"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique
