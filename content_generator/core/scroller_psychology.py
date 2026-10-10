"""
Scroller psychology — why someone stops scrolling.

Distinct from coffee_psychology, which answers why someone cares, shares or
buys. Kept as separate registries on purpose (ADR-002): attention and meaning
are different decisions, and merging them produces a hook bank rather than a
model of viewer behaviour.

    Scroller psychology  ->  "Why would someone stop?"
    Coffee psychology    ->  "Why would someone share/save/follow/buy?"

SCOPE OF THIS FILE (ADR-002 Phases 1-2)
  It CLASSIFIES what a piece of content actually does, and enforces that a
  curiosity mechanism is paid off. It does not yet SELECT a mechanism before
  generation — that is Phase 4, and it is deliberately held until measurement
  is confirmed working, because a selection layer that cannot be evaluated is
  a more elaborate guess.

  Classification-now/selection-later is the honest ordering: it starts
  accumulating the data Phase 4 needs to be worth anything, without pretending
  we already know which mechanism wins.

NO "default" MECHANISM. Classification returns "" when it cannot tell, and ""
is recorded as unknown rather than smuggled in as a real value — the same rule
that governs psychology frames.
"""
from __future__ import annotations
import logging
import re

logger = logging.getLogger(__name__)

# Each entry describes an actual viewer behaviour, not a copywriting trick.
# `payoff_requirement` is what the viewer must RECEIVE for the mechanism to be
# honest — an open loop with nothing behind it is bait.
MECHANISMS: list[dict] = [
    {"id": "pattern_interrupt", "name": "Pattern interrupt",
     "description": "Breaks the visual or verbal rhythm of the feed.",
     "payoff_requirement": "the interruption must lead somewhere, not just startle",
     "signals": ("stop", "wait", "actually", "no one", "nobody", "never")},
    {"id": "curiosity_gap", "name": "Curiosity gap",
     "description": "Names a specific thing the viewer does not know.",
     "payoff_requirement": "the gap must be closed inside the same asset",
     "signals": ("what", "why", "how", "the reason", "turns out", "difference")},
    {"id": "open_loop", "name": "Open loop",
     "description": "Starts something the viewer needs finished.",
     "payoff_requirement": "the loop must close before the asset ends",
     "signals": ("until", "before you", "next time", "then", "watch what")},
    {"id": "recognition", "name": "Recognition",
     "description": "Viewer sees their own experience described.",
     "payoff_requirement": "must explain the experience, not merely name it",
     "signals": ("you know when", "ever", "every morning", "we all", "your")},
    {"id": "surprise", "name": "Surprise",
     "description": "A true fact that contradicts an assumption.",
     "payoff_requirement": "the surprising claim must be verifiable",
     "signals": ("isn't", "is not", "wrong", "myth", "actually", "not really")},
    {"id": "useful_discovery", "name": "Useful discovery",
     "description": "Something the viewer can use immediately.",
     "payoff_requirement": "must be actionable without buying anything",
     "signals": ("check", "read the label", "test", "try", "look for", "compare")},
    {"id": "identity_signal", "name": "Identity signal",
     "description": "Says something about the kind of person the viewer is.",
     "payoff_requirement": "must be earned, not flattery",
     "signals": ("if you", "people who", "real coffee", "serious about")},
    {"id": "tension_resolution", "name": "Tension and resolution",
     "description": "Sets up a problem, then resolves it.",
     "payoff_requirement": "the resolution must be shown, not promised",
     "signals": ("problem", "but", "however", "the fix", "instead", "solution")},
    {"id": "specificity", "name": "Specificity",
     "description": "A concrete detail that proves first-hand knowledge.",
     "payoff_requirement": "the detail must be checkable",
     "signals": ("seconds", "minutes", "gram", "label", "ingredient", "rs ")},
    {"id": "social_currency", "name": "Social currency",
     "description": "Worth repeating because it makes the sharer look informed.",
     "payoff_requirement": "must give the sharer something to say",
     "signals": ("most people", "nobody tells", "little known", "insider")},
    {"id": "proof", "name": "Proof",
     "description": "Demonstrates rather than asserts.",
     "payoff_requirement": "the demonstration must be visible",
     "signals": ("watch", "see", "side by side", "here is", "look at", "shows")},
]
MECHANISMS_BY_ID = {m["id"]: m for m in MECHANISMS}

