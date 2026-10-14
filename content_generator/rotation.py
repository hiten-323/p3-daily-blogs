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
    "how to read an instant coffee label in India — bean, process, and which Purity Beans jar fits your cup",
    "coffee cost at home India — Ultra Blend makes at least 50 cups per 100g jar (about ₹6 a cup); no per-cup figure for other jars",
    "work from home coffee India — a repeatable home cup, not a productivity study",
    "caffeine on the label — Ultra Blend is 70% coffee and may be called lower caffeine; the pure coffee jars may not",
    "instant coffee jars in India — Bold, Purista, Purica, Prima, and Ultra Blend, each described only as labeled",
    "which Purity Beans jar to take before a workout — name the jar, no jitter or fat-loss claims",
    "how Purity Beans labels its jars — Bold, Purista, Purica, Prima, and Ultra Blend",
    "arabica vs robusta instant coffee in India — Purica and Prima are pure Arabica; Purista is pure Robusta. Bold is pure coffee",
    "coffee gifting India — variety box and duo jars, with the Ultra Blend jar called out as 70% coffee",
    "glass jar instant coffee in India — what is printed on a Purity Beans jar",
    "pure coffee jars vs Ultra Blend at 70% coffee — when a lower-caffeine description is allowed",
    "cold brew at home India — a method using a named Purity Beans jar",
    "coffee culture India — from filter kaapi to instant, without invented market statistics",
    "Ultra Blend, 70% coffee and 30% chicory — the smooth milk-coffee tradition, told honestly",
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
    ("SENSORY",        "Name the exact aroma or taste note of today's jar — a private test the viewer can run tomorrow"),
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
     "Robusta (low altitude, double the chlorogenic acid and caffeine, thick persistent crema like Purista). "
     "How each bean shows up in the cup."),
    ("BREWING THERMODYNAMICS",
     "Why boiling water (100°C) destroys coffee: the chemistry of tannin extraction. How water between "
     "80°C and 85°C extracts sweet aromatic compounds without scorching, yielding natural cup sweetness without sugar."),
    ("WATER CHEMISTRY IN EXTRACTION",
     "98% of your morning brew is water. How Total Dissolved Solids (TDS), calcium, and magnesium dictate "
     "aroma solubility, and why office tap water produces bitter coffee regardless of the brand."),

    # ── Clean-Label Awareness & Industry Transparency ──
    ("THE 70/30 MILK COFFEE TRADITION",
     "Why a coffee-chicory blend like Ultra Blend (70% coffee, 30% chicory) suits the South Indian milk-coffee "
     "cup: body, roundness, and honest labelling of the ratio."),
    ("LABEL LITERACY FOR EXECUTIVES",
     "How to read an Indian food label in 10 seconds: bean, process, net weight and storage. "
     "Why ingredient hierarchy matters and how front-of-pack claims obscure back-of-pack reality."),
    ("THE LABEL-READING HABIT",
     "Indian consumers read olive oil, milk and protein labels closely. The same 10-second habit tells you "
     "the bean, the process and the ratio in your coffee jar."),
    ("CLEAN-LABEL MANUFACTURING",
     "What it actually takes to build a zero-compromise clean food brand in India: sourcing certified pure beans, "
     "refusing artificial flow agents, and rejecting artificial aromas."),

    # ── Cognitive Performance & Executive Chronobiology ──
    ("CAFFEINE CHRONOBIOLOGY",
     "Adenosine receptor dynamics: why drinking coffee within 15 minutes of waking impairs cortisol awakening "
     "and creates the dreaded 2 PM crash. The science of delaying caffeine 60-90 minutes for sustained deep work."),
    ("CLEAN CAFFEINE VS JITTERS",
     "The biochemical reason some coffee causes jitters and stomach acid: over-hot water and over-dosing "
     "vs clean, gently processed pure coffee that fuels calm, razor-sharp focus."),
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
     "Building Pure Pantry Provisions without VC capital: why sticking to glass jars and clear labels is harder in year one "
     "but creates an unbreakable moat in year five."),
    ("COFFEE VALUE MATH",
     "The honest economics of the daily cup: Ultra Blend at about ₹6 a cup (100g = ₹309, at least 50 cups) vs a cafe cup at commercial "
     "chains. Calculating the 5-year compounding cost of routine coffee spending."),
    ("THE INDIAN COFFEE REVIVAL",
     "From the legendary Bababudan hills of Chikmagalur and Coorg: why India's shade-grown beans are celebrated "
     "in European specialty markets, and why Indian professionals deserve world-class purity at home."),
]

# ── Platform-Dedicated Semantic Angle Banks (Semantic Anti-Cannibalization) ──
FACEBOOK_ANGLES = [
    ("FAMILY KITCHEN TRUTH",
     "The family morning cup: how to match a Purity Beans jar to how your household drinks coffee, "
     "strong and black, with milk, or the smooth 70/30 Ultra Blend milk coffee."),
    ("MORNING HOME MATH",
     "Ultra Blend at about ₹6 a cup: what a milk-coffee family spends in a year, from one verified jar price."),
    ("THE FILTER KAAPI DEBATE",
     "Traditional South Indian filter coffee vs pure instant: why true coffee lovers care about what is printed under the brand name."),
    ("SUGAR COPING HABIT",
     "Why most people need 3 spoons of sugar in instant coffee: try the 85°C water and one level spoon first, then decide."),
    ("MOTHERS AND GRANDMOTHERS TEST",
     "Checking the kitchen shelf: what the back of a Purity Beans glass jar tells you in ten seconds."),
    ("WEEKEND HOSTING RITUAL",
     "Serving guests real coffee instead of vending powder: the subtle hospitality difference people remember."),
]

