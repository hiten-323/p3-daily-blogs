"""
Version registry — one place for every version stamped on content.

Every generated asset carries these, so a published post can be reproduced
and debugged months later ("which prompts/schema/publisher produced this?").

Bump the relevant constant when you change that layer:
  PROMPT_VERSION    prompt wording / structure changes
  SCHEMA_VERSION    required fields or validation rules change
  PUBLISHER_VERSION publisher request/response behavior changes
  ASSET_FORMAT      image/video composition changes

policy_version is deliberately NOT here — it lives in founder_policies.yaml
because the founder owns it (see founder_policy.py).
"""
from __future__ import annotations

PROMPT_VERSION    = "2.8.0"   # + platform-native growth engine modules
SCHEMA_VERSION    = "1.4.0"   # engagement fields, ai prompts, thumbnails, hook_options
PUBLISHER_VERSION = "2.3.0"   # timed slots, reel video, product tags, telemetry
ASSET_FORMAT      = "3.1.0"   # cinematic frames, white-knockout, safe-zone text

# ADR-002. Bump DECISION_VERSION when the SHAPE of the decision record changes,
# so records written under different definitions are never silently compared.
# Bump PAYOFF_GATE_VERSION when the payoff rule changes, so a rejection can be
# traced to the rule that produced it.
DECISION_VERSION    = "1.0.0"   # scroller state/mechanism, hook strategy, payoff type
PAYOFF_GATE_VERSION = "1.0.0"   # structural hook-promise -> payoff-present check


def all_versions() -> dict:
    """Every version in one dict — stamped onto assets and telemetry."""
    return {
        "prompt_version":    PROMPT_VERSION,
        "schema_version":    SCHEMA_VERSION,
        "publisher_version": PUBLISHER_VERSION,
        "asset_format":      ASSET_FORMAT,
    }
