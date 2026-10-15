"""Master switch for this pipeline's Shopify blog path.

The separate Blogs bot owns the Shopify blog. Default is off so this engine
does not generate, regenerate, publish, or retry blog posts, and so
retry-unposted / mandatory-slot / ledger alerts never treat the blog as missing.

Enable only with an explicit env flag:
  BLOG_ENABLED=true

SHOPIFY_BLOG_ENABLED remains a legacy alias for the same switch.
"""
from __future__ import annotations

import os

_TRUE = {"1", "true", "yes", "on"}


def blog_enabled() -> bool:
    """Return True only when the blog path is explicitly enabled.

    Precedence: BLOG_ENABLED, then legacy SHOPIFY_BLOG_ENABLED. Unset → False.
    """
    for key in ("BLOG_ENABLED", "SHOPIFY_BLOG_ENABLED"):
        raw = os.getenv(key)
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip().lower() in _TRUE
    return False


def blog_disabled_reason() -> str:
    return "blog_disabled: owned by Blogs bot (set BLOG_ENABLED=true to opt in)"
