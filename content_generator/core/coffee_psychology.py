"""
Coffee Marketing Psychology — single source of truth for Purity Beans content.

Why this exists:
  Generic "premium coffee" language produces advertisements. People do not share
  advertisements. The content that travels is the thing someone sends a friend —
  the revelation, the label test, the sensory difference after years of filler.

  These frames are ranked by fit for a pure-instant brand in India. Every
  generation prompt should pick one (or a clean combination) rather than invent
  a new angle from scratch.

Evidence base (condensed):
  - Ritual communication raises willingness-to-pay (Intellect 2023).
  - Revelation / cognitive dissonance is the strongest pure-coffee lever in India
    (chicory normalised for decades; FSSAI front-of-pack rules make it timely).
  - Clean-label self-signaling is rising among urban 25-40s who already read
    ingredient panels on other categories.
  - Social currency ("3 signs...", "look at the label") drives saves + shares more
    reliably than product shots.
  - Accessible premium (café quality at home price) resolves the price-sensitivity
    paradox without status anxiety.
"""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

# ── Primary frames (ordered by leverage for this brand) ───────────────────────

PSYCHOLOGY_FRAMES = [
    {
        "id": "revelation",
        "name": "Revelation / Cognitive Dissonance",
        "risk_level": "medium",
        "theory": {
            "core": "You have been drinking something that is not what you thought it was.",
            "why_it_works": (
                "Creates immediate dissonance. The viewer must either defend the old "
                "habit or update it. Either response is engagement."
            )
        },
        "creative_application": {
            "example_hooks": [
                "You have been drinking chicory your entire life.",
                "Most people do not know their daily coffee has filler.",
                "What is actually inside your coffee jar?"
            ],
            "best_formats": ["reel", "carousel"],
            "share_trigger": "Tag the person who still buys the big brand without reading the label."
        },
        "governance": {
            "allowed_claims": ["100% coffee on Bold, Purista, Purica, and Prima", "zero chicory on those jars", "Ultra Blend is 70% coffee"],
            "prohibited_claims": ["competitors are toxic", "chicory causes diseases", "fabricated percentages"]
        }
    },
    {
        "id": "clean_label",
        "name": "Clean-Label Self-Signaling",
        "risk_level": "low",
        "theory": {
            "core": "Reading the label is an act of self-respect, not paranoia.",
            "why_it_works": (
                "Turns a low-effort behaviour (looking at the back of the pack) into "
                "an identity signal. The person who checks becomes the informed one."
            )
        },
        "creative_application": {
            "example_hooks": [
                "3 signs your coffee is not pure.",
                "How to read a coffee label in 15 seconds.",
                "The ingredient most brands hope you never notice."
            ],
            "best_formats": ["carousel", "reel"],
            "share_trigger": "Save this before your next grocery run."
        },
        "governance": {
            "allowed_claims": ["Purity Beans ingredients: 100% coffee", "read the back ingredient panel"],
            "prohibited_claims": ["other food products are poisoned", "unverified FSSAI violations"]
        }
    },
    {
        "id": "ritual",
        "name": "Ritual Elevation",
        "risk_level": "low",
        "theory": {
            "core": "The morning cup is not caffeine delivery. It is the first decision of the day.",
            "why_it_works": (
                "Rituals increase enjoyment and willingness to pay. Framing the daily "
                "cup as identity ('I choose pure') makes switching feel like an upgrade "
                "to the self, not just the product."
            )
        },
        "creative_application": {
            "example_hooks": [
                "Your morning coffee is the first decision you make about yourself.",
                "Start the day with something that is actually coffee.",
                "The 2-minute ritual that changes the rest of the day."
            ],
            "best_formats": ["reel", "story"],
            "share_trigger": "Send this to someone who still starts the day on autopilot."
        },
        "governance": {
            "allowed_claims": ["pure coffee ritual", "100% coffee ingredients", "premium morning routine"],
            "prohibited_claims": ["instant coffee cures drowsiness forever", "medical sleep cures"]
        }
    },
    {
        "id": "sensory",
        "name": "Sensory Contrast",
        "risk_level": "low",
        "theory": {
            "core": "Once you taste real coffee, the filler version becomes obvious.",
            "why_it_works": (
                "Sensory memory is sticky. Describing the exact moment the taste "
                "changes (bitterness at minute two, muddy aftertaste, missing aroma) "
                "gives the viewer a private test they can run tomorrow morning."
            )
        },
        "creative_application": {
            "example_hooks": [
                "It tastes bitter after two minutes. That is not normal.",
                "Real coffee does not leave a muddy aftertaste.",
                "The first sip that finally tastes like coffee."
            ],
            "best_formats": ["reel", "carousel"],
            "share_trigger": "Share with the person who always says 'coffee just tastes bitter'."
        },
        "governance": {
            "allowed_claims": ["chicory alters flavor and aroma", "pure coffee is naturally aromatic", "bitter muddy aftertaste in fillers"],
            "prohibited_claims": ["pure coffee is sweet without sugar", "sensory preferences are absolute medical health signals"]
        }
    },
    {
        "id": "social_currency",
        "name": "Social Currency / Shareable Discovery",
        "risk_level": "medium",
        "theory": {
            "core": "This is information that makes the sharer look informed.",
            "why_it_works": (
                "People share content that improves their status inside their circle. "
                "'3 signs...', 'look at the label', 'what the ingredient panel actually "
                "says' are high-status discoveries. Product shots are not."
            )
        },
        "creative_application": {
            "example_hooks": [
                "Show this to anyone who still buys the big jar without checking.",
                "The one line on the label that changes everything.",
                "What every coffee lover in your office needs to see."
            ],
            "best_formats": ["carousel", "reel"],
            "share_trigger": "Forward this to the friend who buys coffee for the whole office."
        },
        "governance": {
            "allowed_claims": ["shareable coffee facts", "reading ingredient lists", "identifying fillers"],
            "prohibited_claims": ["anyone drinking chicory is stupid", "unverified status shaming"]
        }
    },
    {
        "id": "accessible_premium",
        "name": "Accessible Premium",
        "risk_level": "low",
        "theory": {
            "core": "Café quality without café price or café effort.",
            "why_it_works": (
                "Resolves the price-sensitivity paradox. Urban Indians will pay for "
                "quality when friction is removed. Instant + pure + Rs 18/cup is the "
                "sweet spot — premium feeling, everyday accessible."
            )
        },
        "creative_application": {
            "example_hooks": [
                "Rs 18. Same purity the café charges Rs 180 for.",
                "Real coffee does not require a machine or a weekend.",
                "Premium is not the price. Premium is what is missing from the jar."
            ],
            "best_formats": ["reel", "carousel", "story"],
            "share_trigger": "Send this to anyone who thinks pure coffee has to be expensive."
        },
        "governance": {
            "allowed_claims": ["Rs 18 per cup serving cost", "cafe coffee often costs Rs 180+", "Purica is freeze-dried 100% Arabica"],
            "prohibited_claims": ["cafe coffee is unhealthy", "unverified price calculations"]
        }
    },
    {
        "id": "certainty",
        "name": "Loss Aversion / Certainty",
        "risk_level": "medium",
        "theory": {
            "core": "Knowing exactly what is in the cup removes a quiet daily uncertainty.",
            "why_it_works": (
                "Premium choice is often rational uncertainty management, not status. "
                "'I know what I am drinking' is a stronger closer than 'this is better'."
            )
        },
        "creative_application": {
            "example_hooks": [
                "The only claim that matters: nothing is hiding in this jar.",
                "You should not need a chemistry degree to trust your coffee.",
                "Bold, Purista, Purica, and Prima are 100% coffee. Ultra Blend is 70% coffee. Written so you can verify it."
            ],
            "best_formats": ["carousel", "reel"],
            "share_trigger": "Save this if you are tired of guessing what is in your cup."
        },
        "governance": {
            "allowed_claims": ["clear labeling", "100% coffee on Bold, Purista, Purica, and Prima", "Ultra Blend is 70% coffee"],
            "prohibited_claims": ["non-labeled foods cause cancer", "other coffee brands are illegal or toxic"]
        }
    }
]

