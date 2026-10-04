"""Instagram-native generation rules for discovery, retention and follower growth."""

INSTAGRAM_NATIVE_RULES = r"""
INSTAGRAM-NATIVE CREATIVE SYSTEM — mandatory:
- Never render internal labels such as "SLIDE 1", "HEADLINE", JSON keys, prompt instructions, or production notes.
- Design for a phone first. Keep essential text inside generous safe zones; no cropped words.
- Avoid repeated black-poster templates. Rotate believable environments: morning window light, café table, kitchen counter,
  ice/glass macro, coffee pour, steam, granules, packaging detail, work desk, travel/commute, creator/UGC POV.
- Brand recognition comes from product, typography discipline and subtle accents; the entire background does NOT need to be dark.
- Do not fabricate/change jar label, pack colour, logo, SKU or product claims.
- On-canvas copy: one idea. Prefer <= 8 words for Reel/Story hook and <= 12 words for carousel cover.
- Reels = discovery: 9:16, immediate visual change in first second, real motion, 3-7 purposeful shots, captions, payoff,
  loopable ending, audio plan, one CTA. Never turn a static poster into an MP4 and call it a Reel.
- Carousels = saves/shares: cover creates curiosity; each slide advances one point; visual variety; final slide gives a useful
  takeaway or one CTA. Never prefix visible copy with slide numbers.
- Stories = interaction/trust: native 9:16 frames, polls/questions/quizzes/A-B choices where applicable, demonstrations,
  behind-the-scenes and replies. Do not merely recycle feed artwork.
- Avoid repetitive anti-chicory messaging. Rotate pillars: coffee education, sensory/ASMR, recipes, relatable culture,
  myth/curiosity, product proof, comparisons, founder/BTS, UGC/POV, seasonal moments.
- No engagement bait, bots, follow/unfollow, pods or mass unsolicited DMs.

---

## FACELESS CONTENT PRODUCTION SYSTEM (Prompt 3 Rules)
If generating reels or carousels, apply these faceless content principles:
1. **7-Slide Carousel Format**:
   - Slide 1: Cover Hook (6 words max, intense pattern interrupt)
   - Slide 2: The Problem (relatable coffee frustration, no statistics)
   - Slide 3: Myth Busted (surprising/contrarian twist)
   - Slide 4: The Revelation (the hidden truth revealed)
   - Slide 5: Why It Matters (Indian consumer scenario/relevance)
   - Slide 6: Purity Beans Difference (100% coffee jars named; Ultra Blend called 70% coffee; how to buy)
   - Slide 7: Branded Share/Comment Trigger (direct save/comment incentive + website URL)
2. **Text-Only Reel Scripts**:
   - Scene-by-scene script writing. For every scene/time-slot, write exact voiceover text, on-screen text overlays, and detailed visual directions (e.g. macro camera panning, steam rising, pouring coffee, hands grinding beans) to make it highly visual without needing to show a face or use generic stock media.
"""

def get_instagram_native_rules():
    return INSTAGRAM_NATIVE_RULES
