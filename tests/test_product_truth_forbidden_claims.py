"""Founder hard bans are enforced by the shared product-truth claim gate."""

import pytest

from content_generator.core.product_truth import product_truth_findings


@pytest.mark.parametrize("claim", [
    "Fresh instant coffee for your morning.",
    "Lab-tested instant coffee.",
    "Zero acidity instant coffee.",
    "Single-origin instant coffee.",
    "Made from premium coffee beans.",
    "A bean-based instant coffee experience.",
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