# Fast lookup
FRAMES_BY_ID = {f["id"]: f for f in PSYCHOLOGY_FRAMES}


def get_frame(frame_id: str) -> dict | None:
    return FRAMES_BY_ID.get(frame_id)


def frame_prompt_block() -> str:
    """
    Compact block injected into generation prompts.
    Forces the model to pick one primary frame instead of inventing angles.
    """
    lines = [
        "PSYCHOLOGY FRAMES (pick ONE primary frame for this asset — do not invent a new one):",
    ]
    for f in PSYCHOLOGY_FRAMES:
        lines.append(
            f"  [{f['id']}] {f['name']} (Risk Level: {f['risk_level'].upper()}):"
        )
        lines.append(
            f"    Core Theory: {f['theory']['core']}"
        )
        lines.append(
            f"    Why it works: {f['theory']['why_it_works']}"
        )
        lines.append(
            f"    Allowed Sourcing Claims: {', '.join(f['governance']['allowed_claims'])}"
        )
        lines.append(
            f"    Prohibited Unverified Claims: {', '.join(f['governance']['prohibited_claims'])}"
        )
        lines.append("")
    lines.append(
        "MANDATORY GOVERNANCE RULE: The chosen psychological mechanism must never override truthfulness. "
        "Verified facts and brand policies always supersede psychological triggers. Do not fabricate "
        "statistics or competitor claims to increase shock value. "
        "The chosen frame must shape the hook, the emotional arc, and the share/save trigger."
    )
    return "\n".join(lines)


