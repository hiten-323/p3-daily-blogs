from content_generator.core import rejection_briefs as rb


def test_promotional_reel_gets_value_brief_from_scratch():
    fb, scratch = rb.brief("reel_1", "objective compliance: Asset assigned DISCOVERY objective is primarily promotional", 0)
    assert scratch and "NON-SALES" in fb and "soft end card" in fb
    fb2, _ = rb.brief("reel_2", "portfolio gate: sales-led asset not allowed at this growth stage", 3)
    assert "freeze-dried vs agglomerated" in fb2 or "brew tip" in fb2 or "myth" in fb2 or "ritual" in fb2


def test_value_formats_rotate():
    assert len({rb.value_format(i) for i in range(4)}) == 4


def test_short_payoff_brief():
    fb, scratch = rb.brief("yt_short", "payoff gate: hook promises 'alternative' but the content delivers new_knowledge", 0)
    assert "delivers" in fb and not scratch


def test_blog_dry_brief_and_stock_guard():
    fb, scratch = rb.brief("blog_post", "dips into dry inventory-style talk (e.g., 'currently out of stock')", 1)
    assert scratch and "NEVER mention stock status" in fb and "guide" in fb
    assert rb.stock_mentions({"body": "Prima is currently out of stock, join the waitlist."})
    assert not rb.stock_mentions({"body": "Brew at 80C for a smoother cup.", "hold_reason": "out of stock"})


def test_unrelated_reason_passthrough():
    assert rb.brief("linkedin_post", "hook too thin", 0) == ("hook too thin", False)


def test_gates_not_loosened_reason_fn_matches_director():
    from content_generator.core import editorial_engine as ee
    assert callable(ee.asset_gate_reason) and callable(ee.portfolio_sales_rejection)
