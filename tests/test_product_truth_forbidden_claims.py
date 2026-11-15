"""Founder hard bans are enforced by the shared product-truth claim gate."""

import pytest

from content_generator.core.product_truth import product_truth_findings


@pytest.mark.parametrize("claim", [
    "Fresh instant coffee for your morning.",
    "Enjoy the freshness of every cup.",
    "Lab-tested instant coffee.",
    "Zero acidity instant coffee.",
    "Single-origin instant coffee.",
    "Made from premium coffee beans.",
    "A bean-based instant coffee experience.",
    "From bean to cup in one shot.",
    "Whole beans, roasted to perfection.",
    "DM us for free samples.",
    "Competitors sell inferior coffee.",
])
def test_unsupported_product_claims_are_rejected(claim):
    findings = product_truth_findings(claim, featured="purica")
    assert findings, claim


def test_brand_name_purity_beans_is_not_mistaken_for_bean_claim():
    assert product_truth_findings("Purity Beans instant coffee, ready in seconds.", featured="purica") == []


def test_instant_coffee_description_remains_allowed():
    assert product_truth_findings("A smooth instant coffee for your daily cup.", featured="purica") == []

def test_published_links_require_all_three_utm_parameters():
    findings = product_truth_findings("Shop here: https://p3online.in")
    assert any("utm_source" in str(row) and "utm_campaign" in str(row) for row in findings)


def test_fully_tagged_product_link_is_allowed():
    assert product_truth_findings(
        "Shop here: https://p3online.in/?utm_source=instagram&utm_medium=story&utm_campaign=purity_beans"
    ) == []


@pytest.mark.parametrize("text", [
    "Freeze-dried instant coffee at Purity Beans is Purica and Purista.",
    "Purity Beans is a brand of instant coffee.",
])
def test_brand_name_followed_by_is_is_not_a_bean_claim(text):
    findings = product_truth_findings(text, featured="purica")
    assert not [row for row in findings if "bean-based" in row["reason"]], text


@pytest.mark.parametrize("text", [
    "Our beans are roasted dark.",
    "The beans from Coorg make this cup.",
    "Purity Beans coffee beans are great.",
])
def test_real_bean_wording_is_still_rejected(text):
    findings = product_truth_findings(text, featured="purica")
    assert [row for row in findings if "bean-based" in row["reason"]], text
