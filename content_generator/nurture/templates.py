"""
Nurture message templates — stage-triggered, segment-specific.

Every template has:
  - A short `subject` line (used as WhatsApp header or email subject)
  - A `body` with {placeholders} for personalisation
  - A `cta` — the one ask at the end of the message

Design principle: One message = one action. Never ask for two things.

Templates are indexed by (segment, stage) so the daily nurture step
can query: "Who moved to sample_sent yesterday?" → dispatch the right
template automatically.
"""
from __future__ import annotations


def _variety_box_url() -> str:
    """50g trial pack. There is no separate trial SKU; the Variety Box is 4×50g."""
    try:
        from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, product_page_url
        return product_page_url(SHOPIFY_PRODUCTS["variety_box"])
    except Exception:
        return "https://p3online.in/products/variety-box"


_VARIETY_BOX_URL = _variety_box_url()

# ─────────────────────────────────────────────────────────────────────────────
# Template registry
# Key: (segment, stage)
# Value: {"subject": str, "body": str, "cta": str, "channel": "whatsapp"|"email"|"both"}
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES: dict[tuple[str, str], dict] = {

    # ── DISTRIBUTOR ───────────────────────────────────────────────────────────
    ("distributor", "inquiry"): {
        "subject": "Purity Beans — Partnership Opportunity in Your Region",
        "channel": "both",
        "body": (
            "Hi {name},\n\n"
            "Thank you for your interest in Purity Beans. Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\n"
            "We're currently expanding our distribution network in {region} and your profile looks like a strong fit.\n\n"
            "Purity Beans is priced at Rs 18/cup — positioned between commodity instant coffee and premium cafes, "
            "which means high velocity AND healthy margins for our partners.\n\n"
            "I'd love to share our distributor deck and discuss territory availability.\n\n"
            "Are you available for a 20-minute call this week?\n\n"
            "Warm regards,\nPurity Beans Team\n{website}"
        ),
        "cta": "Reply with your preferred call time",
    },

    ("distributor", "qualified"): {
        "subject": "Purity Beans Sample Pack Dispatching Soon",
        "channel": "both",
        "body": (
            "Hi {name},\n\n"
            "Great speaking with you! As discussed, we're sending across a sample pack so your team "
            "can experience Purity Beans firsthand.\n\n"
            "What's the best delivery address?\n\n"
            "Also attaching our distributor margin sheet — you'll see why our partners in Mumbai and Pune "
            "reordered within 45 days of their first stock.\n\n"
            "Looking forward to a long partnership,\nPurity Beans Team"
        ),
        "cta": "Reply with your delivery address",
    },

    ("distributor", "sample_sent"): {
        "subject": "Did the Purity Beans samples arrive?",
        "channel": "whatsapp",
        "body": (
            "Hi {name}, this is Purity Beans team.\n\n"
            "Your sample pack was dispatched on {dispatch_date}. "
            "It should have reached you by now!\n\n"
            "Would love to hear what you and your team think of the taste. "
            "Any feedback on the packaging too?\n\n"
            "Once you've tried it, let's talk numbers — we have 3 territory options still open in {region}."
        ),
        "cta": "Reply with your feedback",
    },

    ("distributor", "trial_order"): {
        "subject": "How's the Purity Beans trial stock moving?",
        "channel": "whatsapp",
        "body": (
            "Hi {name},\n\n"
            "It's been 2 weeks since your trial order went out. "
            "How's it moving off the shelves?\n\n"
            "Our partners typically see 60-70% sell-through in the first 3 weeks — "
            "consumers repurchase once they realise it's pure coffee for the same price as chicory blends.\n\n"
            "Ready to talk about a full stocking agreement? I can get the paperwork started this week."
        ),
        "cta": "Reply YES to schedule the agreement call",
    },

    ("distributor", "agreement"): {
        "subject": "Almost there — one step to activate your Purity Beans territory",
        "channel": "email",
        "body": (
            "Hi {name},\n\n"
            "Your distribution agreement is ready for final review. "
            "I'm attaching the signed copy for your records.\n\n"
            "Once you're active, you'll receive:\n"
            "  - Priority stock allocation every month\n"
            "  - Co-marketing assets (digital + print)\n"
            "  - Dedicated account manager contact\n"
            "  - 30-day payment terms after your first 3 months\n\n"
            "Please sign and return at your earliest convenience so we can activate your territory "
            "before the end of {month}.\n\n"
            "Excited to welcome you aboard,\nPurity Beans Team"
        ),
        "cta": "Sign and return the agreement",
    },

    ("distributor", "active"): {
        "subject": "Monthly performance update — {month}",
        "channel": "email",
        "body": (
            "Hi {name},\n\n"
            "Here's your Purity Beans performance snapshot for {month}:\n\n"
            "  - Units sold: {units_sold}\n"
            "  - Revenue: Rs {revenue}\n"
            "  - Top SKU: {top_sku}\n\n"
            "Next month we're launching a new variant — we'd love for you to be in the first batch.\n\n"
            "Your account manager will reach out with the pre-order details.\n\n"
            "Thank you for being a Purity Beans partner!\nPurity Beans Team"
        ),
        "cta": "Reply to pre-order the new variant",
    },

    # ── MODERN TRADE ──────────────────────────────────────────────────────────
    ("modern_trade", "inquiry"): {
        "subject": "Purity Beans — Category Proposal for {chain}",
        "channel": "email",
        "body": (
            "Dear {name},\n\n"
            "I'm reaching out regarding a listing opportunity for Purity Beans, "
            "positioned at Rs 18/cup. Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee.\n\n"
            "We believe Purity Beans can meaningfully grow your hot beverages category by capturing "
            "the consumer who has been choosing between commodity instant coffee and expensive cafe visits.\n\n"
            "I'd like to share our category deck and discuss a pilot listing in select stores.\n\n"
            "Would you be available for a 30-minute call this week?\n\n"
            "Best regards,\nPurity Beans Trade Team"
        ),
        "cta": "Reply to schedule a call",
    },

    ("modern_trade", "proposal_sent"): {
        "subject": "Following up on the Purity Beans category proposal",
        "channel": "email",
        "body": (
            "Dear {name},\n\n"
            "Sharing a quick follow-up on the category proposal sent earlier.\n\n"
            "Key highlights for {chain}:\n"
            "  - Rs 18/cup price point — highest margin per facing in the instant coffee shelf\n"
            "  - 40% repeat purchase rate in pilot stores (Pune, Q1 2026)\n"
            "  - Full in-store activation kit provided at no cost\n\n"
            "We're keen to move to a buyer meeting — please let me know your availability.\n\n"
            "Best regards,\nPurity Beans Trade Team"
        ),
        "cta": "Confirm a buyer meeting date",
    },

    ("modern_trade", "buyer_meeting"): {
        "subject": "Purity Beans pilot details — ready to go",
        "channel": "email",
        "body": (
            "Dear {name},\n\n"
            "Thank you for the productive meeting! As discussed, here is the pilot plan:\n\n"
            "  - Pilot stores: {pilot_stores}\n"
            "  - SKUs: Purity Beans 50g, 100g, 200g\n"
            "  - Trial period: 90 days\n"
            "  - Marketing support: shelf talkers + digital co-branding\n\n"
            "Please confirm the stores so we can schedule the activation visit.\n\n"
            "Looking forward to a successful pilot,\nPurity Beans Trade Team"
        ),
        "cta": "Confirm pilot store list",
    },

    ("modern_trade", "trial_listed"): {
        "subject": "Week {week_number} pilot performance — Purity Beans",
        "channel": "email",
        "body": (
            "Dear {name},\n\n"
            "Here's the week {week_number} performance update for the Purity Beans pilot at {pilot_stores}:\n\n"
            "  - Units sold: {units_sold}\n"
            "  - Velocity (units/store/week): {velocity}\n"
            "  - Shelf availability: {availability}%\n"
            "  - Consumer feedback: {feedback_summary}\n\n"
            "We're on track to meet the 90-day sell-through target. "
            "Shall we start the chain listing paperwork in parallel?\n\n"
            "Best,\nPurity Beans Trade Team"
        ),
        "cta": "Reply to begin chain listing paperwork",
    },

    # ── RETAILER ──────────────────────────────────────────────────────────────
    ("retailer", "inquiry"): {
        "subject": "Stock Purity Beans — Pure Coffee, Higher Margins",
        "channel": "whatsapp",
        "body": (
            "Hi {name},\n\n"
            "Namaste! This is Purity Beans team.\n\n"
            "We noticed your inquiry about stocking pure instant coffee. "
            "Purity Beans — Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee. The home cup is Rs 18.\n\n"
            "Your customers who ask for 'good coffee' will love it, and your margins will too.\n\n"
            "Can I send across a sample pack this week?"
        ),
        "cta": "Reply with your shop address if you want a sample pack",
    },

    ("retailer", "sample_sent"): {
        "subject": "Purity Beans samples on the way!",
        "channel": "whatsapp",
        "body": (
            "Hi {name}, Purity Beans here!\n\n"
            "Your sample pack is on its way — should reach {shop_name} by {eta}.\n\n"
            "Try a cup yourself — you'll see why our retailers in {city} reordered within a month.\n\n"
            "Once you've tried it, I'll share our wholesale pricing. The margins are the best you'll see "
            "in this category."
        ),
        "cta": "Reply 'TRIED' once you've had a cup",
    },

    ("retailer", "shelf_listed"): {
        "subject": "How's Purity Beans selling at {shop_name}?",
        "channel": "whatsapp",
        "body": (
            "Hi {name}!\n\n"
            "It's been 2 weeks since Purity Beans went on your shelf. "
            "How is it moving?\n\n"
            "Tip: customers who ask for 'coffee without chicory' are your best buyers — "
            "they'll become regulars once they find Purity Beans.\n\n"
            "Let me know if you need a top-up or want the 200g pack added."
        ),
        "cta": "Reply to place a reorder",
    },

    ("retailer", "reordering"): {
        "subject": "New SKU available — Purity Beans Cold Brew",
        "channel": "whatsapp",
        "body": (
            "Hi {name}, great news!\n\n"
            "We're launching Purity Beans Cold Brew concentrate — your summer bestseller candidate!\n\n"
            "As an existing retail partner, you get first access at introductory pricing.\n\n"
            "Interested in trying a case?"
        ),
        "cta": "Reply YES to get introductory pricing",
    },

    # ── CONSUMER ──────────────────────────────────────────────────────────────
    ("consumer", "lead"): {
        "subject": "Start with the 50g Variety Box",
        "channel": "whatsapp",
        "body": (
            "Hi {name}!\n\n"
            "You recently showed interest in Purity Beans. Bold, Purista, Purica, and Prima are 100% coffee with zero chicory. Ultra Blend is 70% coffee and 30% chicory.\n\n"
            f"The 50g trial jar pack is the Variety Box: {_VARIETY_BOX_URL}\n\n"
            "Four 50g jars, so you can taste the range before a full-size order. Delivery is across India."
        ),
        "cta": "Order the 50g Variety Box",
    },

    ("consumer", "first_purchase"): {
        "subject": "How did you like your Purity Beans?",
        "channel": "whatsapp",
        "body": (
            "Hi {name}!\n\n"
            "Hope you enjoyed your first cup of Purity Beans!\n\n"
            "If you loved it (we think you will), here's a 10% off code for your next order: PURE10\n\n"
            "Valid for 7 days. Order at: {website}/shop"
        ),
        "cta": "Use code PURE10 for 10% off",
    },

    ("consumer", "repeat_customer"): {
        "subject": "You're officially a Purity Beans regular!",
        "channel": "whatsapp",
        "body": (
            "Hi {name}!\n\n"
            "You've now ordered Purity Beans 3 times — you're officially part of the pure coffee movement!\n\n"
            "As a thank-you, here's free shipping on your next order (no minimum). Use code: PURE_FAN\n\n"
            "Also — would you be open to leaving us a quick Google review? It helps other coffee lovers "
            "find us. {review_link}"
        ),
        "cta": "Leave a review + use PURE_FAN for free shipping",
    },

    ("consumer", "loyal"): {
        "subject": "VIP early access — new Purity Beans variant",
        "channel": "whatsapp",
        "body": (
            "Hi {name}!\n\n"
            "As one of our most loyal customers, you get first access to our new variant "
            "before it goes live on the website.\n\n"
            "We're calling it Purity Beans Dark Roast — 20% stronger, same zero-chicory promise.\n\n"
            "Shall I reserve a pack for you?"
        ),
        "cta": "Reply YES to reserve your pack",
    },
}


