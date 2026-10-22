from content_generator.core.brand_validator import banned_claim_hits, validate_asset_copy


def test_flags_fresh_lab_tested_zero_acidity():
    assert banned_claim_hits("Keep it fresh. Lab-tested. Zero acidity.") == ["fresh", "lab-tested", "zero acidity"]


def test_refresh_is_not_flagged():
    assert banned_claim_hits("Refresh your shelf at p3online.in") == []


def test_validator_rejects_fresh_copy():
    ok, issues = validate_asset_copy("Purity Beans pure coffee tastes as fresh as the first cup.",
                                     check_brand_facts=False, check_length=False)
    assert not ok and any("banned claim" in i for i in issues)
