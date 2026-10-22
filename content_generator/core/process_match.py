"""Process claims have to match the jar they are tied to.

Freeze-dried: Purica (Arabica) and Purista (Robusta) only, plus Gourmet Duo
and Gourmet Duo Mini (those two jars). Agglomerated: Bold (pure coffee) and
Prima (pure Arabica, out of stock — existing gates still refuse to promote it).
Ultra Blend has no process claim. Do not invent another process for any jar.

A mention of freeze-dried / freeze-drying, agglomerat*, or granules used as a
process must be true of the product it names. If the line names no jar, it is
read as a claim about the featured or linked product. A comparison of
freeze-dried and agglomerated coffee may link Bold for the agglomerated side.
It must not call Bold freeze-dried. Process education about freeze-drying
links Purica, Purista, the Variety Box, or Gourmet Duo Mini (Gourmet Duo is
the same two freeze-dried jars).

The check is additive. It does not relax chicory, price, FSSAI, or Prima
promotion gates. A miss fails the piece so generation rewrites or regenerates.
"""
from __future__ import annotations

import re

PROCESS_MATCH_RULE = (
    "PROCESS MATCH — Threads, Instagram, Facebook, LinkedIn, YouTube, Stories, "
    "Reels, carousels, and campaign push: freeze-dried means only Purica (Arabica) "
    "and Purista (Robusta). Gourmet Duo and Gourmet Duo Mini are those two "
    "freeze-dried jars. Agglomerated means Bold (pure coffee) and Prima "
    "(pure Arabica Premium Agglomerate). Prima is out of stock — do not feature it "
    "or tell people to buy it. Do not name a process for Ultra Blend, and do not "
    "invent a process for any jar. Any mention of freeze-dried, freeze-drying, "
    "agglomerated/agglomeration, or granules as a process must be true of the "
    "featured or linked product. If it is not, rewrite the line or stop and regenerate. "
    "A post that teaches freeze-drying must link Purica, Purista, the Variety Box, "
    "or Gourmet Duo Mini. A freeze-dried vs agglomerated comparison may link Bold "
    "for the agglomerated side and must not call Bold freeze-dried."
)

_FREEZE = re.compile(r"freeze[\s-]?dr(?:ied|ying)", re.I)
_AGGLO = re.compile(r"agglomerat\w*", re.I)
_GRANULE_PROCESS = re.compile(
    r"\bgranules?\s+(?:process|method|technique)\b"
    r"|\bgranule[-\s]?process\b"
    r"|\bgranulation\b"
    r"|\b(?:processed|processing|made|produced|formed)\s+(?:into|as)\s+granules?\b",
    re.I,
)
_PREMIUM_AGGLOMERATE = re.compile(r"premium\s+agglomerate\b", re.I)
_BOX_COPULA = re.compile(
    r"variety box\s+is\s+(?:freeze[\s-]?dr|agglomerat)",
    re.I,
)

_FREEZE_SLUGS = frozenset({"purica", "purista", "gourmet_duo", "gourmet_duo_mini"})
_AGGLO_SLUGS = frozenset({"bold", "prima"})
_GRANULE_SLUGS = _FREEZE_SLUGS
_EDU_LINKS = frozenset({
    "purica", "purista", "variety_box", "gourmet_duo_mini", "gourmet_duo",
})
_HANDLES = (
    ("gourmet-duo-mini", "gourmet_duo_mini"),
    ("gourmet-duo", "gourmet_duo"),
    ("purity-beans-purista-gourmet-instant-coffee-granules", "purista"),
    ("purity-beans-purica-gourmet-instant-coffee-granules", "purica"),
    ("purity-beans-ultra-blend-instant-coffee", "ultra_blend"),
    ("purity-beans-prima-premium-instant-coffee", "prima"),
    ("purity-beans-bold-instant-coffee", "bold"),
    ("variety-box", "variety_box"),
)
_REWRITES = (
    (re.compile(r"\bBold is freeze[\s-]?dried\b", re.I), "Bold is agglomerated"),
    (re.compile(r"\bfreeze[\s-]?dried Bold\b", re.I), "agglomerated Bold"),
    (re.compile(r"\bUltra Blend is freeze[\s-]?dried\b", re.I),
     "Ultra Blend is 70% coffee and 30% chicory"),
    (re.compile(r"\bUltra Blend is agglomerat\w*\b", re.I),
     "Ultra Blend is 70% coffee and 30% chicory"),
    (re.compile(r"\bPurica is agglomerat\w*\b", re.I), "Purica is freeze-dried"),
    (re.compile(r"\bPurista is agglomerat\w*\b", re.I), "Purista is freeze-dried"),
)