THREADS_ANGLES = [
    ("UNPOPULAR OPINION ON SUGAR",
     "Most people add sugar to fix water that was too hot. Let it cool 30 seconds first."),
    ("FRONT VS BACK OF JAR",
     "Big Coffee spends millions on the front of the jar so you don't look at the tiny print on the back."),
    ("THE 100C WATER MISTAKE",
     "Boiling water burns coffee in 5 seconds. Let it cool for 60 seconds and the bitterness disappears."),
    ("GRANULE TELLS",
     "Crystals mean freeze dried, fine powder means spray dried. Tip some into your palm before the water goes in."),
    ("INSTANT COFFEE SNOBBERY",
     "Specialty cafes convinced you instant coffee is inherently trash. Bad instant is trash. Freeze-dried pure Arabica at -40°C is pure science."),
    ("THE INGREDIENT LIST TEST",
     "Turn your jar around. The bean and the process tell you how the cup will taste."),
]

YOUTUBE_ANGLES = [
    ("WATER TEMPERATURE EXPERIMENT",
     "Brewing instant coffee at 100°C vs 85°C: visual extraction test and why boiling destroys natural sweetness."),
    ("COLD WATER DISSOLUTION TEST",
     "Freeze-dried Purica in cold water: watch the crystals dissolve and what that says about the process."),
    ("FREEZE DRIED VS SPRAY DRIED",
     "The geometric crystal structure of -40°C freeze-dried crystals vs burnt spray-dried dust under close-up macro lens."),
    ("CAFE CUP VS HOME CUP",
     "Blind taste comparison: a cafe cup vs a Purica home brew (no per-cup price claims)."),
]

LINKEDIN_SEO_KEYWORDS = (
    "coffee benefits, health benefits of coffee, coffee consumption, "
    "coffee market in India, instant coffee India, instant coffee brand, "
    "coffee for productivity, workplace coffee culture, premium coffee brands India, "
    "coffee industry trends"
)

COMMERCIAL_EMOTIONS = [
    ("RELIEF",    "the exhale moment — a cup that tastes the same good way every morning"),
    ("PRIDE",     "choosing a jar you actually understand"),
    ("AMBITION",  "fuelling your grind at 5am when the city is still asleep"),
    ("NOSTALGIA", "the smell of the morning cup in your grandmother's kitchen"),
    ("REBELLION", "keeping it simple: one jar, one spoon, one honest label"),
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
    "Arabica, Robusta or a 70/30 blend: which cup are you?",
    "One 100g jar of Ultra Blend, at least 50 cups: the home milk-coffee math",
    "Purica vs Purista: a side-by-side taste test story",
    "Why freeze-dried coffee is different from regular instant coffee",
    "Agglomerated vs freeze-dried: which one should you buy?",
    "The ingredient your coffee brand never mentions on the label",
    "How to read a coffee label like an expert in 60 seconds",
    "Why premium instant coffee is not an oxymoron",
    "The 30-second water pause that changes your cup",
    "3 things the back of a coffee jar tells you",
    "Why South India loves a 70/30 coffee-chicory milk coffee",
    "The real reason cafe coffee tastes different from home coffee",
    "How Purity Beans is built different: no preservatives, no artificial aroma",
    "Coffee gifting guide for people who actually care about quality",
    "Morning routine with pure coffee: a real Indian working professional story",
    "Why a good home cup does not need a machine",
    "Cold brew with instant coffee: does it actually work?",
    "The history of the coffee-chicory milk coffee in South India",
    "Corporate gifting: why premium coffee beats generic gifts every time",
    "What freeze-dried means and why it matters for your morning cup",
    "The coffee brand that prints what it does NOT add on the label",
    "Student life + real coffee: a two-minute Purity Beans cup",
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
    "Crystals or powder? Check your jar.",
    "What is actually inside your coffee jar?",
    "Real coffee lovers will understand this.",
    "Expensive cafe coffee is not the solution.",
    "That first sip that just does not taste right.",
    "Instant coffee can taste like this.",
    "Your water is too hot. Here is the fix.",
    "I stopped buying branded coffee. Here is why.",
    "Two minutes, one spoon, a lead-free glass jar.",
    "The ingredient on every label that nobody reads.",
    "If you care about what you drink, read this.",
    "Freeze-dried Arabica, at home, in two minutes.",
    "Your office pantry deserves a better jar.",
    "The real reason your coffee does not taste like coffee.",
    "Indian brand. Nothing hidden. Everything on the label.",
    # Reverse-qualifier hooks — exclusion triggers curiosity + pre-qualifies
    "If you already drink single-origin coffee, skip this reel.",
    "This is for people who take their morning cup seriously.",
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