def get_template(segment: str, stage: str) -> dict | None:
    """Return the nurture template for a given segment + stage, or None."""
    return TEMPLATES.get((segment, stage))


def render_template(
    segment: str,
    stage: str,
    **kwargs,
) -> dict | None:
    """
    Return the rendered template with all {placeholders} filled.

    kwargs: name, region, website, month, city, shop_name, etc.

    Safe — missing placeholders are left as-is (no KeyError).
    """
    tmpl = get_template(segment, stage)
    if not tmpl:
        return None

    # Provide sensible defaults so missing kwargs don't crash
    defaults = {
        "name":          "there",
        "region":        "your region",
        "website":       "https://p3online.in",
        "month":         "this month",
        "city":          "your city",
        "shop_name":     "your shop",
        "chain":         "your chain",
        "pilot_stores":  "selected stores",
        "week_number":   "1",
        "units_sold":    "—",
        "velocity":      "—",
        "availability":  "—",
        "feedback_summary": "positive",
        "dispatch_date": "recently",
        "eta":           "soon",
        "review_link":   "https://g.page/puritybeans",
        "top_sku":       "Purity Beans 100g",
        "revenue":       "—",
    }
    merged = {**defaults, **kwargs}

    try:
        rendered_body = tmpl["body"].format_map(merged)
    except (KeyError, ValueError):
        rendered_body = tmpl["body"]  # fallback: unrendered

    return {
        "subject": tmpl["subject"].format_map(merged),
        "body":    rendered_body,
        "cta":     tmpl["cta"].format_map(merged),
        "channel": tmpl["channel"],
        "segment": segment,
        "stage":   stage,
    }


def list_templates() -> list[dict]:
    """List all available templates — useful for dashboard/debug."""
    return [
        {"segment": seg, "stage": stg, "channel": tmpl["channel"], "subject": tmpl["subject"]}
        for (seg, stg), tmpl in TEMPLATES.items()
    ]
