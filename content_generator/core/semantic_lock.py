"""
Semantic Premise Lock — prevents portfolio topic cannibalization.

Ensures:
  platform A premise != platform B premise

One research discovery must not turn into the same single topic repeated
across 8 assets. Each platform must explore an independent angle.
"""
from __future__ import annotations
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

TOPIC_CLUSTERS: dict[str, list[str]] = {
    "chicory_filler": ["chicory", "root", "wartime", "adulter", "filler"],
    "extraction_physics": ["temperature", "100°c", "85°c", "boiling", "scorch", "tannin"],
    "processing_science": ["freeze-dried", "freeze dried", "spray-dried", "spray dried", "-40", "sublimation"],
    "botany_varietal": ["arabica", "robusta", "altitude", "crema", "lipid"],
    "jar_storage": ["storage", "airtight", "fridge", "freezer", "oxidation", "moisture"],
    "cup_economics": ["rs 18", "cafe cup", "economics", "home math", "rs 250"],
    "label_reading": ["ingredient list", "back of the jar", "label literacy", "fine print"],
    "family_ritual": ["household", "family", "grandmothers", "mother", "guest"],
}


def extract_primary_cluster(piece: dict) -> str | None:
    """Identify the dominant semantic cluster for a piece."""
    if not isinstance(piece, dict) or not piece:
        return None
    text = " ".join(
        str(piece.get(k) or "")
        for k in ("hook", "hook_text", "headline", "title", "caption", "body", "text", "angle")
    ).lower()

    scores: dict[str, int] = {}
    for cluster_name, keywords in TOPIC_CLUSTERS.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scores[cluster_name] = hits

    if not scores:
        return None
    return max(scores, key=scores.get)


def verify_portfolio_diversity(pieces: dict[str, dict]) -> dict[str, Any]:
    """
    Verify that assets across platforms do not share the exact same premise.

    Returns:
        {
            "passes": bool,
            "clusters": dict[str, str],
            "duplicates": dict[str, list[str]],
            "diversity_ratio": float
        }
    """
    assigned: dict[str, str] = {}
    clusters_to_keys: dict[str, list[str]] = {}

    for key, piece in pieces.items():
        if not isinstance(piece, dict) or not piece:
            continue
        cluster = extract_primary_cluster(piece)
        if cluster:
            assigned[key] = cluster
            clusters_to_keys.setdefault(cluster, []).append(key)

    duplicates = {c: keys for c, keys in clusters_to_keys.items() if len(keys) > 2}
    total_tagged = len(assigned)
    distinct_clusters = len(clusters_to_keys)
    diversity_ratio = (distinct_clusters / total_tagged) if total_tagged else 1.0

    passes = len(duplicates) == 0 and diversity_ratio >= 0.5

    if not passes:
        logger.warning(
            "[semantic_lock] Portfolio cannibalization warning: duplicate clusters %s (diversity=%.2f)",
            duplicates,
            diversity_ratio,
        )

    return {
        "passes": passes,
        "clusters": assigned,
        "duplicates": duplicates,
        "diversity_ratio": round(diversity_ratio, 2),
    }
