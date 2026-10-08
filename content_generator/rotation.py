"""
Rotation banks and day-number helpers.
All mutable state lives here so every prompt module imports from one place.
"""
import os
import datetime

# ── Start date ────────────────────────────────────────────────────────────────
# Change this if the project restarts from day 0.
CONTENT_ENGINE_START_DATE = datetime.date(2026, 1, 1)

# ── Runtime config ────────────────────────────────────────────────────────────
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://p3online.in")

# ── Rotation banks ────────────────────────────────────────────────────────────

BLOG_TOPIC_CLUSTERS = [
    "how to brew instant coffee at home in India — dose, water, and what the label should say",
    "instant coffee recipe India — 2-minute preparation and flavour variations without invented health claims",
    "instant coffee for students in India — price per cup, jar sizes, and how to read the label",
    "morning coffee routine India — a home cup with the jar that matches how you drink it",
    "how to check an instant coffee label in India for chicory — and which Purity Beans jars are 100% coffee",
    "coffee price comparison India — Rs 18 per cup at home vs Rs 180 at a cafe, using only those two prices",
    "work from home coffee India — a repeatable home cup, not a productivity study",
    "caffeine on the label — Ultra Blend is 70% coffee and may be called lower caffeine; the 100% coffee jars may not",
    "instant coffee jars in India — Bold, Purista, Purica, Prima, and Ultra Blend, each described only as labeled",
    "which Purity Beans jar to take before a workout — name the jar, no jitter or fat-loss claims",
    "how Purity Beans labels its jars — Bold, Purista, Purica, Prima, and Ultra Blend",
    "arabica vs robusta instant coffee in India — Purica and Prima are 100% Arabica; Bold and Purista are 100% Robusta",
    "coffee gifting India — variety box and duo jars, with the Ultra Blend jar called out as 70% coffee",
    "glass jar instant coffee in India — what is printed on a Purity Beans jar",
    "100% coffee jars vs Ultra Blend at 70% coffee — when a lower-caffeine description is allowed",
    "cold brew at home India — a method using a named Purity Beans jar",
    "coffee culture India — from filter kaapi to instant, without invented market statistics",
    "chicory on Indian instant-coffee labels — how to read the panel, without a percentage we cannot source",
]

HOOK_ARCHETYPES = [
    ("EXPOSE",         "Reveal what powerful brands actively hide — righteous anger drives shares"),
    ("IDENTITY CALL",  "Challenge who they believe they are — identity threat stops the scroll"),
    ("SHOCKING STAT",  "Open with a specific number that breaks their reality — precision beats vagueness"),
    ("CONTRARIAN",     "Fight the mainstream belief — controversy holds attention better than agreement"),
    ("TRANSFORMATION", "Before/after in one sentence — implies they can have the after too"),
    ("LOOP BAIT",      "End that loops to the beginning — algorithm rewards replays"),
    ("LIVE CHALLENGE", "Make them act RIGHT NOW — participation drives retention and algorithm boost"),
    ("RELATABLE FAIL", "Voice their silent daily failure — parasocial bond, mass relatability"),
    ("SOCIAL PROOF",   "Mass adoption framed as movement — nobody wants to be the last to know"),
    ("FEAR URGENCY",   "Something bad is happening right now — urgency overrides decision fatigue"),
    ("MYTH BUST",      "Call out a belief they hold as fact — cognitive dissonance halts the thumb"),
    ("INSIDER ACCESS", "You know something the industry hides — forbidden knowledge appeal"),
    ("CURIOSITY GAP",  "Start the answer but force them to watch to complete it — incomplete loops itch"),
    ("SOCIAL SHAME",   "Everyone else knows this but you — FOMO plus status anxiety in one punch"),
    ("PATTERN BREAK",  "Shatter the expected visually or verbally — novelty triggers the dopamine hit"),
    # Psychology-backed additions for pure coffee
    ("RITUAL",         "Frame the morning cup as the first identity decision of the day — ritual raises willingness to pay"),
    ("SENSORY",        "Name the exact taste or smell difference after years of filler — private test the viewer can run tomorrow"),
    ("CLEAN LABEL",    "Turn reading the ingredient panel into an act of self-respect — self-signaling drives saves"),
    ("CERTAINTY",      "Remove the quiet daily uncertainty of not knowing what is in the cup — loss aversion closer"),
    ("ACCESSIBLE",     "Café purity at everyday price and zero effort — resolves the price-sensitivity paradox"),
]