# Viewer states. Each needs a different opening move; using one mechanism for
# every asset is what makes a feed monotonous.
STATES: list[dict] = [
    {"id": "uninterested", "needs": "pattern interruption"},
    {"id": "curious",      "needs": "a clear unanswered question"},
    {"id": "skeptical",    "needs": "proof"},
    {"id": "busy",         "needs": "immediate utility"},
    {"id": "identity_seeking", "needs": "self-recognition"},
    {"id": "informed",     "needs": "a new discovery"},
    {"id": "ready_to_buy", "needs": "trust and reduced friction"},
]
STATES_BY_ID = {s["id"]: s for s in STATES}

_STATE_FOR_MECHANISM = {
    "pattern_interrupt": "uninterested",
    "curiosity_gap": "curious",
    "open_loop": "curious",
    "recognition": "identity_seeking",
    "surprise": "informed",
    "useful_discovery": "busy",
    "identity_signal": "identity_seeking",
    "tension_resolution": "skeptical",
    "specificity": "skeptical",
    "social_currency": "identity_seeking",
    "proof": "skeptical",
}


def _copy_of(piece: dict) -> str:
    """All viewer-facing copy in one string."""
    if not isinstance(piece, dict):
        return ""
    parts = [str(piece.get(k) or "") for k in
             ("hook", "hook_text", "hook_spoken", "hook_text_overlay", "headline",
              "title", "caption", "body", "text", "cta", "primary_cta")]
    for lst in ("slides", "frames", "script", "scenes"):
        for item in (piece.get(lst) or []):
            if isinstance(item, dict):
                parts += [str(item.get(k) or "") for k in
                          ("heading", "headline", "body", "on_screen", "spoken", "voiceover")]
            elif isinstance(item, str):
                parts.append(item)
    return " ".join(parts).lower()


def classify_mechanism(piece: dict) -> str | None:
    """
    Which attention mechanism this copy actually uses.
    Returns None when it cannot tell — never a placeholder id, never "default".
    """
    text = _copy_of(piece)
    if not text.strip():
        return None
    scores = {m["id"]: sum(1 for s in m["signals"] if s in text) for m in MECHANISMS}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None


def classify_state(piece: dict) -> str | None:
    """The viewer state the copy is written for, derived from its mechanism."""
    mech = classify_mechanism(piece)
    return _STATE_FOR_MECHANISM.get(mech) if mech else None


# How the hook is constructed, independent of which mechanism it serves.
_HOOK_STRATEGIES = {
    "question":       re.compile(r"\?\s*$|^\s*(what|why|how|when|which|who)\b", re.I),
    "negation":       re.compile(r"\b(isn'?t|is not|don'?t|do not|never|stop|not really)\b", re.I),
    "second_person":  re.compile(r"\b(you|your|you'?re)\b", re.I),
    "contrarian":     re.compile(r"\b(actually|myth|wrong|opposite|contrary|but)\b", re.I),
    "demonstration":  re.compile(r"\b(watch|see|look at|here'?s what|side by side)\b", re.I),
    "instruction":    re.compile(r"^\s*(read|check|try|swap|compare|look for)\b", re.I),
}


def classify_hook_strategy(piece: dict) -> str | None:
    """How the hook is built. None when there is no hook to classify."""
    hook = " ".join(str(piece.get(k) or "") for k in
                    ("hook", "hook_text", "hook_spoken", "headline", "title")).strip()
    if not hook:
        return None
    for name, rx in _HOOK_STRATEGIES.items():
        if rx.search(hook):
            return name
    return None


# ── Payoff (ADR-002 Phase 2) ─────────────────────────────────────────────────
#
# A curiosity mechanism with nothing behind it is bait, and nothing in the
# pipeline rejected it: a strong hook passed every gate even when the viewer
# learned nothing. Payoff is what separates a hook from a headline.

_PAYOFF_KINDS = {
    "new_knowledge":     ("because", "the reason", "turns out", "what happens",
                          "this means", "which is why", "the difference"),
    "useful_test":       ("check", "read the label", "test", "try this",
                          "look for", "next time you"),
    "comparison":        ("versus", " vs ", "side by side", "compared",
                          "difference between"),
    "decision_framework":("if it", "when it", "rule of thumb", "how to choose",
                          "what to look for"),
    "practical_action":  ("swap", "switch", "stop", "start", "add", "avoid"),
    "verified_discovery":("chicory", "ingredient", "label", "freeze dried",
                          "arabica", "robusta", "additives"),
}

# Copy that opens a loop. If one of these is present, a payoff is mandatory.
_OPENS_LOOP = re.compile(
    r"\b(most people|nobody|no one|what if|why|how|the reason|turns out|"
    r"you('| a)re (making|doing) .{0,20}wrong|isn'?t|is not|secret|hidden|"
    r"before you|until you|don'?t know)\b", re.I)


