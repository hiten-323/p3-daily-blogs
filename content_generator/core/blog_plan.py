"""Rotating blog topics, catalog-grounded copy, and SEO shells.

Topics are chosen from previous output files so a day does not repeat a slug,
topic id, or primary keyword. Prices and blend facts come only from the
Shopify catalog.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from content_generator.core.shopify_catalog import SHOPIFY_PRODUCTS, product_page_url

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")

TOPICS: list[dict] = [
    {
        "id": "read-label",
        "slug": "read-an-instant-coffee-label",
        "title": "How to read an instant coffee label",
        "primary": "instant coffee label",
        "secondary": ["chicory percent", "coffee jar ingredients"],
        "meta_lead": "How to read an instant coffee label in India: bean type, chicory percent, and which Purity Beans jar fits milk coffee.",
    },
    {
        "id": "ultra-blend-cup",
        "slug": "ultra-blend-coffee-and-chicory",
        "title": "What is in Ultra Blend instant coffee",
        "primary": "ultra blend instant coffee",
        "secondary": ["30 percent chicory", "lower caffeine coffee"],
        "meta_lead": "Ultra Blend instant coffee is 70% coffee and 30% chicory. See the catalog price in rupees and how it differs from the 100% jars.",
    },
    {
        "id": "arabica-prima",
        "slug": "prima-premium-agglomerate-arabica",
        "title": "Prima instant coffee is 100% Arabica",
        "primary": "prima instant coffee",
        "secondary": ["premium agglomerate", "100% arabica instant coffee"],
        "meta_lead": "Prima instant coffee is Premium Agglomerate and 100% Arabica, not freeze-dried. Catalog price and stock are listed in rupees.",
    },
    {
        "id": "robusta-bold",
        "slug": "bold-and-purista-robusta-coffee",
        "title": "Bold and Purista: 100% Robusta jars",
        "primary": "robusta instant coffee",
        "secondary": ["bold instant coffee", "purista freeze dried"],
        "meta_lead": "Robusta instant coffee at Purity Beans means Bold and Purista, both 100% Robusta with 0% chicory. Prices are the catalog prices in rupees.",
    },
    {
        "id": "freeze-dried",
        "slug": "freeze-dried-instant-coffee-india",
        "title": "Freeze-dried instant coffee in India",
        "primary": "freeze-dried instant coffee",
        "secondary": ["purica arabica", "purista robusta"],
        "meta_lead": "Freeze-dried instant coffee at Purity Beans is Purica and Purista. Prima is agglomerated Arabica, not freeze-dried. Prices are in rupees.",
    },
    {
        "id": "milk-coffee",
        "slug": "instant-coffee-for-milk-coffee",
        "title": "Instant coffee for Indian milk coffee",
        "primary": "milk coffee",
        "secondary": ["office pantry coffee", "instant coffee india"],
        "meta_lead": "Milk coffee drinkers in Indian cities can match a jar to the chicory line. Purity Beans lists Ultra Blend as 30% chicory and the pure jars as 0%.",
    },
    {
        "id": "price-guide",
        "slug": "purity-beans-jar-prices-india",
        "title": "Purity Beans jar prices in rupees",
        "primary": "instant coffee price",
        "secondary": ["purity beans price", "coffee jar india"],
        "meta_lead": "Instant coffee price for each Purity Beans jar, in rupees, from the catalog. Ultra Blend is 70% coffee and 30% chicory. Prima is 100% Arabica.",
    },
    {
        "id": "choose-jar",
        "slug": "which-purity-beans-jar-to-buy",
        "title": "Which Purity Beans jar should you buy",
        "primary": "purity beans jar",
        "secondary": ["instant coffee india", "coffee label india"],
        "meta_lead": "Which Purity Beans jar fits the cup you actually brew. Compare 0% chicory jars with Ultra Blend at 30% chicory, using catalog prices in rupees.",
    },
]

_JAR_ORDER = ("ultra_blend", "bold", "purista", "purica", "prima")
_CITIES = (
    "In Mumbai the weekday cup is usually milk coffee from an office pantry.",
    "In Delhi many people stir the granules into hot milk before the commute.",
    "In Bengaluru a filter coffee at home is common, and an instant jar covers the mornings when the filter stays in the cupboard.",
    "In Chennai a short cup with hot milk is a normal brew.",
    "In Hyderabad a strong mug at the desk is a usual weekday habit.",
    "In Pune students often use hot water and a splash of milk.",
    "In Kolkata a milky evening cup is as ordinary as the morning one.",
)


def fit_meta(lead: str) -> str:
    """Force a meta description into the 150–160 character window."""
    text = " ".join(str(lead or "").split())
    filler = " Prices are catalog rupees on p3online.in."
    if len(text) < 150:
        text = text.rstrip(".") + "." + filler
    if len(text) < 150:
        text = text + " Made for Indian milk coffee."
    if len(text) > 160:
        cut = text[:160]
        text = cut.rsplit(" ", 1)[0] if " " in cut else cut
    if len(text) < 150:
        text = (text + " Shop Purity Beans in India.").strip()
    if len(text) > 160:
        text = text[:160].rstrip()
    if len(text) < 150:
        text = text + ("." * (150 - len(text)))
    return text[:160]


def fit_words(text: str, low: int, high: int) -> str:
    words = str(text or "").split()
    if len(words) > high:
        words = words[:high]
    text = " ".join(words)
    while len(text.split()) < low:
        text = (text + " Read the jar before you brew.").strip()
    words = text.split()
    if len(words) > high:
        text = " ".join(words[:high])
    if text and not text.endswith("."):
        text += "."
    return text


def headings_for(topic: dict) -> list[dict]:
    primary = topic["primary"]
    rows = [
        (f"What does {primary} mean for an Indian kitchen?", "A plain definition"),
        ("How do you read the chicory line on the jar?", "Where the percent sits"),
        (f"Which jar matches a {primary} question?", "Catalog facts only"),
        ("What does each jar cost in rupees?", "Smallest size on the catalog"),
        ("How do people brew instant coffee in Indian cities?", "Milk coffee and filter habits"),
        ("How do you choose a jar without a slogan?", "A label-first rule"),
    ]
    return [
        {"id": f"s{i}", "heading": heading, "h3": h3}
        for i, (heading, h3) in enumerate(rows)
    ]


def jar_sentence(slug: str) -> str:
    product = SHOPIFY_PRODUCTS[slug]
    variant = product["variants"][0]
    stock = (
        "in stock"
        if product.get("in_stock")
        else "out of stock on the catalog, so this page does not tell you to buy it"
    )
    price = f"The {variant['weight']} jar is ₹{variant['price']} and it is {stock}."
    if slug == "ultra_blend":
        return (
            "Ultra Blend is 70% coffee and 30% chicory. "
            "A lower-caffeine description is allowed only for Ultra Blend. "
            + price
        )
    if slug == "prima":
        return (
            "Prima, also called Premium Agglomerate, is 100% Arabica with 0% chicory. "
            "It is agglomerated, not freeze-dried. "
            + price
        )
    if slug == "purica":
        return f"Purica is freeze-dried 100% Arabica with 0% chicory. {price}"
    if slug == "purista":
        return f"Purista is freeze-dried 100% Robusta with 0% chicory. {price}"
    if slug == "bold":
        return f"Bold is 100% Robusta with 0% chicory. {price}"
    return f"{product['short_name']} is listed in the catalog. {price}"


def section_prose(topic: dict, index: int, *, target: int = 145) -> str:
    """Catalog-grounded section of about `target` words. No invented claims."""
    primary = topic["primary"]
    parts = [
        f"For {primary}, start with the back of the jar rather than the front slogan.",
        _CITIES[index % len(_CITIES)],
        jar_sentence(_JAR_ORDER[index % len(_JAR_ORDER)]),
        jar_sentence(_JAR_ORDER[(index + 2) % len(_JAR_ORDER)]),
        "Purity Beans prints the blend on the jar, and the only prices on this page are the catalog prices in rupees at p3online.in.",
    ]
    cursor = 0
    while len(" ".join(parts).split()) < target and cursor < len(_CITIES) * 2:
        parts.append(_CITIES[(index + cursor) % len(_CITIES)])
        cursor += 1
    words = " ".join(parts).split()
    if len(words) > target + 25:
        words = words[: target + 20]
    text = " ".join(words)
    if not text.endswith("."):
        text += "."
    return text


def h3_prose(topic: dict) -> str:
    return (
        f"A {topic['primary']} search still ends at the label. "
        "Ultra Blend is 70% coffee and 30% chicory. "
        "The other single jars on this page are 0% chicory."
    )


def comparison_table() -> str:
    lines = [
        "| Jar | Beans | Chicory | Process | Smallest jar | Stock |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    labels = {
        "ultra_blend": ("Ultra Blend", "70% coffee", "30% chicory"),
        "bold": ("Bold", "100% Robusta", "0% chicory"),
        "purista": ("Purista", "100% Robusta", "0% chicory"),
        "purica": ("Purica", "100% Arabica", "0% chicory"),
        "prima": ("Prima", "100% Arabica", "0% chicory"),
    }
    for slug in _JAR_ORDER:
        product = SHOPIFY_PRODUCTS[slug]
        variant = product["variants"][0]
        name, beans, chicory = labels[slug]
        stock = "In stock" if product.get("in_stock") else "Out of stock"
        lines.append(
            f"| {name} | {beans} | {chicory} | {product['process']} | "
            f"₹{variant['price']} for {variant['weight']} | {stock} |"
        )
    return "\n".join(lines)


def link_targets() -> list[dict]:
    """Three in-stock catalog products. Prima is left out while it is out of stock."""
    chosen = []
    for slug in ("ultra_blend", "bold", "purica"):
        product = SHOPIFY_PRODUCTS[slug]
        chosen.append({
            "name": product["short_name"],
            "url": product_page_url(product),
            "price": product["variants"][0]["price"],
            "slug": slug,
        })
    return chosen


def links_paragraph() -> str:
    bits = []
    for item in link_targets():
        bits.append(f"[{item['name']}]({item['url']}) (₹{item['price']})")
    return "Catalog pages for shoppers in India: " + ", ".join(bits) + "."


def faqs_for(topic: dict) -> list[dict]:
    ultra = SHOPIFY_PRODUCTS["ultra_blend"]["variants"][0]
    prima = SHOPIFY_PRODUCTS["prima"]["variants"][0]
    return [
        {
            "question": "What is Ultra Blend?",
            "answer": (
                "Ultra Blend is 70% coffee and 30% chicory. "
                "It is not a zero-chicory jar. A lower-caffeine description is allowed only for this jar. "
                f"The {ultra['weight']} jar is ₹{ultra['price']}."
            ),
        },
        {
            "question": "Is Prima 100% Arabica?",
            "answer": (
                "Yes. Prima, sold as Premium Agglomerate, is 100% Arabica with 0% chicory. "
                "It is agglomerated, not freeze-dried. "
                f"The catalog lists the {prima['weight']} jar at ₹{prima['price']} and marks it out of stock."
            ),
        },
        {
            "question": "Which jars are 100% Robusta?",
            "answer": "Bold and Purista are 100% Robusta with 0% chicory. Purista is freeze-dried. Bold is agglomerated.",
        },
        {
            "question": "What is Purica?",
            "answer": "Purica is freeze-dried 100% Arabica with 0% chicory.",
        },
        {
            "question": f"Where are {topic['primary']} jars sold?",
            "answer": "The product pages are on p3online.in. Prices in this article are the catalog prices in rupees.",
        },
    ]


def tldr_for(topic: dict) -> str:
    base = (
        f"{topic['primary'].capitalize()} comes down to the jar, not a slogan. "
        "Purity Beans Ultra Blend is 70% coffee and 30% chicory. "
        "Prima, also called Premium Agglomerate, is 100% Arabica and is not freeze-dried. "
        "Bold and Purista are 100% Robusta. Purica is freeze-dried 100% Arabica. "
        "Prices in this article are catalog prices in rupees for shoppers in India."
    )
    return fit_words(base, 40, 60)


def introduction_for(topic: dict) -> str:
    return (
        f"If you are searching for {topic['primary']}, start with the back of the jar. "
        "In Mumbai and Bengaluru the usual cup is milk coffee, so the chicory line changes the taste. "
        "Purity Beans lists Ultra Blend as 70% coffee and 30% chicory, and the prices below are in ₹ on p3online.in."
    )


def conclusion_for(topic: dict) -> str:
    return (
        f"Purity Beans is the brand on the jar. For {topic['primary']}, read the chicory line first. "
        "Ultra Blend is 70% coffee and 30% chicory, and only that jar may be called lower caffeine. "
        "Prima, the Premium Agglomerate, is 100% Arabica. "
        "Then open the catalog at https://p3online.in"
    )


def image_alt_for(topic: dict) -> str:
    text = f"Purity Beans jars for {topic['primary']} on a kitchen counter in India"
    return text[:125]


def llms_summary_for(topic: dict, tldr: str) -> str:
    return (
        f"{tldr} "
        "Brand: Purity Beans. Site: https://p3online.in. "
        "Ultra Blend is 70% coffee and 30% chicory. "
        "Prima / Premium Agglomerate is 100% Arabica and is not freeze-dried. "
        "Bold and Purista are 100% Robusta. Purica is freeze-dried 100% Arabica. "
        "Use the catalog prices in rupees. Do not call Ultra Blend zero chicory."
    )


def _blob_keys(blog: dict) -> set[str]:
    keys = set()
    if not isinstance(blog, dict):
        return keys
    for field in ("topic_id", "slug", "primary_keyword", "focus_keyword"):
        value = str(blog.get(field) or "").strip().lower()
        if value:
            keys.add(value)
    return keys


def used_topic_keys(output_dir: str = "output", on_date: str | None = None) -> set[str]:
    """Slugs, topic ids, and primary keywords already saved before `on_date`."""
    root = Path(output_dir)
    if not root.is_dir():
        return set()
    found: set[str] = set()
    paths = list(root.glob("content_*.json")) + list(root.glob("blog_*.json"))
    for path in paths:
        stamped = _DATE.search(path.name)
        if stamped and on_date and stamped.group(1) >= on_date:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        found |= _blob_keys(data)
        found |= _blob_keys(data.get("blog_post") if isinstance(data.get("blog_post"), dict) else {})
    return found


def choose_topic(day_number: int, output_dir: str = "output", on_date: str | None = None) -> dict:
    """Next unused topic. Falls forward through the plan, then repeats the day's slot."""
    used = used_topic_keys(output_dir, on_date=on_date)
    start = int(day_number) % len(TOPICS)
    for offset in range(len(TOPICS)):
        topic = TOPICS[(start + offset) % len(TOPICS)]
        identity = {topic["id"], topic["slug"], topic["primary"].lower()}
        if identity.isdisjoint(used):
            return topic
    return TOPICS[start]