SAVE_MECHANICS = [
    ("MYTH-BUSTING LIST",  "List of false beliefs they hold — save to share and correct others"),
    ("COMPARISON TABLE",   "Side-by-side data they will reference later — save as cheat sheet"),
    ("STEP-BY-STEP GUIDE", "Process they want to execute later — save equals bookmark for action"),
    ("CHECKLIST",          "Diagnostic tool they reuse — save for repeated reference"),
    ("NUMBERED FACTS",     "Dense value stack — save to reread when they have time"),
    ("EXPOSE SLIDES",      "Damning evidence broken into slides — save and share to expose wrongdoing"),
    ("RECIPE HOW-TO",      "Instruction they want to execute in 24 hrs — save equals purchase intent"),
    ("DATA STORY",         "Before/after numbers with narrative — save for motivation"),
    ("RANKING TIER LIST",  "Ranked options with criteria — save as decision-making reference"),
    ("INSIDER GLOSSARY",   "Terms the industry uses — save to sound smart in conversations"),
    ("LABEL TEST",         "A 15-second test the viewer can run on the next jar they buy — high save rate"),
    ("RITUAL SCRIPT",      "Exact morning sequence that turns autopilot into a deliberate act — save to reuse"),
]

LINKEDIN_ANGLES = [
    # ── Deep Coffee Science & Processing ──
    ("FREEZE-DRIED VS SPRAY-DRIED",
     "The science of coffee dehydration: why freeze-drying at -40°C preserves volatile aromatics "
     "and essential oils via sublimation, while 200°C spray-drying scorches the bean and forces artificial "
     "flavour replenishment."),
    ("ARABICA VS ROBUSTA BOTANY",
     "Bean botany breakdown: Arabica (high altitude, 60% more lipids, delicate acidity like Purica) vs "
     "Robusta (low altitude, double the chlorogenic acid and caffeine, thick persistent crema like Bold & Purista). "
     "Why blending pure varieties works and why chicory is an adulterant, not a bean."),
    ("BREWING THERMODYNAMICS",
     "Why boiling water (100°C) destroys coffee: the chemistry of tannin extraction. How water between "
     "80°C and 85°C extracts sweet aromatic compounds without scorching, yielding natural cup sweetness without sugar."),
    ("WATER CHEMISTRY IN EXTRACTION",
     "98% of your morning brew is water. How Total Dissolved Solids (TDS), calcium, and magnesium dictate "
     "aroma solubility, and why office tap water produces bitter coffee regardless of the brand."),

    # ── Clean-Label Awareness & Industry Transparency ──
    ("CHICORY ROOT ECONOMICS",
     "The economic reality of Indian coffee: why mass brands blend 30% to 49% roasted chicory root. "
     "A historical wartime substitute that became an FMCG margin trick. The physiological difference between "
     "pure caffeine alertness and chicory inulin digestion."),
    ("LABEL LITERACY FOR EXECUTIVES",
     "How to read an Indian food label in 10 seconds: decoding 'Coffee-Chicory mixture' vs 'Pure Instant Coffee'. "
     "Why ingredient hierarchy matters and how front-of-pack claims obscure back-of-pack reality."),
    ("THE ADULTERATION PARADOX",
     "Why Indian consumers inspect olive oil, milk, and protein powder labels with intense scrutiny, yet "
     "drink 40% root filler in their morning cup without checking the ingredients."),
    ("CLEAN-LABEL MANUFACTURING",
     "What it actually takes to build a zero-compromise clean food brand in India: sourcing certified pure beans, "
     "refusing artificial flow agents, and rejecting artificial aromas."),

    # ── Cognitive Performance & Executive Chronobiology ──
    ("CAFFEINE CHRONOBIOLOGY",
     "Adenosine receptor dynamics: why drinking coffee within 15 minutes of waking impairs cortisol awakening "
     "and creates the dreaded 2 PM crash. The science of delaying caffeine 60-90 minutes for sustained deep work."),
    ("CLEAN CAFFEINE VS JITTERS",
     "The biochemical reason some coffee causes jitters and stomach acid: high-heat burnt beans and filler spikes "
     "vs clean, gently processed 100% coffee that fuels calm, razor-sharp focus."),
    ("THE DESK RITUAL PARADOX",
     "Transforming the autopilot pantry caffeine fix into a deliberate cognitive boundary: how sensory "
     "micro-rituals prime the brain for high-output flow state."),

    # ── Workplace Culture & Corporate Gifting ──
    ("CORPORATE PANTRY ROI",
     "The invisible tax of terrible office pantry coffee: how vending machine syrup sludge drags down team morale, "
     "and the surprising talent-retention ROI of upgrading to pure, premium coffee."),
    ("EXECUTIVE GIFTING ETHOS",
     "Why modern corporate gifting is abandoning generic sweets and plastic hampers in favor of clean, "
     "functional wellness: the rise of premium glass-jar coffee gifting for clients and leadership teams."),
    ("COFFEE CULTURE IN TECH HUBS",
     "From Bengaluru and Gurgaon tech parks to Mumbai founders: how India's knowledge workers are shifting "
     "from roadside sugar tea to artisan pure coffee."),

    # ── Founder Insights & Purity Beans Mission ──
    ("THE BOOTSTRAPPED PURITY BET",
     "Building Pure Pantry Provisions without VC capital: why refusing cheap fillers is harder in year one "
     "but creates an unbreakable moat in year five."),
    ("COFFEE VALUE MATH",
     "The honest economics of the daily cup: Rs 18 for pure, cafe-grade coffee at home vs Rs 180-250 at commercial "
     "chains. Calculating the 5-year compounding cost of routine coffee spending."),
    ("THE INDIAN COFFEE REVIVAL",
     "From the legendary Bababudan hills of Chikmagalur and Coorg: why India's shade-grown beans are celebrated "
     "in European specialty markets, and why Indian professionals deserve world-class purity at home."),
]