def _hook_text_of(piece: dict) -> str:
    explicit = " ".join(str(piece.get(k) or "") for k in
                        ("hook", "hook_text", "hook_spoken", "hook_text_overlay",
                         "headline", "title")).strip()
    if explicit:
        return explicit
    text = str(piece.get("text") or piece.get("body") or piece.get("caption") or "").strip()
    if text:
        first_segment = text.split("\n\n")[0].split("\n")[0].strip()
        if first_segment:
            return first_segment
    return ""


def _body_text_of(piece: dict) -> str:
    """Everything that is NOT the hook — where a payoff would have to live."""
    hook = _hook_text_of(piece).lower()
    body = _copy_of(piece)
    for token in hook.split("."):
        token = token.strip()
        if token and len(token) > 8:
            body = body.replace(token, " ")
    return body.strip()


def hook_promise(piece: dict) -> str | None:
    """
    What expectation does the hook create?

    Structural, not an LLM opinion: the promise is read from the hook's own
    grammar. None when the hook makes no promise that needs settling.
    """
    hook = _hook_text_of(piece).lower()
    if not hook:
        return None
    if re.search(r"\b(most people|nobody|no one|don'?t know|secret|hidden)\b", hook):
        return "undisclosed_fact"
    if re.search(r"\b(why|the reason|because)\b", hook):
        return "explanation"
    if re.search(r"\b(how|what to|which)\b", hook):
        return "method"
    if re.search(r"\b(stop|avoid|never|don'?t)\b", hook):
        return "alternative"
    if re.search(r"\b(isn'?t|is not|wrong|myth|actually)\b", hook):
        return "correction"
    if re.search(r"\?\s*$", hook):
        return "answer"
    return None


# Which payoff kinds can legitimately settle each promise. A promise of an
# undisclosed fact is not settled by an emotional beat; a promise of an
# alternative is not settled by a comparison alone.
_PROMISE_SATISFIED_BY = {
    "undisclosed_fact": {"new_knowledge", "verified_discovery", "comparison"},
    "explanation":      {"new_knowledge", "verified_discovery", "comparison",
                         "decision_framework"},
    "method":           {"useful_test", "practical_action", "decision_framework"},
    "alternative":      {"practical_action", "useful_test", "decision_framework"},
    "correction":       {"new_knowledge", "verified_discovery", "comparison"},
    "answer":           {"new_knowledge", "verified_discovery", "comparison",
                         "decision_framework", "useful_test", "practical_action"},
}


def payoff_strength(piece: dict) -> dict:
    """
    Does the viewer receive what the hook made them expect?

    Structural chain, per the approved contract:
        hook promise -> payoff kinds that could settle it -> what the body
        actually contains -> is the promise settled?

    Deliberately NOT "every post needs a dramatic reveal". A demonstration, an
    explanation, a comparison or an actionable insight all satisfy the gate. A
    post that never opened a loop is judged only on whether it delivers
    something, not on whether it surprises.
    """
    from content_generator.core.versions import PAYOFF_GATE_VERSION

    text = _copy_of(piece)
    base = {"payoff_gate_version": PAYOFF_GATE_VERSION}
    if not text.strip():
        # payoff_present is None, not False: with no copy we did not DETERMINE
        # that a payoff is absent, we were unable to look. A False here would
        # enter the learning log as a measured finding.
        return {**base, "score": None, "kinds": [], "payoff_type": None,
                "hook_promise": None, "payoff_present": None,
                "opens_loop": None, "passes": False,
                "payoff_validation_status": "no_copy", "reason": "no copy to judge"}

    promise = hook_promise(piece)
    body = _body_text_of(piece)
    # Payoff must live in the BODY. A hook that contains its own payoff keyword
    # is still just a hook.
    kinds = [k for k, sigs in _PAYOFF_KINDS.items() if any(s in body for s in sigs)]
    opens = bool(_OPENS_LOOP.search(text))

    score = min(100.0, len(kinds) * 28.0)
    if len(body.split()) < 12:
        score -= 20
    score = max(0.0, score)

    primary = kinds[0] if kinds else None
    out = {**base, "score": score, "kinds": kinds, "payoff_type": primary,
           "hook_promise": promise, "payoff_present": bool(kinds),
           "opens_loop": opens}

    if not kinds:
        return {**out, "passes": False,
                "payoff_validation_status": "missing",
                "reason": ("opens a curiosity loop and never closes it — the viewer "
                           "learns nothing, which is the definition of bait")
                          if opens or promise else
                          "delivers no knowledge, test, comparison or action"}

    # A promise was made: check it is settled by a payoff of the right kind,
    # not merely by any payoff at all.
    if promise:
        acceptable = _PROMISE_SATISFIED_BY.get(promise, set())
        if acceptable and not (set(kinds) & acceptable):
            return {**out, "passes": False,
                    "payoff_validation_status": "mismatched",
                    "reason": (f"hook promises {promise!r} but the content delivers "
                               f"{', '.join(kinds)} — the promise is never settled")}

    return {**out, "passes": True, "payoff_validation_status": "satisfied",
            "reason": f"pays off with: {', '.join(kinds)}"}


