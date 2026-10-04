"""
Adaptive Hashtag Bank — hashtags evolve monthly based on real performance.

Instead of a fixed 25-tag set:
  - Maintain a bank of 300+ hashtags across 5 tiers
  - Attribute each published post's engagement to the hashtags it used
  - Score = weighted engagement per use (follows > shares > saves > comments)
  - select_hashtags() returns today's 25: proven winners + exploration slots
  - Weak tags naturally stop being selected; strong ones get used more

Scores persist in output/learning/hashtag_scores.json (committed by CI).
"""
from __future__ import annotations
import json
import logging
import os

logger = logging.getLogger(__name__)

_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_SCORES_PATH  = os.path.join(_LEARNING_DIR, "hashtag_scores.json")

# ── The bank: ~300 hashtags across 5 tiers ────────────────────────────────────

BANK = {
    # Tier 1 — BROAD (1M+ posts): raw reach, high competition
    "broad": [
        "#Coffee", "#CoffeeLover", "#CoffeeTime", "#CoffeeAddict", "#CoffeeLovers",
        "#Cafe", "#Espresso", "#CoffeeShop", "#CoffeeBreak", "#Barista",
        "#MorningCoffee", "#CoffeeGram", "#InstaCoffee", "#CoffeeLife", "#CoffeeCulture",
        "#Foodie", "#FoodPhotography", "#Drinks", "#MorningRoutine", "#Breakfast",
        "#CoffeeArt", "#LatteArt", "#CoffeeDaily", "#CoffeeLove", "#CafeLife",
        "#CoffeeBean", "#CoffeeBeans", "#CoffeeHolic", "#CoffeeMug", "#CoffeeCup",
        "#Caffeine", "#CaffeineAddict", "#CoffeeIsLife", "#CoffeeFirst", "#ButFirstCoffee",
        "#CoffeeOClock", "#CoffeePlease", "#CoffeeVibes", "#CoffeeMood", "#CoffeeSesh",
    ],
    # Tier 2 — NICHE (100K-1M): targeted coffee community
    "niche": [
        "#InstantCoffee", "#PremiumCoffee", "#PureCoffee", "#GourmetCoffee", "#SpecialtyCoffee",
        "#GlassJar", "#BlackCoffee", "#CoffeeConnoisseur", "#CoffeeSnob", "#ThirdWaveCoffee",
        "#HomeBarista", "#HomeBrewing", "#CoffeeAtHome", "#CoffeeBrewing", "#PourOver",
        "#ColdBrew", "#ColdCoffee", "#IcedCoffee", "#FrenchPress", "#Aeropress",
        "#CoffeeRoasters", "#FreshCoffee", "#ArtisanCoffee", "#CraftCoffee", "#ReadTheLabel",
        "#CoffeeEducation", "#CoffeeFacts", "#CoffeeTips", "#CoffeeScience", "#CoffeeKnowledge",
        "#CoffeeReview", "#CoffeeTasting", "#CoffeeExperience", "#RealCoffee", "#QualityCoffee",
        "#CleanCoffee", "#DailyBrew", "#JarCoffee", "#NaturalCoffee", "#NoAddedSugar",
    ],
    # Tier 3 — INDIAN (local discovery)
    "indian": [
        "#IndianCoffee", "#CoffeeIndia", "#MadeInIndia", "#IndianBrands", "#SupportIndianBrands",
        "#VocalForLocal", "#IndianStartup", "#DesiCoffee", "#FilterCoffee", "#FilterKaapi",
        "#SouthIndianCoffee", "#MumbaiCoffee", "#DelhiCoffee", "#BangaloreCoffee", "#PuneCoffee",
        "#HyderabadFoodies", "#ChennaiCafe", "#IndianFoodie", "#IndiaFood", "#DesiFood",
        "#MadeInIndiaProducts", "#IndianProducts", "#SwadeshiProducts", "#AtmanirbharBharat", "#StartupIndia",
        "#IndianCafes", "#CoffeeCultureIndia", "#IndianCoffeeLovers", "#ChaiVsCoffee", "#KaapiTime",
        "#MorningIndia", "#IndianMornings", "#OfficeLifeIndia", "#WFHIndia", "#IndianYouth",
        "#CoorgCoffee", "#ChikmagalurCoffee", "#ArakuCoffee", "#IndianBeans", "#KarnatakaCoffee",
    ],
    # Tier 4 — DISCOVERY (10K-100K: small enough to rank in top posts)
    "discovery": [
        "#NoChicory", "#ChicoryFree", "#ZeroChicory", "#NoPreservatives", "#PreservativeFree",
        "#NoAdditives", "#CleanLabel", "#ReadTheLabel", "#IngredientTransparency", "#HonestFood",
        "#CoffeeWithoutChicory", "#PureInstantCoffee", "#CoffeeTruth", "#CoffeeMyths", "#CoffeeExposed",
        "#KnowYourCoffee", "#CoffeeLabel", "#WhatsInYourCoffee", "#CoffeeIngredients", "#TransparentBrand",
        "#AgglomeratedCoffee", "#CoffeeGranules", "#InstantCoffeeIndia", "#BestInstantCoffee", "#CoffeeUpgrade",
        "#CoffeeSwitch", "#BetterCoffee", "#CoffeeThatMatters", "#ConsciousConsumer", "#MindfulEating",
        "#FoodTransparency", "#LabelReading", "#SmartShopping", "#QualityOverQuantity", "#PremiumTaste",
        "#CoffeeGifting", "#CorporateGifting", "#GiftIdeasIndia", "#FestiveGifting", "#GourmetGifts",
    ],
    # Tier 5 — BRAND (owned, always included)
    "brand": [
        "#PurityBeans", "#PurityBeansCoffee", "#BrewPure", "#PureCoffeeExperience", "#PurityBeansExperience",
    ],
}

