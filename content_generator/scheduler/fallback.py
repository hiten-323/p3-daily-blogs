"""
Emergency fallback — the engine never misses a day.

When all three LLM providers fail (Gemini + Groq + OpenRouter), the
pipeline would normally crash and produce nothing. This module catches
that scenario and generates a reduced but valid content set from:

  1. Yesterday's strategy (same objective, proven hooks)
  2. Last week's best-performing content (remixed, not copied)
  3. Pre-baked evergreen templates (guaranteed safe fallback)

The founder receives a WhatsApp alert so they know the AI didn't run
at full capacity — but the social queue never goes dark.

Priority cascade:
  yesterday's snapshot → last week's best → evergreen templates

Usage (called automatically by daily.py):
    from content_generator.scheduler.fallback import emergency_content_set
    content = emergency_content_set(day_number=42)
"""
from __future__ import annotations
import logging
import random

logger = logging.getLogger(__name__)


# ── Evergreen templates — always available, never stale ──────────────────────
# These are proven Purity Beans content patterns that work any day of the year.

# EVERY live truthfulness incident traced back to this file.
#
# The previous templates hardcoded, verbatim:
#   "Most people don't know their daily coffee has 40% chicory filler."
#       -> the fabricated statistic that published to the grid
#   "Try your first cup free. Link in bio."
#       -> an offer that has never existed
#   "Slide 1: It tastes bitter after 2 minutes"
#       -> the scaffolding leak that rendered into carousel images
#   "India spends Rs 6,000 crore...", "grew 34% YoY", "India's first"
#       -> unsourced market statistics and an unsubstantiated superlative
#
# None of it came from the LLM. The engine falls back here whenever generation
# fails, so the scrubbers, claim verifier and gates built downstream were all
# catching a defect that shipped with the fallback itself. Fallback content is
# published unattended on the worst days — it must be the SAFEST content in the
# repo, not the least reviewed.
#
# Rules for anything added here:
#   - only facts verifiable from our own label (see claim_verifier.VERIFIED_FACTS)
#   - no claims about what any other brand contains
#   - no market statistics, no superlatives, no offers
#   - no "Slide N:" / "Frame N:" scaffolding in viewer-facing copy
#   - must satisfy the schema, or the publish gate silently drops it
# tests/test_fallback_safety.py enforces all of the above.

