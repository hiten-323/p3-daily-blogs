"""Nurture copy stays on real jars. It does not invent a SKU, a coupon, or a rate."""
from __future__ import annotations


def test_nurture_copy_has_no_invented_offer():
    from content_generator.nurture.templates import TEMPLATES

    blob = " ".join(
        " ".join(str(template.get(key) or "") for key in ("subject", "body", "cta"))
        for template in TEMPLATES.values()
    ).lower()
    for banned in (
        "pure10",
        "pure_fan",
        "cold brew",
        "dark roast",
        "20% stronger",
        "within 45 days",
        "60-70%",
        "40% repeat",
        "within a month",
    ):
        assert banned not in blob, banned
    assert "30% chicory" in blob
    assert "ultra blend is 70% coffee and 30% chicory" in blob