LINKEDIN_SEO_KEYWORDS = (
    "coffee benefits, health benefits of coffee, coffee consumption, "
    "coffee market in India, instant coffee India, instant coffee brand, "
    "coffee for productivity, workplace coffee culture, premium coffee brands India, "
    "coffee industry trends"
)

COMMERCIAL_EMOTIONS = [
    ("RELIEF",    "the exhale moment — finally getting real coffee after years of filler"),
    ("PRIDE",     "choosing quality when everyone around you settles for cheap garbage"),
    ("AMBITION",  "fuelling your grind at 5am when the city is still asleep"),
    ("NOSTALGIA", "the real coffee taste your grandmother made before brands added chicory"),
    ("REBELLION", "refusing to be fooled by fake ingredients disguised as premium packaging"),
    ("JOY",       "the small daily luxury that costs less than a tapri chai"),
    ("FOCUS",     "clean energy that builds without the crash — real caffeine, real work"),
    # Psychology-backed additions
    ("CERTAINTY", "the quiet confidence of knowing exactly what is in the cup"),
    ("RITUAL",    "the deliberate first act of the day — not autopilot caffeine"),
    ("RESPECT",   "treating yourself as someone who deserves real ingredients"),
]

PRODUCTS = [
    "Ultra Blend",
    "Bold",
    "Purista",
    "Purica",
]

# ── 30 Viral content ideas rotating bank ─────────────────────────────────────