def recommended_frame_for_format(fmt: str) -> list[str]:
    """Return frame ids that historically fit a given format."""
    fmt = (fmt or "").lower()
    out = []
    for f in PSYCHOLOGY_FRAMES:
        if fmt in f["creative_application"]["best_formats"]:
            out.append(f["id"])
    return out or [f["id"] for f in PSYCHOLOGY_FRAMES]


def validate_registry() -> bool:
    """
    Validate all psychology frames against the strict schema.
    Returns True if valid, raises ValueError on any violation.
    """
    seen_ids = set()
    valid_risk_levels = {"low", "medium", "high"}
    
    for f in PSYCHOLOGY_FRAMES:
        # Check required root keys
        for key in ("id", "name", "risk_level", "theory", "creative_application", "governance"):
            if key not in f:
                raise ValueError(f"Psychology frame missing required root key: '{key}' in frame: {f.get('id', 'unknown')}")
        
        # Duplicate ID check
        f_id = f["id"]
        if not isinstance(f_id, str) or not f_id:
            raise ValueError(f"Invalid frame ID: {f_id}")
        if f_id in seen_ids:
            raise ValueError(f"Duplicate psychology frame ID detected: '{f_id}'")
        seen_ids.add(f_id)
        
        # Validate risk level
        risk = f["risk_level"]
        if risk not in valid_risk_levels:
            raise ValueError(f"Invalid risk_level '{risk}' in frame '{f_id}'. Must be one of {valid_risk_levels}")
            
        # Validate theory block
        theory = f["theory"]
        if not isinstance(theory, dict):
            raise ValueError(f"theory must be a dict in frame '{f_id}'")
        for key in ("core", "why_it_works"):
            if key not in theory or not isinstance(theory[key], str) or not theory[key].strip():
                raise ValueError(f"theory block missing or has empty key '{key}' in frame '{f_id}'")
                
        # Validate creative application block
        creative = f["creative_application"]
        if not isinstance(creative, dict):
            raise ValueError(f"creative_application must be a dict in frame '{f_id}'")
        for key in ("example_hooks", "share_trigger", "best_formats"):
            if key not in creative:
                raise ValueError(f"creative_application missing key '{key}' in frame '{f_id}'")
        
        if not isinstance(creative["example_hooks"], list) or not all(isinstance(x, str) for x in creative["example_hooks"]):
            raise ValueError(f"example_hooks must be a list of strings in frame '{f_id}'")
            
        if not isinstance(creative["share_trigger"], str) or not creative["share_trigger"].strip():
            raise ValueError(f"share_trigger must be a non-empty string in frame '{f_id}'")
            
        if not isinstance(creative["best_formats"], list) or not all(isinstance(x, str) for x in creative["best_formats"]):
            raise ValueError(f"best_formats must be a list of strings in frame '{f_id}'")

        # Validate governance block
        gov = f["governance"]
        if not isinstance(gov, dict):
            raise ValueError(f"governance must be a dict in frame '{f_id}'")
        for key in ("allowed_claims", "prohibited_claims"):
            if key not in gov:
                raise ValueError(f"governance missing key '{key}' in frame '{f_id}'")
            if not isinstance(gov[key], list) or not all(isinstance(x, str) for x in gov[key]):
                raise ValueError(f"{key} must be a list of strings in frame '{f_id}'")
                
    logger.info("[psychology] All %d psychology frames verified successfully against the strict registry schema.", len(PSYCHOLOGY_FRAMES))
    return True


# Run schema and duplicate validation at import/startup time
validate_registry()