def _finding(sentence: str, reason: str) -> dict:
    return {"claim": sentence.strip()[:140], "type": "product_truth", "reason": reason}


def _allows(slug: str, kind: str) -> bool:
    if slug == "ultra_blend":
        return False
    if kind == "freeze":
        return slug in _FREEZE_SLUGS or slug == "variety_box"
    if kind == "agglomerated":
        return slug in _AGGLO_SLUGS or slug == "variety_box"
    if kind == "granule_process":
        return slug in _GRANULE_SLUGS or slug == "variety_box"
    return False


def _spans(sentence: str) -> list[tuple[str, re.Match]]:
    found: list[tuple[str, re.Match]] = []
    for kind, pattern in (
        ("freeze", _FREEZE),
        ("agglomerated", _AGGLO),
        ("granule_process", _GRANULE_PROCESS),
    ):
        for match in pattern.finditer(sentence):
            if kind == "agglomerated" and _name_only(sentence, match):
                continue
            found.append((kind, match))
    return found


def _name_only(sentence: str, match: re.Match) -> bool:
    """'Premium Agglomerate' is Prima's name, not a separate process claim."""
    window = sentence[max(0, match.start() - 12):match.end()]
    name = _PREMIUM_AGGLOMERATE.search(window)
    return bool(name) and name.end() + max(0, match.start() - 12) >= match.end()


def _token_hits(sentence: str) -> list[tuple[int, int, str]]:
    from content_generator.core.product_truth import _SLUG_TOKENS

    hits: list[tuple[int, int, str]] = []
    raw = sentence.lower()
    for slug, tokens in _SLUG_TOKENS:
        for token in tokens:
            for match in re.finditer(
                rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", raw,
            ):
                hits.append((match.start(), match.end(), slug))
    return hits


def _owner(clause: str, match: re.Match) -> str:
    """The jar this process word is about.

    "agglomerated Bold" belongs to Bold, even when Purista sits a few words
    earlier. "Bold is agglomerated" belongs to Bold. A bare process word with
    no jar stays unattributed.
    """
    hits = _token_hits(clause)
    if not hits:
        return ""
    start, end = match.start(), match.end()
    later = [other.start() for _, other in _spans(clause) if other.start() > start]
    limit = min(later) if later else len(clause)
    after = [hit for hit in hits if end <= hit[0] < limit and hit[0] - end <= 40]
    if after:
        after.sort()
        return after[0][2]
    before = [hit for hit in hits if hit[1] <= start and start - hit[1] <= 48]
    if not before:
        return ""
    before.sort(key=lambda hit: hit[1], reverse=True)
    gap = clause[before[0][1]:start]
    if re.match(r"\s*(?:is|are|uses|using|,|:|–|—|-)\s*$", gap, re.I):
        return before[0][2]
    return ""


def _featured_slug(featured: str | None) -> str:
    if not str(featured or "").strip():
        return ""
    from content_generator.core.product_truth import named_slugs

    found = named_slugs(str(featured))
    return found[0] if found else ""