VIRAL_CONTENT_IDEAS = [
    "What is actually inside your instant coffee jar? (Ingredient label truth)",
    "I switched to pure coffee for 30 days. Here is what changed.",
    "Why most Indians are unknowingly drinking chicory every morning",
    "The Rs 18 vs Rs 180 coffee experiment — same caffeine, same quality?",
    "Real coffee vs adulterated coffee: a side-by-side taste test story",
    "Why freeze-dried coffee is different from regular instant coffee",
    "Agglomerated vs freeze-dried: which one should you buy?",
    "The ingredient your coffee brand never mentions on the label",
    "How to read a coffee label like an expert in 60 seconds",
    "Why premium instant coffee is not an oxymoron",
    "The Indian coffee adulterant problem that nobody is talking about",
    "3 signs your coffee has fillers (and how to check)",
    "What happens when you remove chicory from your morning coffee",
    "The real reason cafe coffee tastes different from home coffee",
    "How Purity Beans is built different: no preservatives, no artificial aroma",
    "Coffee gifting guide for people who actually care about quality",
    "Morning routine with pure coffee: a real Indian working professional story",
    "Why the best coffee in India costs Rs 18, not Rs 180",
    "Cold brew with instant coffee: does it actually work?",
    "The 80-year history of chicory in Indian coffee (and why it is still here)",
    "Corporate gifting: why premium coffee beats generic gifts every time",
    "What freeze-dried means and why it matters for your morning cup",
    "The coffee brand that prints what it does NOT add on the label",
    "Student life + real coffee: why Purity Beans makes sense at Rs 18",
    "Hotel and hospitality buyers: why gourmet instant coffee is the upgrade guests notice",
    "The difference between coffee you drink and coffee you experience",
    "Why Indian consumers are finally reading ingredient labels on coffee",
    "Distributor opportunity: the only pure instant coffee brand in your city",
    "How to make barista-quality coffee at home without any equipment",
    "The Purity Beans blind taste test: what real coffee lovers say",
    # Psychology-backed additions
    "Your morning coffee is the first decision you make about yourself",
    "It tastes bitter after two minutes — that is not normal",
    "The 15-second label test that ends the guessing",
    "Real coffee does not require a machine or a weekend",
    "Knowing exactly what is in the cup is the real upgrade",
]

# ── Scroll-stopping hooks bank ────────────────────────────────────────────────

VIRAL_HOOKS = [
    "You have been drinking chicory your entire life.",
    "What is actually inside your coffee jar?",
    "Real coffee lovers will understand this.",
    "Expensive cafe coffee is not the solution.",
    "That first sip that just does not taste right.",
    "Most instant coffee is not coffee at all.",
    "Your coffee brand is lying to you.",
    "I stopped buying branded coffee. Here is why.",
    "Rs 18 per cup. No chicory. No preservatives. No compromise.",
    "The ingredient on every label that nobody reads.",
    "If you care about what you drink, read this.",
    "Coffee without the filler finally exists in India.",
    "Everyone in your office is drinking adulterated coffee.",
    "The real reason your coffee does not taste like coffee.",
    "Indian brand. Nothing hidden. Everything on the label.",
    # Reverse-qualifier hooks — exclusion triggers curiosity + pre-qualifies
    "If you already drink single-origin coffee, skip this reel.",
    "This is not for people who enjoy chicory.",
    "Don't watch this if you're happy with your instant coffee.",
    "Real coffee is not for everyone. Scroll if that's you.",
    "If you've never read a coffee label, this will hurt.",
    # Psychology-backed additions
    "Your morning cup is the first decision you make about yourself.",
    "It tastes bitter after two minutes. That is not normal.",
    "You should not need a chemistry degree to trust your coffee.",
    "Real coffee does not leave a muddy aftertaste.",
    "The only claim that matters: nothing is hiding in this jar.",
    "Premium is not the price. Premium is what is missing from the jar.",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_day_number() -> int:
    """Founder day on the IST calendar, same day the content file is named for."""
    from content_generator.core.ist_dates import today_ist
    return (today_ist() - CONTENT_ENGINE_START_DATE).days


def get_todays_blog_topic(day: int) -> str:
    return BLOG_TOPIC_CLUSTERS[day % len(BLOG_TOPIC_CLUSTERS)]

def get_todays_viral_idea(day: int) -> str:
    return VIRAL_CONTENT_IDEAS[day % len(VIRAL_CONTENT_IDEAS)]

def get_todays_hook(day: int) -> str:
    return VIRAL_HOOKS[day % len(VIRAL_HOOKS)]


def pick(bank: list, day: int, offset: int = 0):
    """Return the bank item for this day, with optional offset for diversity."""
    return bank[(day + offset) % len(bank)]
