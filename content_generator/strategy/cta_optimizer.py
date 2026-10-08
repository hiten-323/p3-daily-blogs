"""
CTA optimizer — selects the highest-converting call-to-action for a given
objective and audience segment.

Sources ranked by priority:
  1. Measured click-through + conversion rate from cta_performance table
  2. Business-priority-weighted defaults
  3. Static fallback copy

Feed real data:
    from content_generator.analytics.metrics_store import record_cta_click
    record_cta_click("Buy at p3online.in", objective="Consumer Purchase",
                     audience="consumer", converted=True, revenue=450)
"""
import logging

logger = logging.getLogger(__name__)

# Default CTA copy per (objective, audience) — used until live data accumulates
_DEFAULT_CTAS: dict[tuple[str, str], list[str]] = {
    ("Follower Growth",         "consumer"):     [
        "Follow @puritybeans so you never drink roasted root again",
        "Follow — tomorrow I'll show you how to read the back of a coffee label",
        "Follow for daily pure coffee truths Big Coffee hides",
        "Follow Hiten Jain for unfiltered coffee science",
    ],
    ("FOLLOW",                  "consumer"):     [
        "Follow @puritybeans so you never drink roasted root again",
        "Follow — tomorrow I'll show you how to read the back of a coffee label",
        "Follow for daily pure coffee truths Big Coffee hides",
        "Follow Hiten Jain for unfiltered coffee science",
    ],
    ("DISCOVERY",               "consumer"):     [
        "Send this to someone who drinks instant coffee",
        "Share this with a coffee lover who deserves better",
        "Pass this to anyone who buys commercial coffee jars",
    ],
    ("AUTHORITY",               "consumer"):     [
        "Save this before your next grocery run",
        "Bookmark this quick reference guide",
        "Save this so you have it when checking coffee ingredients",
    ],
    ("COMMUNITY",               "consumer"):     [
        "Which one would you pick? Comment below",
        "Have you checked the back of your coffee jar? Tell us below",
        "Drop a coffee emoji if you only drink 100% pure beans",
    ],
    ("CONVERSION",              "consumer"):     [
        "Buy at p3online.in — Rs 18 per cup, free delivery",
        "Order 100% pure coffee at p3online.in",
        "Try Purity Beans → p3online.in",
    ],
    ("Consumer Purchase",       "consumer"):     [
        "Buy at p3online.in — Rs 18 per cup, free delivery",
        "Order now at p3online.in",
        "Try Purity Beans → p3online.in",
    ],
    ("Consumer Purchase",       "retailer"):     [
        "Stock Purity Beans — WhatsApp for wholesale pricing",
        "Retail enquiries: WhatsApp us now",
    ],
    ("Distributor Acquisition", "distributor"):  [
        "DM for distribution partnership in your region",
        "Become a Purity Beans distributor — DM now",
        "Distribution enquiry: call or WhatsApp us",
    ],
    ("Retailer Lead Gen",       "retailer"):     [
        "Get Purity Beans on your shelf — WhatsApp for pricing",
        "Retail partnership enquiry → WhatsApp us",
    ],
    ("Website Traffic",         "consumer"):     [
        "Read the full story at p3online.in",
        "More at p3online.in/blog",
    ],
    ("Brand Awareness",         "consumer"):     [
        "Follow for daily coffee truth",
        "Share with a coffee lover",
        "Tag someone who drinks fake coffee",
    ],
    ("Engagement Growth",       "consumer"):     [
        "Share this — someone you know is drinking chicory right now",
        "Tag a coffee lover who needs to see this",
        "Save this for the next time someone argues about coffee",
    ],
}

_FALLBACK_CTA = "Follow @puritybeans for daily pure coffee truths"


def get_best_cta(
    objective: str,
    audience: str  = "consumer",
    day: int       = 0,
) -> str:
    """
    Return the best CTA for given objective + audience.

    Uses measured conversion rate when available (>= 5 clicks).
    Falls back to priority-ordered defaults otherwise.
    """
    # Try data-driven selection first
    data_cta = _get_data_driven_cta(objective, audience)
    if data_cta:
        return data_cta

    # Fallback to defaults with day-based rotation
    key = (objective, audience)
    options = _DEFAULT_CTAS.get(key)
    if not options:
        # Check normalized / alias
        obj_upper = str(objective or "").upper()
        if "FOLLOW" in obj_upper:
            options = _DEFAULT_CTAS.get(("FOLLOW", audience))
        elif "DISCOVERY" in obj_upper:
            options = _DEFAULT_CTAS.get(("DISCOVERY", audience))
        elif "AUTHORITY" in obj_upper:
            options = _DEFAULT_CTAS.get(("AUTHORITY", audience))
        elif "COMMUNITY" in obj_upper:
            options = _DEFAULT_CTAS.get(("COMMUNITY", audience))
        elif "CONVERT" in obj_upper or "PURCHASE" in obj_upper:
            options = _DEFAULT_CTAS.get(("CONVERSION", audience))

    if not options:
        options = _DEFAULT_CTAS.get((objective, "consumer"), [_FALLBACK_CTA])

    return options[day % len(options)]


def _get_data_driven_cta(objective: str, audience: str) -> str:
    """Return the highest-converting measured CTA, or empty string if none."""
    try:
        from content_generator.analytics.metrics_store import get_cta_performance
        rows = get_cta_performance(min_clicks=5)
        # Filter by objective + audience
        relevant = [
            r for r in rows
            if r.get("objective") == objective and r.get("audience") == audience
        ]
        if relevant:
            # Already sorted by conv_rate DESC in get_cta_performance
            return relevant[0]["cta_text"]
    except Exception as _e:
        logger.debug("[cta_optimizer] optional step failed: %s", _e)
    return ""


def get_all_ctas_for_objective(objective: str, audience: str = "consumer") -> list[str]:
    """Return all CTA options for an objective — useful for A/B testing."""
    key = (objective, audience)
    return list(_DEFAULT_CTAS.get(key, [_FALLBACK_CTA]))