_EVERGREEN: list[dict] = [
    {
        "type":      "reel",
        "hook":      "Turn the jar around before you buy it.",
        "hook_text": "Turn the jar around before you buy it.",
        "hook_spoken": "The front of the pack is marketing. The back is the recipe.",
        "hook_text_overlay": "READ THE BACK",
        "frames": [
            {"on_screen": "READ THE BACK",
             "spoken": "The front of the pack is marketing. The back is the recipe."},
            {"on_screen": "INGREDIENTS",
             "spoken": "Find the ingredient list. Read every line, not just the first."},
            {"on_screen": "WHAT'S IN OURS",
             "spoken": "Purity Beans lists one thing: coffee. Zero chicory, nothing added."},
            {"on_screen": "ONE LINE",
             "spoken": "Coffee needs one ingredient. Anything else is worth knowing about."},
            {"on_screen": "YOUR TURN",
             "spoken": "Check the jar in your kitchen tonight and see what it says."},
        ],
        "body":    "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": ("The front of a coffee pack is marketing. The back is the recipe.\n\n"
                    "Purity Beans — Bold, Purista, Purica, and Prima list one ingredient: coffee, with zero chicory. Ultra Blend is 70% coffee.\n\n"
                    "Check the jar in your kitchen tonight.\n\np3online.in"),
        "cta":     "Read the label, then shop at p3online.in",
        "comment_trigger": "What does the label on your jar actually say?",
        "save_trigger":    "Save this for your next grocery run.",
        "share_trigger":   "Send this to whoever buys the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio":   "Quiet kitchen ambience, no music bed — the spoken line carries it.",
        "loop_ending": "Ends on the jar being turned around, which is where it opens — the last frame reads as the first.",
        "angle":   "EXPOSE",
        "source":  "evergreen_template",
    },
    {
        "type":  "carousel",
        "hook":  "Three things to check on a coffee label",
        "title": "Three things to check on a coffee label",
        "slides": [
            {"slide": 1, "heading": "Read the ingredient list",
             "body": "It is on the back, usually in the smallest type on the pack.",
             "visual": "Close-up of an ingredient panel, jar turned to camera"},
            {"slide": 2, "heading": "Count the ingredients",
             "body": "Coffee needs one. Anything else is there for a reason worth knowing.",
             "visual": "Finger tracing down a short ingredient list"},
            {"slide": 3, "heading": "Look for chicory by name",
             "body": "It is a root, not a bean, and it is listed when present.",
             "visual": "Ingredient panel with the word chicory in frame"},
            {"slide": 4, "heading": "Check the order",
             "body": "Ingredients are listed by weight, so the first one is the bulk of it.",
             "visual": "Ingredient panel with the first line highlighted"},
            {"slide": 5, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
             "visual": "Purity Beans jar, label facing camera"},
            # The schema requires the website on the final slide — the carousel
            # is the one format where the CTA lives in the image, not the caption.
            {"slide": 6, "heading": "Do it tonight",
             "body": "Turn around the jar in your kitchen and read the list. "
                     "Purity Beans — p3online.in",
             "visual": "Hand turning a jar on a kitchen counter"},
        ],
        "caption": ("Three things worth checking on any coffee label.\n\n"
                    "Purity Beans — Bold, Purista, Purica, and Prima list one ingredient: coffee. Ultra Blend is 70% coffee.\n\n"
                    "Zero chicory, no additives.\n\np3online.in"),
        "cta":     "Shop pure coffee at p3online.in",
        "comment_trigger": "Which of the three surprised you?",
        "save_trigger":    "Save this for your next grocery run.",
        "share_trigger":   "Share with someone who drinks instant daily.",
        "hashtags": "#PurityBeans #PureCoffee #ZeroChicory #CoffeeIndia #ReadTheLabel",
        "source":  "evergreen_template",
    },
    {
        "type":    "instagram_post",
        "hook":    "Read the jar. The list is the product.",
        "body":    "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": ("Read the jar. The list is the product.\n\n"
                    "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. "
                    "Ultra Blend is 70% coffee.\n\nTurn your jar around and compare.\n\np3online.in"),
        "cta":     "Shop at p3online.in",
        "comment_trigger": "How many ingredients are on your jar?",
        "save_trigger":    "Save this for your next grocery run.",
        "share_trigger":   "Send this to a fellow coffee drinker.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeLover",
        "source":  "evergreen_template",
    },
    {
        "type": "linkedin_post",
        "hook": "We built a coffee brand around a shorter ingredient list",
        "body": (
            "Instant coffee in India is a category where the ingredient list is "
            "the most informative thing on the pack, and the least read.\n\n"
            "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. "
            "Ultra Blend is 70% coffee.\n\n"
            "That constraint decides sourcing, cost and shelf positioning — it is "
            "a harder product to make and an easier one to explain.\n\n"
            "For distributors and retailers interested in stocking it, my DMs are open.\n\n"
            "p3online.in"
        ),
        "cta": "Distributor and retailer enquiries welcome in DMs",
        "hashtags": "#Coffee #FMCG #IndianBrands #Distribution #PurityBeans",
        "source": "evergreen_template",
    },
    # ── Set 2 — count the ingredients ─────────────────────────────────────────
    {
        "type": "reel",
        "hook": "Instant coffee should have a very short ingredient list.",
        "hook_text": "Instant coffee should have a very short ingredient list.",
        "hook_spoken": "Pick up any jar of instant coffee and count the lines.",
        "hook_text_overlay": "COUNT THE LINES",
        "frames": [
            {"on_screen": "COUNT THE LINES",
             "spoken": "Pick up any jar of instant coffee and count the ingredients."},
            {"on_screen": "ONE IS ENOUGH",
             "spoken": "Coffee needs one ingredient to be coffee. That is the whole list."},
            {"on_screen": "ANYTHING ELSE",
             "spoken": "Everything after the first line is there for a reason. Worth knowing which."},
            {"on_screen": "WHAT OURS SAYS",
             "spoken": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee."},
            {"on_screen": "GO COUNT",
             "spoken": "Go count the lines on the jar in your kitchen right now."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Count the ingredients on your instant coffee.\n\nCoffee needs one. Purity Beans lists one: coffee.\n\nCheck the jar in your kitchen tonight.\n\np3online.in",
        "cta": "Count yours, then shop at p3online.in",
        "comment_trigger": "How many ingredients does your jar list?",
        "save_trigger": "Save this before your next grocery run.",
        "share_trigger": "Send this to whoever buys the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the jar being picked up, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "What 100% coffee actually means",
        "title": "What 100% coffee actually means",
        "slides": [
            {"slide": 1, "heading": "It is a claim about the list",
             "body": "It means the ingredient list has coffee on it and nothing else.",
             "visual": "Ingredient panel filling the frame"},
            {"slide": 2, "heading": "Not a claim about strength",
             "body": "Strength comes from how much you use and how you brew it.",
             "visual": "Spoon of coffee held over a cup"},
            {"slide": 3, "heading": "Not a claim about roast",
             "body": "Roast changes flavour. It does not change what is in the jar.",
             "visual": "Two jars side by side on a counter"},
            {"slide": 4, "heading": "Read it as a list, not a slogan",
             "body": "The front of a pack is designed. The back is declared.",
             "visual": "Jar being turned from front to back"},
            {"slide": 5, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
             "visual": "Purity Beans jar, label facing camera"},
            {"slide": 6, "heading": "Check yours tonight",
             "body": "Turn the jar around and read the list. Purity Beans - p3online.in",
             "visual": "Hand turning a jar on a kitchen counter"},
        ],
        "caption": "100% coffee is a claim about the ingredient list, not about strength or roast.\n\nPurity Beans — Bold, Purista, Purica, and Prima list one ingredient: coffee. Ultra Blend is 70% coffee.\n\nCheck the jar in your kitchen tonight.\n\np3online.in",
        "cta": "Read your label, then shop at p3online.in",
        "comment_trigger": "What does your jar list after the first line?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever buys the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Ingredients are listed by weight, so the first line is most of the jar.",
        "body": "That is why the order matters as much as the list. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Ingredients are listed by weight, so the first line is most of what you are buying.\n\nThe order tells you as much as the list does.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Read the label, then shop at p3online.in",
        "comment_trigger": "What is the first ingredient on your jar?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever buys the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 3 — chicory, explained plainly ────────────────────────────────────
    {
        "type": "reel",
        "hook": "Chicory is a root, not a coffee bean.",
        "hook_text": "Chicory is a root, not a coffee bean.",
        "hook_spoken": "Chicory is a root. Roasted and ground, it looks a lot like coffee.",
        "hook_text_overlay": "ROOT, NOT BEAN",
        "frames": [
            {"on_screen": "ROOT, NOT BEAN",
             "spoken": "Chicory is a root. Roasted and ground, it looks a lot like coffee."},
            {"on_screen": "IT IS DECLARED",
             "spoken": "When it is in the jar, it is named on the ingredient list."},
            {"on_screen": "FIVE SECONDS",
             "spoken": "Which means you can find out by turning the jar around."},
            {"on_screen": "WHAT OURS SAYS",
             "spoken": "Purity Beans — Bold, Purista, Purica, and Prima list coffee and nothing else, with zero chicory. Ultra Blend is 70% coffee."},
            {"on_screen": "CHECK YOURS",
             "spoken": "Turn your jar around tonight and look for the word."},
        ],
        "body": "Chicory is a roasted root. It is declared on the label when present. Purity Beans — Bold, Purista, Purica, and Prima list coffee only.",
        "caption": "Chicory is a root, not a bean. Roasted and ground, it looks like coffee.\n\nWhen it is in a jar it is named on the label, so you can check in seconds.\n\nPurity Beans — Bold, Purista, Purica, and Prima list coffee, with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Check your label, then shop at p3online.in",
        "comment_trigger": "Does the word chicory appear on your jar?",
        "save_trigger": "Save this so you remember what to look for.",
        "share_trigger": "Send this to someone who has never read their coffee label.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the jar turning, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Chicory, explained without the drama",
        "title": "Chicory, explained without the drama",
        "slides": [
            {"slide": 1, "heading": "It is a root",
             "body": "Chicory is a plant root, not a coffee bean.",
             "visual": "Chicory root beside coffee beans on a board"},
            {"slide": 2, "heading": "It is roasted and ground",
             "body": "Processed that way, it looks very similar to ground coffee.",
             "visual": "Two dark grounds side by side in bowls"},
            {"slide": 3, "heading": "It carries its own taste",
             "body": "It is more bitter and a little woody next to coffee.",
             "visual": "Two cups poured side by side"},
            {"slide": 4, "heading": "It is always declared",
             "body": "If it is in the jar, it is named on the ingredient list.",
             "visual": "Ingredient panel with a finger pointing at a line"},
            {"slide": 5, "heading": "So you can simply check",
             "body": "Turning the jar around answers the question in seconds.",
             "visual": "Hand rotating a jar to the back label"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima list coffee, with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Chicory is a root, not a bean. Roasted and ground it looks like coffee, and it is always named on the label when present.\n\nPurity Beans — Bold, Purista, Purica, and Prima list coffee, with zero chicory. Ultra Blend is 70% coffee.\n\nCheck the jar in your kitchen tonight.\n\np3online.in",
        "cta": "Check your label, then shop at p3online.in",
        "comment_trigger": "Does the word chicory appear on your jar?",
        "save_trigger": "Save this so you know what to look for.",
        "share_trigger": "Send this to someone who has never checked.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Chicory is a root, not a coffee bean.",
        "body": "Roasted and ground it looks like coffee, and it is named on the ingredient list whenever it is in the jar. Purity Beans — Bold, Purista, Purica, and Prima list coffee, with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Chicory is a root, not a bean.\n\nRoasted and ground it looks like coffee - and it is always named on the label when it is there.\n\nPurity Beans — Bold, Purista, Purica, and Prima list coffee, with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Check your label, then shop at p3online.in",
        "comment_trigger": "Does the word chicory appear on your jar?",
        "save_trigger": "Save this so you remember what to look for.",
        "share_trigger": "Send this to someone who has never read their label.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    # ── Set 4 — how to keep it tasting like it should ─────────────────────────
    {
        "type": "reel",
        "hook": "Most instant coffee goes stale in the jar, not in the shop.",
        "hook_text": "Most instant coffee goes stale in the jar, not in the shop.",
        "hook_spoken": "The jar on your counter is doing more damage than the shelf ever did.",
        "hook_text_overlay": "SEAL IT",
        "frames": [
            {"on_screen": "SEAL IT",
             "spoken": "The jar on your counter is doing more damage than the shelf ever did."},
            {"on_screen": "AIR",
             "spoken": "Every time it stays open, moisture gets in and aroma gets out."},
            {"on_screen": "HEAT",
             "spoken": "Above the stove is the warmest shelf in the kitchen. Move it."},
            {"on_screen": "DRY SPOON",
             "spoken": "A wet spoon clumps the whole jar. Keep one spoon dry, just for coffee."},
            {"on_screen": "TONIGHT",
             "spoken": "Close it tight, move it off the stove, and taste the difference this week."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Instant coffee usually goes stale in the jar, not in the shop.\n\nClose it tight, keep it off the stove, use a dry spoon.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Store it right, then restock at p3online.in",
        "comment_trigger": "Where does the coffee jar live in your kitchen?",
        "save_trigger": "Save this and move your jar tonight.",
        "share_trigger": "Send this to whoever leaves the lid off.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the lid closing, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Four things that stale your coffee at home",
        "title": "Four things that stale your coffee at home",
        "slides": [
            {"slide": 1, "heading": "An open lid",
             "body": "Aroma leaves the moment the jar is open. Close it between cups.",
             "visual": "Open jar on a counter, lid beside it"},
            {"slide": 2, "heading": "A wet spoon",
             "body": "Moisture clumps what it touches and the clumps spread.",
             "visual": "Damp spoon going into a jar"},
            {"slide": 3, "heading": "The shelf above the stove",
             "body": "It is the warmest place in the kitchen. Pick a cooler one.",
             "visual": "Jar on a shelf directly above a hob"},
            {"slide": 4, "heading": "Sunlight on the counter",
             "body": "Light and warmth together age it faster than either alone.",
             "visual": "Jar in a bright window"},
            {"slide": 5, "heading": "Fix all four tonight",
             "body": "Lid closed, dry spoon, cool shelf, out of the sun.",
             "visual": "Jar being moved into a closed cupboard"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Four things stale your coffee at home: an open lid, a wet spoon, the shelf above the stove, and direct sun.\n\nAll four are free to fix tonight.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Store it right, then restock at p3online.in",
        "comment_trigger": "Which of the four is happening in your kitchen?",
        "save_trigger": "Save this and fix one tonight.",
        "share_trigger": "Send this to whoever leaves the lid off.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "A wet spoon will clump a whole jar of instant coffee.",
        "body": "Keep one dry spoon for coffee, close the lid between cups, and keep the jar off the shelf above the stove. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "A wet spoon will clump a whole jar.\n\nOne dry spoon, lid closed between cups, and keep it off the shelf above the stove.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Store it right, then restock at p3online.in",
        "comment_trigger": "Where does your coffee jar live?",
        "save_trigger": "Save this and move your jar tonight.",
        "share_trigger": "Send this to whoever leaves the lid off.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 5 — freeze dried, explained ───────────────────────────────────────
    {
        "type": "reel",
        "hook": "Freeze dried and spray dried are not the same thing.",
        "hook_text": "Freeze dried and spray dried are not the same thing.",
        "hook_spoken": "Two jars can both say instant coffee and be made completely differently.",
        "hook_text_overlay": "TWO METHODS",
        "frames": [
            {"on_screen": "TWO METHODS",
             "spoken": "Two jars can both say instant coffee and be made completely differently."},
            {"on_screen": "SPRAY DRIED",
             "spoken": "Spray drying uses hot air. It is fast, and heat costs aroma."},
            {"on_screen": "FREEZE DRIED",
             "spoken": "Freeze drying works cold, so more of the aroma survives the process."},
            {"on_screen": "LOOK AT IT",
             "spoken": "Freeze dried looks like crystals. Spray dried looks like fine powder."},
            {"on_screen": "OURS",
             "spoken": "Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory."},
        ],
        "body": "Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory, no additives.",
        "caption": "Freeze dried and spray dried are not the same thing.\n\nSpray drying uses hot air. Freeze drying works cold, so more aroma survives.\n\nLook at the granules: crystals or powder.\n\nPurity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.\n\np3online.in",
        "cta": "Look at your granules, then shop at p3online.in",
        "comment_trigger": "Crystals or powder in your jar?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to the coffee drinker who has never looked closely.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the granules in close up, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Crystals or powder: what your granules tell you",
        "title": "Crystals or powder: what your granules tell you",
        "slides": [
            {"slide": 1, "heading": "Tip some into your palm",
             "body": "Before the water goes in, look at what you are actually holding.",
             "visual": "Granules poured into an open palm"},
            {"slide": 2, "heading": "Crystals mean freeze dried",
             "body": "Irregular, glassy pieces that catch the light.",
             "visual": "Macro shot of coffee crystals"},
            {"slide": 3, "heading": "Fine powder means spray dried",
             "body": "Even, dusty and uniform, because hot air made it.",
             "visual": "Macro shot of fine coffee powder"},
            {"slide": 4, "heading": "Why the method matters",
             "body": "Freeze drying works cold, so more of the aroma survives.",
             "visual": "Steam rising from a fresh cup"},
            {"slide": 5, "heading": "It is on the pack",
             "body": "The method is usually printed on the label. Look for it.",
             "visual": "Label with the drying method in frame"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Tip some granules into your palm before the water goes in.\n\nCrystals mean freeze dried. Fine powder means spray dried, which uses hot air.\n\nPurity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.\n\np3online.in",
        "cta": "Look at your granules, then shop at p3online.in",
        "comment_trigger": "Crystals or powder in your jar?",
        "save_trigger": "Save this and check your jar tonight.",
        "share_trigger": "Send this to someone who has never looked closely.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Two jars of instant coffee can look completely different in your palm.",
        "body": "Irregular glassy crystals mean freeze dried. Even fine powder means spray dried, which uses hot air. Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.",
        "caption": "Tip some into your palm before the water goes in.\n\nCrystals mean freeze dried. Fine powder means spray dried, made with hot air.\n\nPurity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.\n\np3online.in",
        "cta": "Look at your granules, then shop at p3online.in",
        "comment_trigger": "Crystals or powder in your jar?",
        "save_trigger": "Save this and check your jar tonight.",
        "share_trigger": "Send this to someone who has never looked closely.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    # ── Set 6 — dose, not additives ───────────────────────────────────────────
    {
        "type": "reel",
        "hook": "If your coffee tastes weak, the fix is usually the spoon.",
        "hook_text": "If your coffee tastes weak, the fix is usually the spoon.",
        "hook_spoken": "Weak coffee is almost always a dose problem, not a coffee problem.",
        "hook_text_overlay": "CHECK THE SPOON",
        "frames": [
            {"on_screen": "CHECK THE SPOON",
             "spoken": "Weak coffee is almost always a dose problem, not a coffee problem."},
            {"on_screen": "ONE LEVEL SPOON",
             "spoken": "Start with one level teaspoon for a small cup. Level, not heaped."},
            {"on_screen": "SAME CUP",
             "spoken": "Use the same cup every morning so you are changing one thing at a time."},
            {"on_screen": "ADJUST ONCE",
             "spoken": "Too weak, add a quarter spoon tomorrow. Not a whole one."},
            {"on_screen": "THREE DAYS",
             "spoken": "Three mornings and you will have your number. Then it is the same every day."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Weak coffee is usually a dose problem.\n\nOne level teaspoon, same cup, adjust by a quarter spoon at a time. Three mornings and you have your number.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Find your spoon, then restock at p3online.in",
        "comment_trigger": "How many spoons go into your cup?",
        "save_trigger": "Save this and try it tomorrow morning.",
        "share_trigger": "Send this to whoever says instant coffee tastes weak.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the spoon going into the jar, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "How to find your spoon in three mornings",
        "title": "How to find your spoon in three mornings",
        "slides": [
            {"slide": 1, "heading": "Morning one: one level spoon",
             "body": "One level teaspoon in your usual cup. Level, not heaped.",
             "visual": "Level teaspoon held over a cup"},
            {"slide": 2, "heading": "Keep the cup the same",
             "body": "Change one thing at a time or you learn nothing.",
             "visual": "The same mug on a counter"},
            {"slide": 3, "heading": "Morning two: adjust a quarter",
             "body": "Too weak, add a quarter spoon. Too strong, take a quarter away.",
             "visual": "Quarter spoon being tapped off"},
            {"slide": 4, "heading": "Morning three: confirm it",
             "body": "Make the same cup again and check it still tastes right.",
             "visual": "Two identical cups side by side"},
            {"slide": 5, "heading": "Now it is repeatable",
             "body": "You have a number. Every cup after this one is the same.",
             "visual": "Spoon resting beside a filled cup"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Three mornings to find your spoon.\n\nOne level teaspoon, same cup, adjust by a quarter. Then it is the same cup every day.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Find your spoon, then restock at p3online.in",
        "comment_trigger": "How many spoons go into your cup?",
        "save_trigger": "Save this and start tomorrow morning.",
        "share_trigger": "Send this to whoever says instant tastes weak.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Weak coffee is usually a dose problem, not a coffee problem.",
        "body": "One level teaspoon, the same cup every morning, and adjust by a quarter spoon at a time. Three mornings and you have your number. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Weak coffee is usually a dose problem.\n\nOne level teaspoon, same cup, adjust a quarter at a time. Three mornings and you have your number.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Find your spoon, then restock at p3online.in",
        "comment_trigger": "How many spoons go into your cup?",
        "save_trigger": "Save this and try it tomorrow.",
        "share_trigger": "Send this to whoever says instant tastes weak.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 7 — water off the boil ────────────────────────────────────────────
    {
        "type": "reel",
        "hook": "Pouring water straight off the boil is scorching your coffee.",
        "hook_text": "Pouring water straight off the boil is scorching your coffee.",
        "hook_spoken": "Straight off the boil is hotter than coffee wants to be.",
        "hook_text_overlay": "WAIT 30 SECONDS",
        "frames": [
            {"on_screen": "WAIT 30 SECONDS",
             "spoken": "Straight off the boil is hotter than coffee wants to be."},
            {"on_screen": "TAKE IT OFF",
             "spoken": "Take the kettle off the heat and count to thirty."},
            {"on_screen": "THEN POUR",
             "spoken": "Then pour. That small pause is the whole technique."},
            {"on_screen": "WHY",
             "spoken": "Very hot water pulls harder, and what it pulls hardest is the bitterness."},
            {"on_screen": "TRY BOTH",
             "spoken": "Make one cup each way tomorrow and taste them side by side."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Water straight off the boil is hotter than coffee wants.\n\nTake the kettle off, count to thirty, then pour. That pause is the whole technique.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Try it tomorrow, then restock at p3online.in",
        "comment_trigger": "Do you pour straight off the boil?",
        "save_trigger": "Save this and try it in the morning.",
        "share_trigger": "Send this to whoever makes the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the kettle being set down, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "The thirty second pause that changes your cup",
        "title": "The thirty second pause that changes your cup",
        "slides": [
            {"slide": 1, "heading": "Boil the kettle as usual",
             "body": "Nothing changes here. Bring it up to the boil.",
             "visual": "Kettle coming to the boil"},
            {"slide": 2, "heading": "Take it off the heat",
             "body": "Off the hob, or let it click off and leave it alone.",
             "visual": "Kettle lifted off a hob"},
            {"slide": 3, "heading": "Count to thirty",
             "body": "That is long enough to come off the very top of the heat.",
             "visual": "Clock face or counting fingers"},
            {"slide": 4, "heading": "Then pour",
             "body": "Straight onto the coffee, the same way you always do.",
             "visual": "Water pouring into a cup of granules"},
            {"slide": 5, "heading": "Why it helps",
             "body": "Very hot water pulls harder, and it pulls the bitterness hardest.",
             "visual": "Two cups, one darker than the other"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Boil, take it off, count to thirty, then pour.\n\nVery hot water pulls harder, and it pulls bitterness hardest. That pause is the whole technique.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Try it tomorrow, then restock at p3online.in",
        "comment_trigger": "Do you pour straight off the boil?",
        "save_trigger": "Save this and try it in the morning.",
        "share_trigger": "Send this to whoever makes the coffee in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Take the kettle off and count to thirty before you pour.",
        "body": "Water straight off the boil pulls harder, and what it pulls hardest is the bitterness. Take it off the heat, count to thirty, then pour. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Take the kettle off the heat and count to thirty before you pour.\n\nVery hot water pulls harder, and it pulls bitterness hardest.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Try it tomorrow, then restock at p3online.in",
        "comment_trigger": "Do you pour straight off the boil?",
        "save_trigger": "Save this and try it in the morning.",
        "share_trigger": "Send this to whoever makes the coffee.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 8 — arabica and robusta ───────────────────────────────────────────
    {
        "type": "reel",
        "hook": "Arabica and robusta are two different plants, not two grades.",
        "hook_text": "Arabica and robusta are two different plants, not two grades.",
        "hook_spoken": "People talk about them like good and bad. They are simply different species.",
        "hook_text_overlay": "TWO PLANTS",
        "frames": [
            {"on_screen": "TWO PLANTS",
             "spoken": "People talk about them like good and bad. They are two different species."},
            {"on_screen": "ARABICA",
             "spoken": "Arabica grows higher and slower, and tends to taste softer and more aromatic."},
            {"on_screen": "ROBUSTA",
             "spoken": "Robusta grows lower and hardier, and tends to taste stronger and more bitter."},
            {"on_screen": "IT IS ON THE PACK",
             "spoken": "Which one you are drinking is usually printed on the label."},
            {"on_screen": "OURS",
             "spoken": "Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory."},
        ],
        "body": "Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory, no additives.",
        "caption": "Arabica and robusta are two different plants, not two grades.\n\nArabica grows higher and slower and tends to be softer. Robusta is hardier and tends to be stronger and more bitter.\n\nPurity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.\n\np3online.in",
        "cta": "Check your pack, then shop at p3online.in",
        "comment_trigger": "Which one does your pack say?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever argues about coffee at your table.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the label being read, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Arabica and robusta, side by side",
        "title": "Arabica and robusta, side by side",
        "slides": [
            {"slide": 1, "heading": "Two species, not two grades",
             "body": "They are different plants, so they behave differently.",
             "visual": "Two coffee plants side by side"},
            {"slide": 2, "heading": "Where they grow",
             "body": "Arabica prefers higher, cooler ground. Robusta is hardier and lower.",
             "visual": "Hillside plantation and lowland plantation"},
            {"slide": 3, "heading": "How they taste",
             "body": "Arabica tends softer and more aromatic. Robusta tends stronger and more bitter.",
             "visual": "Two cups being tasted"},
            {"slide": 4, "heading": "Neither is a verdict",
             "body": "Different is not the same as better. Blends use both on purpose.",
             "visual": "Beans of both types mixed in a bowl"},
            {"slide": 5, "heading": "Your pack will say",
             "body": "The type is usually printed on the label. Look for it.",
             "visual": "Label with the bean type in frame"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Arabica and robusta are two species, not two grades.\n\nArabica grows higher and tends softer. Robusta is hardier and tends stronger. Neither is a verdict.\n\nPurity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.\n\np3online.in",
        "cta": "Check your pack, then shop at p3online.in",
        "comment_trigger": "Which one does your pack say?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever argues about coffee at your table.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Arabica and robusta are two different plants, not two grades.",
        "body": "Arabica grows higher and slower and tends to taste softer. Robusta is hardier and tends to taste stronger and more bitter. Neither is a verdict. Purity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.",
        "caption": "Arabica and robusta are two species, not two grades.\n\nArabica tends softer and more aromatic. Robusta tends stronger and more bitter. Different is not better.\n\nPurity Beans Purica is freeze-dried 100% Arabica. Bold and Purista are 100% Robusta. 100% coffee, zero chicory.\n\np3online.in",
        "cta": "Check your pack, then shop at p3online.in",
        "comment_trigger": "Which one does your pack say?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever argues about coffee at your table.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 9 — the first thing a fresh jar does ──────────────────────────────
    {
        "type": "reel",
        "hook": "Smell the jar before you make the first cup.",
        "hook_text": "Smell the jar before you make the first cup.",
        "hook_spoken": "The moment you break the seal is the most honest the coffee will ever smell.",
        "hook_text_overlay": "SMELL IT FIRST",
        "frames": [
            {"on_screen": "SMELL IT FIRST",
             "spoken": "The moment you break the seal is the most honest the coffee will ever smell."},
            {"on_screen": "BREAK THE SEAL",
             "spoken": "Open it and hold it under your nose before anything else happens."},
            {"on_screen": "REMEMBER IT",
             "spoken": "That is your reference. Everything after this is measured against it."},
            {"on_screen": "CHECK IN A MONTH",
             "spoken": "Smell it again in a month. If it has faded, your storage is the reason."},
            {"on_screen": "OURS",
             "spoken": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Smell the jar the moment you break the seal.\n\nThat is your reference. Smell it again in a month, and if it has faded, storage is the reason.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Smell yours tonight, then restock at p3online.in",
        "comment_trigger": "When did you last smell your coffee jar?",
        "save_trigger": "Save this and do it with your next jar.",
        "share_trigger": "Send this to whoever opens the new jar in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the seal being broken, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "A one month test for your coffee storage",
        "title": "A one month test for your coffee storage",
        "slides": [
            {"slide": 1, "heading": "Open a fresh jar",
             "body": "Break the seal and smell it before you make anything.",
             "visual": "Foil seal being peeled back"},
            {"slide": 2, "heading": "That smell is your baseline",
             "body": "It is the strongest the jar will ever be. Remember it.",
             "visual": "Jar held up to the light"},
            {"slide": 3, "heading": "Store it the way you always do",
             "body": "No changes. You are testing your own kitchen, not a theory.",
             "visual": "Jar going into its usual place"},
            {"slide": 4, "heading": "Smell it again in a month",
             "body": "Same jar, same nose, four weeks later.",
             "visual": "Hand reaching for the same jar"},
            {"slide": 5, "heading": "Read the result",
             "body": "Faded means air, heat or damp got in. All three are fixable.",
             "visual": "Lid being closed firmly"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Smell a fresh jar the moment you open it. That is your baseline.\n\nSmell it again in a month. Faded means air, heat or damp got in, and all three are fixable.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Run the test, then restock at p3online.in",
        "comment_trigger": "When did you last smell your coffee jar?",
        "save_trigger": "Save this and start with your next jar.",
        "share_trigger": "Send this to whoever opens the new jar in your house.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Smell a fresh jar the moment you break the seal.",
        "body": "That is the strongest it will ever be, and it is your baseline. Smell it again in a month, and if it has faded, air, heat or damp got in. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Smell the jar the moment you break the seal. That is your baseline.\n\nSmell it again in a month. Faded means air, heat or damp got in, and all three are fixable.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Run the test, then restock at p3online.in",
        "comment_trigger": "When did you last smell your coffee jar?",
        "save_trigger": "Save this and start with your next jar.",
        "share_trigger": "Send this to whoever opens the new jar.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    # ── Set 10 — milk ─────────────────────────────────────────────────────────
    {
        "type": "reel",
        "hook": "Add the water first, then the milk. Not the other way round.",
        "hook_text": "Add the water first, then the milk. Not the other way round.",
        "hook_spoken": "Milk straight onto the granules is why your cup has lumps in it.",
        "hook_text_overlay": "WATER FIRST",
        "frames": [
            {"on_screen": "WATER FIRST",
             "spoken": "Milk straight onto the granules is why your cup has lumps in it."},
            {"on_screen": "A LITTLE WATER",
             "spoken": "Start with a splash of hot water. Just enough to cover the coffee."},
            {"on_screen": "STIR IT SMOOTH",
             "spoken": "Stir until it is a smooth dark paste with nothing grainy left."},
            {"on_screen": "NOW THE MILK",
             "spoken": "Then top it up with milk, hot or cold, however you like it."},
            {"on_screen": "NO LUMPS",
             "spoken": "Same coffee, same milk, no lumps. The order is the whole trick."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Milk straight onto the granules is why you get lumps.\n\nSplash of hot water first, stir to a smooth paste, then top up with milk.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Try it tomorrow, then restock at p3online.in",
        "comment_trigger": "Do you add water or milk first?",
        "save_trigger": "Save this and try it in the morning.",
        "share_trigger": "Send this to whoever complains about lumps.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the spoon stirring, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Four steps to a milk coffee with no lumps",
        "title": "Four steps to a milk coffee with no lumps",
        "slides": [
            {"slide": 1, "heading": "Coffee in the cup",
             "body": "Your usual spoon, straight into a dry cup.",
             "visual": "Granules in the bottom of an empty mug"},
            {"slide": 2, "heading": "A splash of hot water",
             "body": "Just enough to cover the granules. Not a full cup.",
             "visual": "Small amount of water being poured"},
            {"slide": 3, "heading": "Stir to a paste",
             "body": "Keep going until it is smooth and nothing is grainy.",
             "visual": "Spoon working a dark paste"},
            {"slide": 4, "heading": "Then the milk",
             "body": "Top it up hot or cold. It will not clump now.",
             "visual": "Milk being poured into the cup"},
            {"slide": 5, "heading": "Why it works",
             "body": "Coffee dissolves in water more easily than in milk.",
             "visual": "Two cups, one smooth and one grainy"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Coffee in the cup, splash of hot water, stir to a smooth paste, then milk.\n\nCoffee dissolves in water more easily than in milk, which is the whole reason for the order.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Try it tomorrow, then restock at p3online.in",
        "comment_trigger": "Do you add water or milk first?",
        "save_trigger": "Save this and try it in the morning.",
        "share_trigger": "Send this to whoever complains about lumps.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Lumps in your milk coffee are an order problem, not a coffee problem.",
        "body": "Splash of hot water onto the granules first, stir to a smooth paste, then top up with milk. Coffee dissolves in water more easily than in milk. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Lumps are an order problem.\n\nHot water onto the granules first, stir smooth, then milk. Coffee dissolves in water more easily than in milk.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Try it tomorrow, then restock at p3online.in",
        "comment_trigger": "Do you add water or milk first?",
        "save_trigger": "Save this and try it in the morning.",
        "share_trigger": "Send this to whoever complains about lumps.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 11 — cold coffee ──────────────────────────────────────────────────
    {
        "type": "reel",
        "hook": "You can make cold coffee without any hot water at all.",
        "hook_text": "You can make cold coffee without any hot water at all.",
        "hook_spoken": "Instant coffee dissolves in cold water. It just needs longer.",
        "hook_text_overlay": "NO KETTLE",
        "frames": [
            {"on_screen": "NO KETTLE",
             "spoken": "Instant coffee dissolves in cold water. It just needs longer."},
            {"on_screen": "COFFEE AND SUGAR",
             "spoken": "Coffee in the glass, sugar if you take it, and two spoons of cold water."},
            {"on_screen": "STIR HARD",
             "spoken": "Stir hard for a minute. It goes pale and thick as the air gets in."},
            {"on_screen": "ADD COLD MILK",
             "spoken": "Then pour in cold milk and ice and stir it through."},
            {"on_screen": "ONE GLASS",
             "spoken": "One glass, one spoon, no kettle, and nothing added that was not yours."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Cold coffee without boiling anything.\n\nCoffee, sugar and two spoons of cold water. Stir hard for a minute until it goes pale and thick, then add cold milk and ice.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Make one this afternoon, then restock at p3online.in",
        "comment_trigger": "Hot or cold in your house this week?",
        "save_trigger": "Save this for the next hot afternoon.",
        "share_trigger": "Send this to whoever asks for cold coffee.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the glass being set down, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Cold coffee in one glass, no kettle",
        "title": "Cold coffee in one glass, no kettle",
        "slides": [
            {"slide": 1, "heading": "Coffee in the glass",
             "body": "Your usual spoon, straight into a tall glass.",
             "visual": "Granules in the bottom of a tall glass"},
            {"slide": 2, "heading": "Sugar if you take it",
             "body": "Add it now, while there is almost no liquid to fight.",
             "visual": "Sugar being spooned in"},
            {"slide": 3, "heading": "Two spoons of cold water",
             "body": "Only two. This part is a paste, not a drink.",
             "visual": "Small amount of cold water added"},
            {"slide": 4, "heading": "Stir hard for a minute",
             "body": "It turns pale and thick as air works into it.",
             "visual": "Spoon whipping a pale coffee paste"},
            {"slide": 5, "heading": "Cold milk and ice",
             "body": "Pour it in, stir it through, and it is done.",
             "visual": "Milk poured over ice in the glass"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar beside the finished glass"},
        ],
        "caption": "Cold coffee without boiling anything.\n\nCoffee, sugar, two spoons of cold water. Stir hard for a minute until pale and thick, then cold milk and ice.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Make one this afternoon, then restock at p3online.in",
        "comment_trigger": "Hot or cold in your house this week?",
        "save_trigger": "Save this for the next hot afternoon.",
        "share_trigger": "Send this to whoever asks for cold coffee.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Cold coffee does not need a kettle at all.",
        "body": "Coffee and sugar in the glass, two spoons of cold water, stir hard for a minute until it goes pale and thick, then cold milk and ice. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Cold coffee, no kettle.\n\nCoffee and sugar, two spoons of cold water, stir hard for a minute until pale and thick, then cold milk and ice.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Make one this afternoon, then restock at p3online.in",
        "comment_trigger": "Hot or cold in your house this week?",
        "save_trigger": "Save this for the next hot afternoon.",
        "share_trigger": "Send this to whoever asks for cold coffee.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 12 — how long a jar lasts ─────────────────────────────────────────
    {
        "type": "reel",
        "hook": "Work out how long a jar lasts before you decide it is expensive.",
        "hook_text": "Work out how long a jar lasts before you decide it is expensive.",
        "hook_spoken": "A jar is not a price. It is a number of mornings.",
        "hook_text_overlay": "COUNT MORNINGS",
        "frames": [
            {"on_screen": "COUNT MORNINGS",
             "spoken": "A jar is not a price. It is a number of mornings."},
            {"on_screen": "YOUR SPOON",
             "spoken": "Find your usual spoon. That is your dose, and it does not change."},
            {"on_screen": "CUPS PER DAY",
             "spoken": "Count how many cups actually get made in your house each day."},
            {"on_screen": "DIVIDE",
             "spoken": "Net weight, divided by your dose, divided by cups a day. That is your answer."},
            {"on_screen": "NOW COMPARE",
             "spoken": "Compare jars on mornings, not on the number on the front."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "A jar is not a price, it is a number of mornings.\n\nNet weight, divided by your usual spoon, divided by cups a day. Compare jars on that.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Do the sum, then shop at p3online.in",
        "comment_trigger": "How many cups a day does your house make?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever does the household shopping.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the jar being set down, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Two jars at the same price are rarely the same number of mornings",
        "title": "Two jars at the same price are rarely the same number of mornings",
        "slides": [
            {"slide": 1, "heading": "Find the net weight",
             "body": "It is on the pack, usually near the bottom of the label.",
             "visual": "Net weight printed on a jar"},
            {"slide": 2, "heading": "Find your dose",
             "body": "The spoon you actually use, not the one on the packet.",
             "visual": "Level teaspoon of granules"},
            {"slide": 3, "heading": "Count the cups",
             "body": "How many get made in your house on a normal day.",
             "visual": "Several mugs on a kitchen counter"},
            {"slide": 4, "heading": "Do the division",
             "body": "Weight, divided by dose, divided by cups a day.",
             "visual": "Simple sum written on paper"},
            {"slide": 5, "heading": "Compare mornings",
             "body": "Now the two jars are actually comparable to each other.",
             "visual": "Two jars side by side"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Compare coffee jars on mornings, not on the number on the front.\n\nNet weight, divided by your usual spoon, divided by cups a day.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Do the sum, then shop at p3online.in",
        "comment_trigger": "How many cups a day does your house make?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever does the household shopping.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "A jar of coffee is not a price. It is a number of mornings.",
        "body": "Net weight, divided by the spoon you actually use, divided by cups a day. That is how long it lasts, and it is the only way two jars are comparable. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "A jar is not a price. It is a number of mornings.\n\nNet weight, divided by your usual spoon, divided by cups a day. Compare jars on that number.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Do the sum, then shop at p3online.in",
        "comment_trigger": "How many cups a day does your house make?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever does the household shopping.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },

    # ── Set 13 — the date on the pack ─────────────────────────────────────────
    {
        "type": "reel",
        "hook": "Best before is not the same as an expiry date.",
        "hook_text": "Best before is not the same as an expiry date.",
        "hook_spoken": "People read best before as a deadline. It is a quality note, not a safety one.",
        "hook_text_overlay": "BEST BEFORE",
        "frames": [
            {"on_screen": "BEST BEFORE",
             "spoken": "People read best before as a deadline. It is a quality note, not a safety one."},
            {"on_screen": "WHAT IT MEANS",
             "spoken": "It is the date the maker expects it to still taste the way they intended."},
            {"on_screen": "FIND THE OTHER ONE",
             "spoken": "Look for the packed or manufactured date too. Both are usually printed."},
            {"on_screen": "DO THE MATH",
             "spoken": "The gap between them tells you how fresh the jar was when you bought it."},
            {"on_screen": "CHECK TONIGHT",
             "spoken": "Turn your jar around and find both dates. It takes five seconds."},
        ],
        "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
        "caption": "Best before is a quality note, not a safety deadline.\n\nFind the packed date as well. The gap between the two tells you how fresh the jar was when you bought it.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Check both dates, then shop at p3online.in",
        "comment_trigger": "What dates are printed on your jar?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever does the household shopping.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "audio": "Quiet kitchen ambience, no music bed - the spoken line carries it.",
        "loop_ending": "Ends on the date panel in close up, which is how it opens - the last frame reads as the first.",
        "angle": "EDUCATE",
        "source": "evergreen_template",
    },
    {
        "type": "carousel",
        "hook": "Two dates on the pack, and what each one means",
        "title": "Two dates on the pack, and what each one means",
        "slides": [
            {"slide": 1, "heading": "Best before",
             "body": "The date the maker expects it to still taste as intended.",
             "visual": "Best before date printed on a pack"},
            {"slide": 2, "heading": "Packed or manufactured",
             "body": "When it was actually made and sealed.",
             "visual": "Manufactured date on the same pack"},
            {"slide": 3, "heading": "The gap matters",
             "body": "It tells you how much of the life was already gone at purchase.",
             "visual": "Two dates side by side with a gap marked"},
            {"slide": 4, "heading": "Best before is not expiry",
             "body": "It is a quality note. Expiry is a different kind of date.",
             "visual": "Label panel with the wording in frame"},
            {"slide": 5, "heading": "Check before you buy",
             "body": "Same five seconds as reading the ingredient list.",
             "visual": "Hand turning a jar in a shop aisle"},
            {"slide": 6, "heading": "What ours says",
             "body": "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. p3online.in",
             "visual": "Purity Beans jar, label facing camera"},
        ],
        "caption": "Best before is a quality note, not a safety deadline.\n\nFind the packed date too. The gap tells you how much of the jar's life was gone before you bought it.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Check both dates, then shop at p3online.in",
        "comment_trigger": "What dates are printed on your jar?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever does the household shopping.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
    {
        "type": "instagram_post",
        "hook": "Best before is a quality note, not a safety deadline.",
        "body": "Find the packed or manufactured date as well. The gap between the two tells you how much of the jar's life was already gone when you bought it. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
        "caption": "Best before is a quality note, not a safety deadline.\n\nFind the packed date too. The gap tells you how fresh the jar was when you bought it.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\np3online.in",
        "cta": "Check both dates, then shop at p3online.in",
        "comment_trigger": "What dates are printed on your jar?",
        "save_trigger": "Save this for your next grocery run.",
        "share_trigger": "Send this to whoever does the household shopping.",
        "hashtags": "#PurityBeans #PureCoffee #InstantCoffee #ZeroChicory #CoffeeIndia",
        "source": "evergreen_template",
    },
]

_DISTRIBUTOR_TEMPLATES: list[dict] = [
    {
        "type": "linkedin_post",
        "hook": "What our distributors ask about first",
        "body": (
            "The first question is always the ingredient list, because it is what "
            "the customer asks them about at the counter.\n\n"
            "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. "
            "Ultra Blend is 70% coffee. That is a straightforward range to stand "
            "behind on a shelf full of blends.\n\n"
            "We are expanding our distributor network. If you distribute FMCG and "
            "want the details, message me.\n\np3online.in"
        ),
        "cta": "DM for the distributor pack",
        "hashtags": "#FMCG #Distribution #Coffee #IndianBrands #PurityBeans",
        "source": "evergreen_distributor",
    },
    {
        "type": "linkedin_post",
        "hook": "One ingredient is easier to sell across a counter",
        "body": "A short ingredient list answers the shopper's question before it is asked.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee. That makes counter conversations short and repeatable for the person selling it.\n\nWe are expanding our distributor network. If you distribute FMCG and want the details, message me.\n\np3online.in",
        "cta": "DM for the distributor pack",
        "hashtags": "#FMCG #Distribution #Coffee #IndianBrands #PurityBeans",
        "source": "evergreen_distributor",
    },
    {
        "type": "linkedin_post",
        "hook": "What we get asked about shelf life",
        "body": "Stockists ask about rotation before they ask about margin, because slow-moving stock is the expensive problem.\n\nPurity Beans Purica is freeze-dried 100% Arabica and Bold is agglomerated 100% Robusta, both in glass jars - 100% coffee, zero chicory - and we are direct about pack sizes and dating so a buyer can plan rotation rather than guess at it.\n\nWe are expanding our distributor network. If you distribute FMCG and want the details, message me.\n\np3online.in",
        "cta": "DM for the distributor pack",
        "hashtags": "#FMCG #Distribution #Retail #IndianBrands #PurityBeans",
        "source": "evergreen_distributor",
    },
    {
        "type": "linkedin_post",
        "hook": "The label question comes up at every meeting",
        "body": "Every buyer conversation reaches the ingredient panel, usually within the first few minutes. It is the fastest way to understand what a product actually is.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee. The panel is the pitch.\n\nWe are expanding our distributor network. If you distribute FMCG and want the details, message me.\n\np3online.in",
        "cta": "DM for the distributor pack",
        "hashtags": "#FMCG #Distribution #Coffee #IndianBrands #PurityBeans",
        "source": "evergreen_distributor",
    },
    {
        "type": "linkedin_post",
        "hook": "Category education is doing our selling for us",
        "body": "The shoppers who turn a jar around before buying are the ones who become repeat customers. They are not looking for a brand, they are looking for a short ingredient list.\n\nPurity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee. The more label-literate a category gets, the easier those jars are to place.\n\nWe are expanding our distributor network. If you distribute FMCG and want the details, message me.\n\np3online.in",
        "cta": "DM for the distributor pack",
        "hashtags": "#FMCG #Distribution #Coffee #IndianBrands #PurityBeans",
        "source": "evergreen_distributor",
    },
]


def emergency_content_set(day_number: int = 0) -> dict:
    """
    Generate a reduced content set when all LLM providers are unavailable.

    Returns a valid content dict with the same keys as generate_daily_content(),
    so the rest of the pipeline (save, memory, objectives) can continue normally.
    """
    logger.warning(
        "[fallback] ALL LLM PROVIDERS FAILED — using emergency content set for day %d",
        day_number,
    )

    # Try yesterday's snapshot first
    content = _from_yesterday_snapshot(day_number)
    if content:
        logger.info("[fallback] Using yesterday's snapshot as base")
        _send_fallback_alert("yesterday_snapshot", day_number)
        return _attach_stories(content, day_number)

    # Try last week's best content
    content = _from_best_historical(day_number)
    if content:
        logger.info("[fallback] Using best historical content")
        _send_fallback_alert("historical_best", day_number)
        return _attach_stories(content, day_number)

    # Final safety net: evergreen templates
    logger.warning("[fallback] Using evergreen templates (minimum viable output)")
    _send_fallback_alert("evergreen_templates", day_number)
    return _attach_stories(_from_evergreen(day_number), day_number)


def _from_yesterday_snapshot(day_number: int) -> dict | None:
    """Extract and lightly remix yesterday's content."""
    try:
        from content_generator.scheduler.snapshot import load_yesterday_snapshot
        snap = load_yesterday_snapshot()
        if not snap or "content" not in snap:
            return None

        yesterday_content = snap["content"]
        # Mark as recycled so analytics can discount it
        yesterday_content["_source"]    = "emergency_fallback_yesterday"
        yesterday_content["_recycled"]  = True
        yesterday_content["day_number"] = day_number
        return yesterday_content
    except Exception as e:
        logger.debug("[fallback] yesterday snapshot failed: %s", e)
        return None


def _from_best_historical(day_number: int) -> dict | None:
    """Build a content set from the highest-performing historical pieces."""
    try:
        from content_generator.analytics.metrics_store import get_recent_metrics
        rows = get_recent_metrics(days=30)
        if not rows or len(rows) < 3:
            return None

        # Top 4 by viral score
        top = sorted(rows, key=lambda x: x.get("viral_score", 0), reverse=True)[:4]

        reels = []
        for r in top[:2]:
            reels.append({
                "hook":   r.get("hook_archetype", "Pure coffee. Real taste."),
                "body":   "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory and no additives. Ultra Blend is 70% coffee.",
                "cta":    "Read the label, then shop at p3online.in",
                "_source": f"recycled:{r.get('content_id', '')}",
            })

        return {
            "day_number":     day_number,
            "reels":          reels,
            "carousel":       _EVERGREEN[1],
            "instagram_post": _EVERGREEN[2],
            "linkedin_post":  _DISTRIBUTOR_TEMPLATES[0],
            "_source":        "emergency_fallback_historical",
            "_recycled":      True,
        }
    except Exception as e:
        logger.debug("[fallback] historical best failed: %s", e)
        return None


def _of_type(kind: str) -> list[dict]:
    return [p for p in _EVERGREEN if p.get("type") == kind]


def _pick(kind: str, day_number: int, offset: int = 0) -> dict | None:
    """Deterministic day-indexed pick, so consecutive days differ and any day is reproducible."""
    pool = _of_type(kind)
    if not pool:
        return None
    return pool[(int(day_number or 0) + offset) % len(pool)]


def _from_evergreen(day_number: int) -> dict:
    """
    Guaranteed fallback using static evergreen templates, rotated by day.

    This used to random.shuffle() the template list and take the first of each
    type. With one template per type that was a shuffle of a single-element
    list: every fallback day produced byte-identical content. Since no day has
    ever produced real generation, that is every post the account has ever made
    — the same reel, the same carousel, the same caption, for weeks.

    Rotation is now indexed by day rather than randomised, which:
      - guarantees consecutive days differ, where shuffling only made it likely
      - makes any given day reproducible, so a bad post can be traced to a
        template instead of an unrecoverable RNG draw
      - offsets reel_2 from reel_1 so the two reels in a day are never the same
    """
    reels = [r for r in (_pick("reel", day_number), _pick("reel", day_number, 1)) if r]
    while len(reels) < 2 and _of_type("reel"):
        reels.append(_of_type("reel")[0])

    payload = {
        "day_number":     day_number,
        "reels":          reels,
        "carousel":       _pick("carousel", day_number) or _EVERGREEN[1],
        "instagram_post": _pick("instagram_post", day_number) or _EVERGREEN[2],
        "linkedin_post":  _DISTRIBUTOR_TEMPLATES[
                              int(day_number or 0) % len(_DISTRIBUTOR_TEMPLATES)],
        "_source":        "emergency_fallback_evergreen",
        "_recycled":      True,
    }
    return _attach_stories(payload, day_number)


def _attach_stories(payload: dict, day_number: int) -> dict:
    """Give fallback days a stories.story_1 so post_story is not slogan-only."""
    if not isinstance(payload, dict):
        return payload
    stories = payload.get("stories") if isinstance(payload.get("stories"), dict) else {}
    s1 = stories.get("story_1") if isinstance(stories.get("story_1"), dict) else {}
    if s1.get("headline") or s1.get("poll_question"):
        return payload
    try:
        from content_generator.publisher.story_copy import stories_block_from_content
        payload["stories"] = stories_block_from_content(payload, day_number)
    except Exception as e:
        logger.debug("[fallback] stories block skipped: %s", e)
    return payload


def _send_fallback_alert(source: str, day_number: int) -> None:
    """Alert the founder that the fallback activated."""
    msg = (
        f"FALLBACK ACTIVATED — Day {day_number}\n"
        f"Source: {source}\n"
        f"All LLM providers unavailable.\n"
        f"Reduced content set generated.\n"
        f"Check API keys and provider status."
    )
    try:
        from content_generator.scheduler.watchdog import _alert
        _alert(msg)
    except Exception:
        logger.warning("[fallback] %s", msg)