# How many of each tier make up the daily 25
_TIER_QUOTA = {"broad": 5, "niche": 5, "indian": 5, "discovery": 5, "brand": 5}

# Out of each non-brand tier's quota, how many slots explore unproven tags
_EXPLORE_SLOTS = 1


# ── Scoring ───────────────────────────────────────────────────────────────────

def _load_scores() -> dict:
    if not os.path.exists(_SCORES_PATH):
        return {}
    try:
        with open(_SCORES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_scores(scores: dict) -> None:
    os.makedirs(_LEARNING_DIR, exist_ok=True)
    with open(_SCORES_PATH, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2, ensure_ascii=False)


def record_post_hashtags(hashtags: str | list, metrics: dict) -> None:
    """
    Attribute a published post's engagement to every hashtag it used.
    Called by the insights fetcher when metrics arrive.

    Score per post = follows*10 + shares*5 + saves*4 + comments*3 + reach*0.005
    Each tag accumulates: uses += 1, total_score += post_score
    """
    if isinstance(hashtags, str):
        tags = [t for t in hashtags.split() if t.startswith("#")]
    else:
        tags = [str(t) for t in (hashtags or []) if str(t).startswith("#")]
    if not tags:
        return

    post_score = (
        metrics.get("follows_gained", 0) * 10.0
        + metrics.get("shares", 0)        * 5.0
        + metrics.get("saves", 0)         * 4.0
        + metrics.get("comments", 0)      * 3.0
        + metrics.get("reach", 0)         * 0.005
    )

    scores = _load_scores()
    for tag in tags:
        entry = scores.setdefault(tag, {"uses": 0, "total_score": 0.0})
        entry["uses"]        += 1
        entry["total_score"] += post_score
    _save_scores(scores)
    logger.info("[hashtags] Attributed score %.1f to %d tags", post_score, len(tags))


def _avg_score(tag: str, scores: dict) -> float | None:
    """Average engagement per use; None = unproven (never used)."""
    e = scores.get(tag)
    if not e or not e.get("uses"):
        return None
    return e["total_score"] / e["uses"]


# ── Selection ─────────────────────────────────────────────────────────────────

def select_hashtags(day: int = 0) -> str:
    """
    Return today's 25 hashtags as a space-joined string.

    Per non-brand tier: (quota - explore) proven best performers +
    explore slots cycling through unproven tags so every tag eventually
    gets tested. Brand tags are always all included.
    Falls back to deterministic rotation before any performance data exists.
    """
    scores  = _load_scores()
    chosen: list[str] = []

    for tier, quota in _TIER_QUOTA.items():
        pool = BANK[tier]
        if tier == "brand":
            chosen.extend(pool[:quota])
            continue

        proven   = [(t, _avg_score(t, scores)) for t in pool]
        ranked   = sorted((p for p in proven if p[1] is not None), key=lambda x: x[1], reverse=True)
        unproven = [t for t, s in proven if s is None]

        n_exploit = quota - _EXPLORE_SLOTS if unproven else quota
        picks = [t for t, _ in ranked[:n_exploit]]

        # Exploration: cycle unproven tags deterministically by day
        slots_left = quota - len(picks)
        if slots_left > 0:
            candidates = unproven or [t for t, _ in ranked[n_exploit:]] or pool
            for i in range(slots_left):
                picks.append(candidates[(day + i) % len(candidates)])

        # De-dup while preserving order
        seen = set(chosen)
        for t in picks:
            if t not in seen:
                chosen.append(t)
                seen.add(t)

    # Top up to exactly 25 if de-dup dropped any
    if len(chosen) < 25:
        for tier in ("discovery", "niche", "indian", "broad"):
            for t in BANK[tier]:
                if t not in chosen:
                    chosen.append(t)
                    if len(chosen) == 25:
                        break
            if len(chosen) == 25:
                break

    return " ".join(chosen[:25])


def get_bank_report() -> dict:
    """Summary of hashtag performance — for founder report / debugging."""
    scores = _load_scores()
    all_tags = [t for tier in BANK.values() for t in tier]
    scored = [(t, _avg_score(t, scores)) for t in all_tags]
    proven = sorted((p for p in scored if p[1] is not None), key=lambda x: x[1], reverse=True)
    return {
        "bank_size":     len(all_tags),
        "tested":        len(proven),
        "untested":      len(all_tags) - len(proven),
        "top_10":        [{"tag": t, "avg_score": round(s, 1)} for t, s in proven[:10]],
        "bottom_10":     [{"tag": t, "avg_score": round(s, 1)} for t, s in proven[-10:]] if len(proven) > 10 else [],
    }
