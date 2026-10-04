"""
Purity Beans — brand configuration.

Single source of truth for brand identity, positioning, hashtags, and
content guardrails used across all content generation prompts.

Import from anywhere in the engine:
    from config.brand_config import BRAND, POSITIONING, HASHTAG_SETS
"""

# ── Core brand identity ───────────────────────────────────────────────────────

BRAND = {
    "name":        "Purity Beans",
    "company":     "Pure Pantry Provisions",
    "tagline":     "Read the jar. Bold, Purista, Purica, and Prima are 100% coffee. Ultra Blend is 70% coffee.",
    "category":    "Premium Instant Coffee",
    "origin":      "India",
    "website":     "https://p3online.in",
    "instagram":   "@puritybeans",
    "tone":        "premium but human, honest not corporate, Indian in DNA",
    "colors": {
        "background": "#0D0905",   # espresso dark
        "gold":       "#C8962E",   # signature gold
        "cream":      "#F5EED8",   # warm cream text
    },
}

# ── Market positioning ────────────────────────────────────────────────────────

POSITIONING = {
    "usp":              "Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.",
    "price_per_cup":    18,            # Rs
    "cafe_price":       180,           # Rs (average cafe latte)
    "price_ratio":      "10x cheaper than cafes",
    "purity_claim":     "Zero chicory applies to the 100% coffee jars. Ultra Blend is 70% coffee.",
    "target_segments": {
        "consumer":     "urban Indians 25-45 who care about what they drink",
        "distributor":  "FMCG distributors in Tier-1 and Tier-2 cities",
        "modern_trade": "supermarket buyers and category managers",
        "retailer":     "kirana stores and specialty food retailers",
    },
    "competitors_to_avoid_naming": ["Nescafé", "Bru", "Davidoff", "Continental"],
    "key_pain_points": [
        "Many instant coffees sold in India list chicory on the ingredient panel",
        "The ingredient list is the place to check for chicory",
        "Premium cafe quality is unaffordable daily",
        "No transparency about coffee purity on labels",
    ],
    "proof_points": [
        "Bold and Purista are 100% Robusta. Purica is freeze-dried 100% Arabica. Prima is 100% Arabica Premium Agglomerate.",
        "Ultra Blend is 70% coffee. A lower-caffeine description is allowed only for that jar.",
        "Rs 18 per cup vs Rs 180 at cafes",
    ],
}

# ── Hashtag sets by content type ──────────────────────────────────────────────

HASHTAG_SETS = {
    # Generic reel fallback
    "reels": (
        "#PurityBeans #PureCoffee #InstantCoffee #NoChicory #CoffeeLover "
        "#IndianCoffee #CoffeeIndia #PremiumCoffee #CoffeeReels "
        "#CoffeeOfTheDay #MorningCoffee"
    ),
    # Morning reel (7-9am slot) — used by generator.py → reels.build()
    "reel_morning": (
        "#PurityBeans #PureCoffee #MorningCoffee #CoffeeLover #InstantCoffee "
        "#NoChicory #IndianCoffee #CoffeeIndia #MorningRoutine #CoffeeTime"
    ),
    # Night reel (8-10pm slot) — used by generator.py → reels.build()
    "reel_night": (
        "#PurityBeans #PureCoffee #EveningCoffee #CoffeeLover #InstantCoffee "
        "#NoChicory #IndianCoffee #NightCoffee #CoffeeReels #CoffeeLovers"
    ),
    "viral_reel": (
        "#PurityBeans #NoChicory #CoffeeTruth #InstantCoffee #CoffeeLover "
        "#PureCoffee #IndianCoffee #CoffeeShorts #CoffeeReels #FoodFacts"
    ),
    "educational_reel": (
        "#PurityBeans #CoffeeFacts #InstantCoffee #PureCoffee #NoChicory "
        "#CoffeeEducation #IndianCoffee #CoffeeLover #KnowYourCoffee"
    ),
    "carousel": (
        "#PurityBeans #PureCoffee #InstantCoffee #NoChicory #CoffeeLover "
        "#IndianCoffee #PremiumCoffee #CoffeeCarousel #SaveThis #LearnWithCoffee"
    ),
    "linkedin": (
        "#PurityBeans #D2CBrand #FoodBusiness #IndianStartup #PureCoffee "
        "#CPGIndia #FMCGIndia #BrandBuilding #Entrepreneurship"
    ),
    "instagram": (
        "#PurityBeans #PureCoffee #InstantCoffee #NoChicory #CoffeeLover "
        "#IndianCoffee #CoffeeIndia #MorningBrew #CoffeeDaily"
    ),
    "story": (
        "#PurityBeans #PureCoffee #InstantCoffee #NoChicory #CoffeeLover"
    ),
    "blog": (
        "purity beans, pure instant coffee, no chicory coffee, "
        "instant coffee india, 100% arabica instant coffee"
    ),
    "b2b": (
        "#PurityBeans #DistributorOpportunity #FMCGIndia #CPGIndia "
        "#InstantCoffee #B2BCoffee #IndianBrand"
    ),
}

# ── Content guardrails ────────────────────────────────────────────────────────

BANNED_PHRASES = [
    "transform your mornings",
    "elevate your experience",
    "perfect cup",
    "fuel your day",
    "game changer",
    "level up",
    "discover the difference",
    "premium quality",
    "best coffee",
    "world class",
    "unmatched quality",
    "superior taste",
    "crafted with care",
    "passion for coffee",
    "artisanal",
    "small batch",         # only if untrue
    "sustainable",         # only if unverified
]

REQUIRED_ELEMENTS = {
    "every_post":   ["brand name mention", "zero chicory claim OR price mention"],
    "reel":         ["hook in first 3 seconds", "CTA at end"],
    "carousel":     ["save-worthy information", "slide 1 stops the scroll"],
    "linkedin":     ["business angle", "distributor/retailer relevance"],
    "blog":         ["keyword in title", "purity claim", "shop CTA"],
}

# ── Business targets ──────────────────────────────────────────────────────────

BUSINESS_TARGETS = {
    "monthly_revenue_inr":    500_000,    # Rs 5L/month target
    "daily_orders_target":    50,
    "avg_order_value_inr":    350,
    "distributor_target":     5,          # active distributors
    "retailer_target":        50,         # retail outlets
    "content_pieces_per_day": 6,          # reels + carousel + linkedin + blog + stories + yt
}

# ── Shopify Product Catalog (Source of Truth for Jars & Pricing) ───────────────
try:
    from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, get_product
    PRODUCT_CATALOG = SHOPIFY_PRODUCTS
except Exception:
    PRODUCT_CATALOG = {}