def _linked_slugs(text: str) -> list[str]:
    raw = str(text or "").lower()
    found: list[str] = []
    for handle, slug in _HANDLES:
        if f"/products/{handle}" in raw and slug not in found:
            found.append(slug)
    return found


def _destination(text: str, featured: str | None) -> str:
    """The product a reader would open. A product URL is that link."""
    linked = _linked_slugs(text)
    if linked:
        return linked[0]
    return _featured_slug(featured)


def _reason(kind: str, dest: str, owner: str) -> str:
    if owner == "ultra_blend" or dest == "ultra_blend":
        return (
            "Ultra Blend has no process claim; do not call it freeze-dried, "
            "agglomerated, or a granule process"
        )
    if owner == "bold" and kind in {"freeze", "granule_process"}:
        return (
            "Bold is agglomerated pure coffee, not freeze-dried; "
            "do not call Bold freeze-dried or a granule process"
        )
    if owner in _FREEZE_SLUGS and kind == "agglomerated":
        return (
            f"{owner.replace('_', ' ')} is freeze-dried, not agglomerated"
        )
    if kind == "freeze" and dest == "bold":
        return (
            "freeze-drying matches Purica and Purista, not Bold; "
            "a freeze-dried vs agglomerated comparison may link Bold only for "
            "the agglomerated side and must not call Bold freeze-dried"
        )
    if kind == "freeze":
        return (
            "a freeze-drying mention must match Purica, Purista, "
            "Variety Box, or Gourmet Duo Mini"
        )
    if kind == "agglomerated":
        return (
            "an agglomerated mention must match Bold "
            "(Prima is agglomerated and out of stock — do not promote it)"
        )
    return (
        "granules as a process match freeze-dried Purica and Purista, "
        "not this product"
    )


def process_match_findings(text: str, featured: str | None = None) -> list[dict]:
    """Process mentions that contradict the jar they are about or linked to."""
    if not text or not str(text).strip():
        return []
    from content_generator.core.product_truth import (
        _CLAUSE, _SENTENCE, _claim_text, _locally_negated, named_slugs,
    )

    source = _claim_text(str(text))
    findings: list[dict] = []
    attributions: dict[str, set[str]] = {
        "freeze": set(), "agglomerated": set(), "granule_process": set(),
    }
    claimed: set[str] = set()
    bold_called_freeze = False

    for sentence in _SENTENCE.split(source):
        sentence = sentence.strip()
        if not sentence:
            continue
        for clause in _CLAUSE.split(sentence):
            clause = clause.strip()
            if not clause:
                continue
            if _BOX_COPULA.search(clause):
                findings.append(_finding(
                    clause,
                    "the Variety Box includes freeze-dried Purica and Purista "
                    "and agglomerated Bold; do not call the box itself one process, "
                    "and do not name a process for the Ultra Blend jar",
                ))
            alone = {slug for _start, _end, slug in _token_hits(clause)}
            for kind, match in _spans(clause):
                if _locally_negated(clause, match.start()):
                    continue
                owner = _owner(clause, match)
                if not owner and len(alone) == 1:
                    owner = next(iter(alone))
                claimed.add(kind)
                if owner:
                    attributions[kind].add(owner)
                    if owner == "bold" and kind == "freeze":
                        bold_called_freeze = True
                    if not _allows(owner, kind):
                        findings.append(_finding(clause, _reason(kind, owner, owner)))
    if not claimed:
        return _unique(findings)

    dest = _destination(source, featured)
    comparison = "freeze" in claimed and "agglomerated" in claimed
    named = named_slugs(source)
    if dest and not all(
        _kind_ok(dest, kind, attributions, comparison, bold_called_freeze, named)
        for kind in claimed
    ):
        kind = next(iter(claimed))
        for item in ("freeze", "granule_process", "agglomerated"):
            if item in claimed and not _kind_ok(
                dest, item, attributions, comparison, bold_called_freeze, named,
            ):
                kind = item
                break
        findings.append(_finding(source, _reason(kind, dest, dest if dest in named else "")))
    return _unique(findings)


