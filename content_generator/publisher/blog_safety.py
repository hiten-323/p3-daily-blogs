"""Single-source-of-truth safety guard for this pipeline's blog path."""
from __future__ import annotations


def assert_blog_disabled() -> None:
    """Raise unless the blog path was explicitly enabled (BLOG_ENABLED=true)."""
    from content_generator.core.blog_flags import blog_enabled
    if not blog_enabled():
        raise RuntimeError(
            "GitHub blog publishing is disabled; Blogs bot owns the Shopify blog"
        )
