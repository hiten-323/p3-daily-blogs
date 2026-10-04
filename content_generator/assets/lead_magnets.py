"""
Lead magnets — the REAL resources a value-unlock reel gives away.

The value-unlock mechanic ("comment GUIDE and I'll send it") only works if the
thing actually exists and is worth having. These are ready-to-send resources
the founder pastes into a DM/comment reply when someone comments the keyword.

Each has: a keyword (what people comment), a promise (what the reel offers),
and the deliverable (what you send back). Keep the deliverable genuinely
useful — that is what converts a follow into trust.

Delivery is MANUAL by the founder (Policy #001: no mass auto-DM tools). At low
follower counts a personal reply converts far better than automation anyway.
"""

LEAD_MAGNETS = [
    {
        "keyword": "CHICORY",
        "promise": "how to read a jar and see whether chicory is listed",
        "deliverable": (
            "Check the label, not a kitchen experiment:\n"
            "1. Read the ingredient list. Chicory is named when it is in the jar.\n"
            "2. 'Coffee-chicory mix' means chicory is in that jar.\n"
            "3. Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. "
            "Ultra Blend is 70% coffee.\n"
            "See the jars: p3online.in"
        ),
    },
    {
        "keyword": "GUIDE",
        "promise": "the Pure Coffee Buyer's Guide — read any label like an expert",
        "deliverable": (
            "Pure Coffee Buyer's Guide (India):\n"
            "- 'Coffee-chicory mix' = it has chicory, however small the print.\n"
            "- Look for chicory on the ingredient list. If it is named, it is in the jar.\n"
            "- '100% coffee' has to name the jar. Purity Beans Bold, Purista, Purica, and Prima are 100% coffee.\n"
            "- Purica is freeze-dried 100% Arabica. Prima is Premium Agglomerate 100% Arabica, not freeze-dried.\n"
            "- Bold and Purista are 100% Robusta. Ultra Blend is 70% coffee.\n"
            "- Price is not proof of what is in the jar. The label is.\n"
            "Purity Beans prints the jar facts at p3online.in"
        ),
    },
    {
        "keyword": "BREW",
        "promise": "the barista method for cafe-quality coffee at home in 2 minutes",
        "deliverable": (
            "2-Minute Barista Method (no machine):\n"
            "1. 1 heaped tsp Purity Beans in a cup.\n"
            "2. Add 2 tsp hot (not boiling) water + 1 tsp sugar if you like it sweet.\n"
            "3. Whisk/spoon-beat 40 seconds until pale and creamy.\n"
            "4. Add hot milk or water. The beaten paste floats up as a foam layer.\n"
            "Cafe texture, Rs 18 a cup. Get the coffee: p3online.in"
        ),
    },
    {
        "keyword": "GIFT",
        "promise": "the corporate gifting rate card + which variant suits which client",
        "deliverable": (
            "Purity Beans Corporate Gifting:\n"
            "- Purista / Purica gourmet jars = premium client & festival gifting.\n"
            "- Ultra Blend = bulk office pantry, everyday crowd-pleaser.\n"
            "- Bold = for the serious-coffee clients who notice quality.\n"
            "Custom hampers and bulk rates available. Reply here or visit p3online.in "
            "and mention 'corporate gifting'."
        ),
    },
    {
        "keyword": "MATCH",
        "promise": "which Purity Beans variant matches how YOU drink coffee",
        "deliverable": (
            "Find your match:\n"
            "- 100% Robusta, freeze-dried granules -> PURISTA\n"
            "- 100% Robusta, agglomerated -> BOLD\n"
            "- Freeze-dried 100% Arabica -> PURICA\n"
            "- Premium Agglomerate, 100% Arabica -> PRIMA\n"
            "- 70% coffee, the jar a lower-caffeine description fits -> ULTRA BLEND\n"
            "Tell me how you drink it and I'll confirm. Shop: p3online.in"
        ),
    },
    {
        "keyword": "COST",
        "promise": "the real math on what your daily coffee costs per year",
        "deliverable": (
            "Your coffee math:\n"
            "- Cafe cup ~Rs 180 x 300 days = ~Rs 54,000/year\n"
            "- Purity Beans at home ~Rs 18 a cup = ~Rs 5,400/year\n"
            "- Those two prices are the comparison. Do not assume every jar has the same caffeine: Ultra Blend is 70% coffee.\n"
            "Do the math on your own habit — then see p3online.in"
        ),
    },
    {
        "keyword": "STORE",
        "promise": "how to store instant coffee so it never goes flat",
        "deliverable": (
            "Keep coffee fresh:\n"
            "1. Airtight, always — oxygen kills aroma faster than time.\n"
            "2. Cool + dark cupboard. NOT the fridge (moisture ruins granules).\n"
            "3. Dry spoon only. One wet spoon clumps the whole jar.\n"
            "4. Buy a size you'll finish in 6-8 weeks.\n"
            "Purity Beans jars are sealed to hold aroma: p3online.in"
        ),
    },
    {
        "keyword": "SWAP",
        "promise": "the 7-day swap plan to move off chicory coffee without missing it",
        "deliverable": (
            "7-day swap (so the taste change never jolts you):\n"
            "Day 1-2: your usual, but half a spoon less.\n"
            "Day 3-4: half your usual + half Purity Beans in the same cup.\n"
            "Day 5-6: mostly a 100% coffee Purity Beans jar (not Ultra Blend).\n"
            "Day 7: a full cup of that jar. Ultra Blend is 70% coffee, so do not call it zero chicory.\n"
            "Start the swap: p3online.in"
        ),
    },
]


def get_todays_lead_magnet(day: int) -> dict:
    """
    Today's offer — biased toward keywords that have historically earned the
    most comments/follows, once the learning loop has data (else round-robin).
    """
    ranked = _ranked_by_performance()
    if ranked:
        # Rotate within the proven top half so winners repeat without going stale
        top = ranked[: max(1, len(ranked) // 2)]
        by_kw = {m["keyword"]: m for m in LEAD_MAGNETS}
        pool = [by_kw[k] for k in top if k in by_kw]
        if pool:
            return pool[day % len(pool)]
    return LEAD_MAGNETS[day % len(LEAD_MAGNETS)]


def _ranked_by_performance() -> list[str]:
    """Keywords ordered best-first by real engagement, from the learning log."""
    try:
        from content_generator.core.learning_engine import _load_log, _engagement_score
        scores: dict[str, list] = {}
        for e in _load_log():
            kw = (e.get("lead_magnet") or "").strip().upper()
            if kw and e.get("metrics"):
                scores.setdefault(kw, []).append(_engagement_score(e["metrics"])[1])
        avg = {k: sum(v) / len(v) for k, v in scores.items() if v}
        return [k for k, _ in sorted(avg.items(), key=lambda x: x[1], reverse=True)]
    except Exception:
        return []