def _kind_ok(dest, kind, attributions, comparison, bold_called_freeze, named) -> bool:
    owners = attributions.get(kind) or set()
    if dest in owners and not _allows(dest, kind):
        return False
    if bold_called_freeze and dest == "bold" and kind in {"freeze", "granule_process"}:
        return False
    if not owners:
        if _allows(dest, kind):
            return True
        return bool(
            dest == "bold" and kind == "freeze" and comparison and not bold_called_freeze
        )
    if not all(_allows(owner, kind) for owner in owners):
        return False
    if dest == "ultra_blend" and dest not in owners and len(named) >= 2:
        return True
    if kind in {"freeze", "granule_process"} and dest == "bold":
        return bool(comparison and not bold_called_freeze)
    if kind in {"freeze", "granule_process"} and dest not in _EDU_LINKS:
        return False
    if kind == "agglomerated" and dest not in (_AGGLO_SLUGS | {"variety_box"}):
        return bool(comparison and dest in _EDU_LINKS)
    return True


def _unique(findings: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for item in findings:
        key = (item["reason"], item["claim"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


_AGGLO_WORD = re.compile(r"\bagglomerat\w*\b", re.I)
_AGGLO_TAG = re.compile(r"agglomerat\w*(?:\s+coffee)?", re.I)


def rewrite_process_text(text: str) -> str:
    """Correct a direct false process label. Leave essays for regeneration."""
    if not isinstance(text, str) or not text:
        return text
    updated = text
    for pattern, replacement in _REWRITES:
        updated = pattern.sub(replacement, updated)
    return updated


def _drop_unowned_agglomerated(text: str, featured: str | None) -> str:
    """Drop stray agglomerated wording on a freeze-dried jar that names no Bold or Prima."""
    if not text or not _AGGLO_WORD.search(text):
        return text
    dest = _destination(text, featured) or _featured_slug(featured)
    if dest not in _FREEZE_SLUGS:
        return text
    from content_generator.core.product_truth import named_slugs

    if any(slug in _AGGLO_SLUGS for slug in named_slugs(text)):
        return text
    if _AGGLO_TAG.fullmatch(text.strip()):
        return "instant coffee"
    protected: list[str] = []

    def hold(match: re.Match) -> str:
        protected.append(match.group(0))
        return f"\ue000{len(protected) - 1}\ue001"

    held = _PREMIUM_AGGLOMERATE.sub(hold, text)
    held = _AGGLO_WORD.sub("", held)
    held = re.sub(r"\s+(?:and|&)\s+(?=variants\b)", " ", held, flags=re.I)
    held = re.sub(r"\s{2,}", " ", held)
    held = re.sub(r"\s+,", ",", held)
    held = re.sub(r",\s*,", ", ", held)

    def restore(match: re.Match) -> str:
        return protected[int(match.group(1))]

    return re.sub(r"\ue000(\d+)\ue001", restore, held).strip()


_MIXED_PROCESS = re.compile(
    r"\bagglomerat\w*\s+or\s+freeze[\s-]?dr\w*\b|\bfreeze[\s-]?dr\w*\s+or\s+agglomerat\w*\b",
    re.I,
)
_PROCESS_WORD = re.compile(
    r"freeze[\s-]?dr(?:ied|ying)|\bagglomerat\w*\b|" + _GRANULE_PROCESS.pattern, re.I,
)
_DEST_LINE = {
    "bold": "Bold is agglomerated pure coffee.",
    "prima": "Prima is agglomerated pure Arabica, not freeze-dried.",
    "ultra_blend": "Ultra Blend is 70% coffee and 30% chicory.",
    "purica": "Purica is freeze-dried pure Arabica.",
    "purista": "Purista is freeze-dried pure Robusta.",
    "gourmet_duo": "Gourmet Duo is freeze-dried Purica and Purista.",
    "gourmet_duo_mini": "Gourmet Duo Mini is freeze-dried Purica and Purista.",
    "variety_box": "The Variety Box includes freeze-dried Purica and Purista and agglomerated Bold.",
}
_SCORE_KEYS = {"editorial_score", "editorial_error", "viral_potential", "gate_rejection", "fallback_ladder"}


def _sentences(text: str) -> list[str]:
    from content_generator.core.product_truth import _SENTENCE
    return [part.strip() for part in _SENTENCE.split(text) if part and part.strip()]


def _bad(text: str, featured: str | None) -> bool:
    return bool(process_match_findings(text, featured))


def _with_line(text: str, line: str) -> str:
    text = (text or "").strip()
    if not line or line.lower() in text.lower():
        return text
    if text and text[-1] not in ".!?":
        text += "."
    return f"{text} {line}".strip()


def _fix_sentence(sentence: str) -> str:
    if _BOX_COPULA.search(sentence):
        return _DEST_LINE["variety_box"]
    if _MIXED_PROCESS.search(sentence):
        return _MIXED_PROCESS.sub(
            "Bold is agglomerated pure coffee, and Purica and Purista are freeze-dried", sentence,
        )
    from content_generator.core.product_truth import _CLAUSE, _locally_negated
    for clause in _CLAUSE.split(sentence):
        clause = clause.strip()
        if not clause:
            continue
        alone = {slug for _start, _end, slug in _token_hits(clause)}
        for kind, match in _spans(clause):
            if _locally_negated(clause, match.start()):
                continue
            owner = _owner(clause, match) or (next(iter(alone)) if len(alone) == 1 else "")
            if owner and not _allows(owner, kind):
                return _DEST_LINE.get(owner) or sentence
    return sentence


def comply_process_text(text: str, featured: str | None = None) -> str:
    """Rewrite process wording until the gate is clean. A miss still fails closed."""
    if not isinstance(text, str) or not text.strip():
        return text
    dest = _destination(text, featured) or _featured_slug(featured)

    def polish(value: str) -> str:
        return _drop_unowned_agglomerated(rewrite_process_text(value), featured)

    updated = polish(text)
    if not _bad(updated, featured):
        return updated
    if updated.strip().startswith("#") or updated.count("#") >= 2:
        cleaned = re.sub(r"\s{2,}", " ", _PROCESS_WORD.sub("", updated)).strip()
        if cleaned and not _bad(cleaned, featured):
            return cleaned
    updated = polish(" ".join(_fix_sentence(part) for part in _sentences(updated)))
    if not _bad(updated, featured):
        return updated
    if dest == "ultra_blend":
        updated = " ".join(part for part in _sentences(updated) if not _spans(part)).strip()
        return _with_line(updated, _DEST_LINE["ultra_blend"]) if "70% coffee" not in updated else updated
    if dest in _AGGLO_SLUGS:
        updated = polish(_with_line(updated, _DEST_LINE[dest]))
        if not _bad(updated, featured):
            return updated
    updated = " ".join(part for part in _sentences(updated) if not _bad(part, featured)).strip()
    line = _DEST_LINE.get(dest, "")
    if line and not _bad(_with_line(updated, line), featured):
        return _with_line(updated, line)
    if line and _bad(updated, featured) and not _bad(line, featured):
        return line
    return updated.strip() or text


def align_process_piece(piece: dict, featured: str | None = None) -> dict:
    """Rewrite process labels on one asset before the gate runs."""
    if not isinstance(piece, dict):
        return piece

    def walk(node):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key in _SCORE_KEYS:
                    continue
                if isinstance(value, str):
                    node[key] = comply_process_text(value, featured)
                elif isinstance(value, (dict, list)):
                    walk(value)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                if isinstance(item, str):
                    node[index] = comply_process_text(item, featured)
                else:
                    walk(item)

    walk(piece)
    return piece
