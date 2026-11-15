"""Store links the generator writes carry utm_source, utm_medium and utm_campaign."""
from content_generator.core.product_truth import product_truth_findings
from content_generator.core.utm import site_link, tag_store_links, tag_url
from content_generator.scheduler.daily import _inject_brand_into_piece


def _utm_findings(text):
    return [f for f in product_truth_findings(text) if "utm_source" in f["reason"]]


def test_site_link_is_tagged_per_platform():
    assert site_link("threads_post") == (
        "https://p3online.in/?utm_source=threads&utm_medium=post&utm_campaign=202610")
    assert _utm_findings("Shop " + site_link("instagram_post")) == []


def test_tag_store_links_keeps_existing_tags_and_punctuation():
    tagged = "https://p3online.in/?utm_source=x&utm_medium=y&utm_campaign=z"
    assert tag_store_links(f"Go {tagged}.", "facebook_post") == f"Go {tagged}."
    out = tag_store_links("Shop: https://p3online.in/products/bold.", "facebook_post")
    assert out.endswith("utm_campaign=202610.")
    assert _utm_findings(out) == []
    assert tag_url("https://p3online.in/products/bold?ref=a", "blog").startswith(
        "https://p3online.in/products/bold?ref=a&utm_source=blog")


def test_injected_brand_link_passes_the_utm_rule():
    piece = _inject_brand_into_piece("instagram_post", {"caption": "A cup worth reading the label for."})
    assert "utm_source=instagram" in piece["caption"]
    assert _utm_findings(piece["caption"]) == []


def test_rule_ignores_structured_data_but_not_store_links():
    assert _utm_findings("https://schema.org/InStock") == []
    assert _utm_findings('<link rel="canonical" href="https://p3online.in/blogs/news/a">') == []
    assert _utm_findings(
        '<script type="application/ld+json">{"url": "https://p3online.in/blogs/news/a"}</script>') == []
    assert _utm_findings("Shop https://p3online.in/products/bold")
    assert _utm_findings("Shop https://p3online.in?ref=1")
