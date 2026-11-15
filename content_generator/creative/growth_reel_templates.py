"""Growth-reel template fast_cut_curiosity.

The structure comes from a public reference reel. Pixels, audio, script,
on-screen words, and the reference keyword are not copied. Measured views
and follower counts for our own posts stay in the learning log; the
reference reel's like and comment counts are not our results.

Rendered length is 34 seconds: inside the 30-40 second target, and inside
the existing discovery gate that rejects a reel longer than 35 seconds.
"""
from __future__ import annotations

TEMPLATE_ID = "fast_cut_curiosity"
DURATION_S = 34
KEYWORD = "CUP"
ACCENT_HEX = "#C8962E"
STORE = "https://p3online.in/"

# Spoken and caption lines we are willing to publish. The ban list in the
# prompt names phrases the model must not write; these lines are the ones
# that actually ship if the model leaves the CTA blank.
SPOKEN = {
    "curiosity": "Watch what the spoon does next.",
    "cta": f"Comment {KEYWORD} and I'll send you the link.",
}

REFERENCE_LIBRARY = (
    {
        "id": "ig:lenabrooks.ai:Db5TJjviR08",
        "handle": "lenabrooks.ai",
        "url": "https://www.instagram.com/reel/Db5TJjviR08/",
        "width": 1080,
        "height": 1920,
        "duration_s": 37,
        "observed_likes": 1572,
        "observed_comments": 4022,
        "publish_source_video": False,
        "copied": {
            "pixels": False,
            "audio": False,
            "script": False,
            "captions": False,
            "keyword": False,
        },
        "not_a_performance_sample": True,
        "structure_notes": (
            "0-3s hook: split screen. Top is a macro action such as a spoon scoop or a hot-water pour. Bottom is the real jar. A curiosity line is spoken and captioned in the first second.",
            "Hard cut every 1-3 seconds. No crossfades. Every shot has a slow digital punch-in so the frame never sits still.",
            "Word-by-word captions: big bold sans-serif, white with a drop shadow, one gold accent on the key word, lower-middle, inside the safe area.",
            "Voice leads. A quiet lo-fi bed sits under it. No dead air.",
            "Teach the point first. The comment-keyword ask is only in the last three seconds.",
            "Target length is 30-40 seconds. This account renders 34 so the existing 35-second discovery gate still holds.",
        ),
    },
)


def store_link(content: str = "cup") -> str:
    """Comment-reply URL. Prices are not encoded here."""
    campaign = TEMPLATE_ID
    token = "".join(ch for ch in str(content or "cup").lower() if ch.isalnum()) or "cup"
    return (
        f"{STORE}?utm_source=instagram&utm_medium=growth_reel"
        f"&utm_campaign={campaign}&utm_content={token}"
    )


def reference_entry() -> dict:
    entry = dict(REFERENCE_LIBRARY[0])
    entry["copied"] = dict(entry["copied"])
    entry["structure_notes"] = tuple(entry["structure_notes"])
    return entry


def prompt_block() -> str:
    """Structure instructions. Does not include the reference script."""
    ref = REFERENCE_LIBRARY[0]
    notes = "\n".join(f"- {line}" for line in ref["structure_notes"])
    link = store_link(KEYWORD.lower())
    return f"""FAST CUT CURIOSITY (growth_reel template {TEMPLATE_ID}):
Set growth_template_id to {TEMPLATE_ID} and duration_seconds to {DURATION_S}.
Borrow only the structure notes below. Do not copy the reference reel's topic, script, captions, audio, or keyword.
Reference id {ref['id']} is a structure sample. Its public like and comment counts are not our views and not our follower change.
{notes}
OPENING: seconds 0-3 are a split screen. Top: macro spoon scoop or hot-water pour, generated only as non-product b-roll. Bottom: one real photographed jar. Never draw, restyle, or invent a jar, label, or package.
FIRST SECOND: speak and caption "{SPOKEN['curiosity']}" or another concrete curiosity line in the same spirit.
PACING: hard cuts only, a new shot every 1 to 3 seconds, slow punch-in on every shot, 1080x1920, {DURATION_S} seconds total.
CAPTIONS: one word at a time, bold sans-serif, white with a drop shadow, accent {ACCENT_HEX} on the key word, lower-middle, at least 80px from each side and above the bottom 220px.
AUDIO: spoken voice is primary. A quiet lo-fi bed plays under it from the first frame to the last. No dead air.
COPY: teach one coffee-craft point before any ask. The only ask is the last 3 seconds: "{SPOKEN['cta']}"
The link you send after that comment is {link}
Do not speak a price. If a price is required, read it from the live Shopify catalog.
Ultra Blend is 70% coffee and 30% chicory. Do not call that jar a coffee-only jar.
Freeze-dried names Purica and Purista only. Agglomerated names Bold and Prima only.
Do not write a health claim, a fake deadline, a hidden offer, or a giveaway sample.
Do not claim a cafe is hiding a method, and do not cross out a machine or another brand.
Do not use a purity percentage, a just-opened wording, a laboratory claim, an acid-free claim, or an origin the jar does not print.
The opening split may show the real jar photo. That replaces the no-jar line for this format only. The spoken ask still waits until the last three seconds.
"""


def stamp(piece: dict) -> dict:
    """Attach template metadata. Does not rewrite the model's caption or hook."""
    if not isinstance(piece, dict):
        return piece
    piece["growth_template_id"] = TEMPLATE_ID
    piece["template_id"] = TEMPLATE_ID
    piece["duration_seconds"] = DURATION_S
    piece["reply_link"] = store_link(KEYWORD.lower())
    piece["comment_keyword"] = KEYWORD
    piece["comment_trigger"] = SPOKEN["cta"]
    piece.setdefault("sound_suggestion", "Spoken voice leads. Quiet lo-fi bed underneath. No dead air.")
    piece.setdefault("loop_note", "The last frame cuts back to the opening split.")
    piece["reference_structure_id"] = REFERENCE_LIBRARY[0]["id"]
    piece["reference_copied"] = dict(REFERENCE_LIBRARY[0]["copied"])
    return piece
