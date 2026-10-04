"""
Editorial review agent.

Before any piece goes out, an LLM editor scores it on 5 dimensions.
Pieces scoring below EDITORIAL_MIN_SCORE (default 6.5 / 10) are flagged
for regeneration.

Scoring dimensions:
  shareability  — Would a real person forward this?
  saveability   — Would they screenshot / bookmark it?
  emotion_pull  — Does it trigger a strong emotion (anger, pride, joy)?
  hook_strength — Does the opening stop the scroll in < 2 s?
  brand_clarity — Is Purity Beans the obvious winner / solution?

Set ENABLE_EDITORIAL_REVIEW=false to skip (useful in dev / CI).
"""
import json
import logging
import os

logger = logging.getLogger(__name__)

_MIN_SCORE = float(os.getenv("EDITORIAL_MIN_SCORE", "6.5"))
_ENABLED   = os.getenv("ENABLE_EDITORIAL_REVIEW", "true").lower() == "true"

_PROMPT_TEMPLATE = """\
You are an expert social media editor and retention copywriter for Purity Beans (Rs 18/cup). Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee and may be called lower caffeine. Do not reward a claim that the whole range is 100% coffee.

Your job is to audit this content with a stopwatch. Evaluate it line by line.
Flag every moment where a viewer would lose interest, stop watching/reading, or swipe away, and identify exactly why.

CONTENT:
{content_json}

Score each dimension 0–10:
1. shareability  — Would a real Indian consumer forward/share this? (10 = definitely)
2. saveability   — Would they screenshot or save it for later? (10 = definitely)
3. emotion_pull  — Does it trigger anger, pride, joy, or nostalgia? (10 = very strong)
4. hook_strength — Does the opening line stop the scroll in under 2 seconds? (10 = instant stop)
5. brand_clarity — Is Purity Beans the clear winner / solution? (10 = crystal clear)

Scoring rules:
- Generic, safe, or forgettable content scores below 6 on shareability and saveability.
- If the hook could apply to any coffee brand, hook_strength ≤ 5.
- If a line causes an attention drop, penalize hook_strength and saveability.

Reply ONLY with this JSON (no extra text):
{{
  "shareability": <float 0-10>,
  "saveability": <float 0-10>,
  "emotion_pull": <float 0-10>,
  "hook_strength": <float 0-10>,
  "brand_clarity": <float 0-10>,
  "overall": <float 0-10>,
  "verdict": "APPROVE" or "REJECT",
  "feedback": "<actionable critique explaining attention drops and how to rewrite lines to pull the reader to the next>",
  "retention_audit": "<line-by-line critique flagging any weak moments, otherwise empty string>"
}}"""


class EditorialScoreError(RuntimeError):
    """The scorer did not return a usable score. Callers must retry or surface this."""


def review_content(content: dict, label: str = "content") -> dict:
    """
    Run editorial review on a content piece.

    Returns numeric scores. A provider or parse failure is retried once, then
    raised. It is not converted into a 7.0 pass or a 0.0 reject — both of
    those used to look like a real editorial judgment.
    """
    if not _ENABLED:
        return _pass()

    from content_generator.providers.llm_router import call as llm_call
    snippet = json.dumps(content, ensure_ascii=False, indent=2)[:4000]
    prompt = _PROMPT_TEMPLATE.format(content_json=snippet)
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            raw_result = llm_call(prompt, label=f"editorial_{label}", max_tokens=800)
            scores = _validate(raw_result)
            logger.info(
                "[editorial] %s → overall=%.1f  verdict=%s",
                label, scores["overall"], scores["verdict"],
            )
            return scores
        except EditorialScoreError as e:
            last_error = e
            logger.warning(
                "[editorial] %s score parse failed (attempt %d/2): %s",
                label, attempt + 1, e,
            )
        except Exception as e:
            last_error = e
            logger.warning(
                "[editorial] %s scoring call failed (attempt %d/2): %s",
                label, attempt + 1, e,
            )
    raise EditorialScoreError(f"scoring failed for {label}: {last_error}")


def should_regenerate(review: dict) -> bool:
    """Return True if the piece should be regenerated based on review scores."""
    return (
        review.get("verdict") == "REJECT"
        or review.get("overall", 10.0) < _MIN_SCORE
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

def _validate(result: dict) -> dict:
    dims = ["shareability", "saveability", "emotion_pull", "hook_strength", "brand_clarity"]
    if not isinstance(result, dict):
        raise EditorialScoreError(f"score was {type(result).__name__}, not an object")
    for key in ("editorial_score", "scores", "review"):
        inner = result.get(key)
        if isinstance(inner, dict) and any(d in inner for d in dims):
            result = {**result, **inner}
            break

    missing = []
    for d in dims:
        raw = result.get(d)
        if raw in (None, ""):
            missing.append(d)
            continue
        try:
            result[d] = round(max(0.0, min(10.0, float(raw))), 1)
        except (TypeError, ValueError):
            missing.append(d)
    if missing:
        raise EditorialScoreError("score missing dimensions: " + ", ".join(missing))

    raw_overall = result.get("overall")
    if raw_overall in (None, ""):
        result["overall"] = round(sum(result[d] for d in dims) / len(dims), 1)
    else:
        try:
            result["overall"] = round(float(raw_overall), 1)
        except (TypeError, ValueError):
            raise EditorialScoreError(f"overall is not a number: {raw_overall!r}")

    if result.get("verdict") not in ("APPROVE", "REJECT"):
        result["verdict"] = "APPROVE" if result["overall"] >= _MIN_SCORE else "REJECT"

    result.setdefault("feedback", "")
    return result


def _pass() -> dict:
    """Used only when editorial review is explicitly disabled. Not a measured score."""
    return {
        "shareability": 7.0, "saveability": 7.0, "emotion_pull": 7.0,
        "hook_strength": 7.0, "brand_clarity": 7.0, "overall": 7.0,
        "verdict": "APPROVE", "feedback": "",
    }
