"""Tests for dedicated LinkedIn knowledge & brand awareness generation and publishing."""
from content_generator.prompts import linkedin
from content_generator.publisher.linkedin import _extract_post_text
from content_generator.rotation import LINKEDIN_ANGLES, WEBSITE_URL


def test_linkedin_angles_cover_coffee_science_and_knowledge():
    labels = [angle[0] for angle in LINKEDIN_ANGLES]
    assert "FREEZE-DRIED VS SPRAY-DRIED" in labels
    assert "ARABICA VS ROBUSTA BOTANY" in labels
    assert "BREWING THERMODYNAMICS" in labels
    assert "CHICORY ROOT ECONOMICS" in labels
    assert "CAFFEINE CHRONOBIOLOGY" in labels
    assert "CORPORATE PANTRY ROI" in labels


def test_linkedin_prompt_builds_knowledge_structure():
    angle = ("BREWING THERMODYNAMICS", "80C vs 100C water")
    avoid = "AVOID REPETITION"
    prompt = linkedin.build(angle, avoid, day=10)
    assert "KNOWLEDGE & AWARENESS PILLARS" in prompt
    assert "Hiten Jain, Founder of Pure Pantry Provisions" in prompt
    assert "Freeze-drying" in prompt
    assert "Arabica" in prompt
    assert "Robusta" in prompt
    assert "Purity Beans" in prompt
    assert WEBSITE_URL in prompt


def test_extract_post_text_includes_all_structured_elements():
    piece = {
        "hook": "Why pouring 100°C boiling water destroys your morning coffee.",
        "body": "Coffee extraction is basic thermodynamics. Water at 100°C scorches delicate chlorogenic acids and draws out astringent bitter tannins. When you brew at 80°C to 85°C, natural bean sweetness surfaces without sugar.",
        "brand_bridge": "That is why Purity Beans freeze-dries pure Arabica and Robusta beans at -40°C — so the cup you drink at your desk retains volatile aromatics intact.",
        "closing_question": "What temperature do you typically brew your coffee at work?",
        "cta": f"Upgrade your daily desk ritual with 100% pure coffee at {WEBSITE_URL}",
        "hashtags": "#CoffeeKnowledge #FoodScience #PurityBeans",
    }
    extracted = _extract_post_text({"linkedin_post": piece})
    assert piece["hook"] in extracted
    assert piece["body"] in extracted
    assert piece["brand_bridge"] in extracted
    assert piece["closing_question"] in extracted
    assert piece["cta"] in extracted
    assert piece["hashtags"] in extracted
    assert len(extracted) <= 3000
