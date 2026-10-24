from content_generator.publisher import product_links as pl


def test_tracked_url_has_product_handle_and_utm():
    url = pl.tracked_url("bold", "facebook")
    assert url.startswith("https://p3online.in/products/purity-beans-bold-instant-coffee?")
    assert "utm_source=facebook" in url and "utm_medium=post" in url and "utm_campaign=202610" in url


def test_story_utm_content():
    assert "utm_content=story" in pl.tracked_url("bold", "instagram_story")


def test_featured_slug_from_content_and_rotation():
    assert pl.featured_slug({"featured_product": "Ultra Blend"}) == "ultra_blend"
    assert pl.featured_slug({}, day=1) in {"bold", "ultra_blend", "purista", "purica"}


def test_prima_out_of_stock_gets_no_product_link():
    assert pl.featured_slug({"featured_product": "Prima"}) == ""
    out = pl.with_product_link("Hello coffee people", {"featured_product": "Prima"}, "linkedin")
    assert "/products/" not in out and "p3online.in" in out


def test_instagram_says_link_in_bio_and_names_product():
    out = pl.with_product_link("Great cup.", {"featured_product": "Bold"}, "instagram")
    assert "link in bio" in out.lower() and "Purity Beans Bold" in out
    assert "http" not in out and "Comment TRY" in out and "LINK" in out


def test_clickable_platforms_append_once():
    c = {"featured_product": "Purista"}
    once = pl.with_product_link("Body", c, "linkedin")
    assert once.count("p3online.in/products/") == 1
    assert pl.with_product_link(once, c, "linkedin") == once


def test_threads_fits_limit_keeps_link():
    out = pl.with_product_link("x" * 600, {"featured_product": "Bold"}, "threads", limit=500)
    assert len(out) <= 500 and "p3online.in/products/" in out


def test_block_is_claim_safe():
    for plat in ("instagram", "facebook", "threads", "linkedin", "youtube"):
        for prod in ("Bold", "Ultra Blend", "Purista", "Purica"):
            b = pl.link_block({"featured_product": prod}, plat).lower()
            assert "100%" not in b and "₹" not in b and "pure" not in b
            assert "chicory" not in b and "hurry" not in b and "last chance" not in b


def test_story_line_and_kill_switch(monkeypatch):
    assert pl.story_link_line("Sip better") == "Sip better · Link in bio"
    monkeypatch.setenv("PRODUCT_LINKS", "0")
    assert pl.with_product_link("Body", {"featured_product": "Bold"}, "linkedin") == "Body"