# ── Hook decomposition (ADR-002 Phase 3) ─────────────────────────────────────

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", str(s or "").lower()).strip()


def hook_layers(piece: dict) -> dict:
    """The three hook channels a video has, and whether they are distinct."""
    on_screen = _norm(piece.get("hook_text_overlay") or piece.get("hook_text"))
    spoken    = _norm(piece.get("hook_spoken"))
    visual    = _norm(piece.get("hook_visual_concept") or piece.get("visual_hook"))
    present   = {k: v for k, v in
                 (("on_screen", on_screen), ("spoken", spoken), ("visual", visual)) if v}
    # Distinctness is undefined with fewer than two channels — None, not True.
    # Reporting True for an asset that has no hooks at all would record a
    # quality property we never actually checked.
    distinct = (len({v for v in present.values()}) == len(present)
                if len(present) >= 2 else None)
    return {"layers": present, "distinct": distinct}


def check_hook_decomposition(piece: dict) -> dict:
    """
    A reel's on-screen text, spoken line and visual should do different work.
    Repeating one sentence across all three wastes the only seconds that decide
    whether the viewer stays.

    Only enforced when at least two channels are present — an asset that simply
    has no separate spoken hook is not penalised here.
    """
    info = hook_layers(piece)
    layers = info["layers"]
    if len(layers) < 2:
        return {"passes": True, "reason": "fewer than two hook channels present"}
    if not info["distinct"]:
        dupes = [k for k in layers if list(layers.values()).count(layers[k]) > 1]
        return {"passes": False,
                "reason": f"hook channels are identical ({', '.join(sorted(dupes))}) — "
                          "on-screen, spoken and visual must each do different work"}
    return {"passes": True, "reason": "hook channels are distinct"}


def describe(piece: dict, content: dict = None, platform: str = None,
             fmt: str = None) -> dict:
    """
    The versioned decision record for one asset (ADR-002 Phase 1).

    OBSERVATIONAL ONLY. Nothing here influences frame selection, publishing
    frequency, reward, content mix or any publish decision. It exists so that
    "which attention mechanism worked" becomes answerable once real outcomes
    land — today it records a hypothesis, never a finding.

    Unavailable fields are None. They are never "default", never "" and never
    0: an unknown that looks like a value is worse than an obvious gap,
    because only the obvious gap gets fixed.
    """
    from content_generator.core.versions import DECISION_VERSION

    content = content or {}
    payoff = payoff_strength(piece)

    def _or_none(v):
        v = str(v or "").strip()
        return v or None

    return {
        "scroller_state":         classify_state(piece),
        "attention_mechanism":    classify_mechanism(piece),
        "psychology_frame":       _or_none(content.get("psychology_frame")),
        "psychology_frame_version": content.get("psychology_frame_version"),
        "hook_strategy":          classify_hook_strategy(piece),
        "payoff_type":            payoff["payoff_type"],
        "hook_promise":           payoff["hook_promise"],
        "payoff_present":         payoff["payoff_present"],
        "payoff_validation_status": payoff["payoff_validation_status"],
        "payoff_gate_version":    payoff["payoff_gate_version"],
        "platform":               _or_none(platform),
        "format":                 _or_none(fmt or piece.get("type")),
        "funnel_stage":           _or_none(piece.get("funnel_stage")
                                           or piece.get("objective")),
        "business_objective":     _or_none(piece.get("business_objective")
                                           or piece.get("primary_cta")),
        "target_kpi_at_creation": _or_none(piece.get("target_kpi_at_creation")
                                           or content.get("target_kpi_at_creation")),
        "hook_layers_distinct":   hook_layers(piece)["distinct"],
        "decision_version":       DECISION_VERSION,
        "basis": "classified from copy; mechanism SELECTION is ADR-002 Phase 4 "
                 "and is not active",
    }
