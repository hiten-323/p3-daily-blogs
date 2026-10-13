# Purity Beans Growth Operating System

> **Prefer evidence over elegance.**
> **The simplest solution that measurably improves the business wins.**

An autonomous daily growth engine for [Purity Beans](https://p3online.in) —
India's cleanest instant coffee (100% coffee, zero chicory) by Pure Pantry
Provisions. It generates, publishes, measures, and learns — every day,
unattended, on GitHub Actions.

## The daily loop

```
06:00 IST  GENERATE   insights + Shopify revenue → learn → generate content
                      → editorial gate (8.0) → images → LinkedIn/blog/YouTube publish
10:00 IST  MORNING    Instagram carousel  (owner-chosen morning window)
22:00 IST  EVENING    Instagram reel post (owner-chosen evening window)
```

The publishing times above are the canonical production schedule. They are
maintained in `content_generator/core/slot_registry.py` and the workflow cron
is checked against that registry by the config-drift test.

## Visual gate

Before any publish, the generate slot runs `enforce_visual_gate` on every
surface: Story, Reel frame, carousel, feed, Facebook, LinkedIn, Threads, and
the YouTube thumbnail. The check is fail-closed. A frame must be sharp, show
the full jar inside the safe zone, carry a mask that passed integrity (no
ragged edge), have no studio disc or halo under the base, sit on a contact
shadow, and not overlap the cup, laptop, or plants. The on-image CTA must use
`@purepantryprovisions`. Unverified stat hooks (invented rupee claims, "waste",
"every week") fail.

A failure is re-rendered on the next lifestyle scene and the other side of
the prop, up to `QUALITY_MAX_REGEN` extra tries. What still fails is
`BLOCKED`, moved out of the publish folder, and never posted. The same rule
applies when a publish slot composes a Story or an evening feed. CI renders
every scene and format and fails if any of them miss this bar.

Every morning the system asks one question: *"What is the fastest way to gain
followers tomorrow — and which of yesterday's content actually made money?"*

## Constitution

Architecture is **frozen** ([ADR-001](docs/ADR-001.md)). These documents govern
the system and change only through ADRs:

| Document | Answers |
|---|---|
| [MISSION.md](MISSION.md) | What this system is and is not |
| [OPERATING_PRINCIPLES.md](OPERATING_PRINCIPLES.md) | The 10 rules every change obeys |
| [SUCCESS_METRICS.md](SUCCESS_METRICS.md) | What winning means, measured how |
| [GOAL_HIERARCHY.md](GOAL_HIERARCHY.md) | Which goal wins when goals conflict |
| [POLICY_ENGINE.md](POLICY_ENGINE.md) | Every enforced rule + where it lives in code |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Module map + key decisions |
| [ASSUMPTIONS.md](ASSUMPTIONS.md) | What we take as true + blast radius if wrong |
| [UNKNOWNS.md](UNKNOWNS.md) | Open questions + the cheapest probe for each |

## Core capabilities

- **Dual-track content** — growth track (non-branded, cinematic, follower-first)
  and brand track (exact jar reference + buy CTA + website, always all three)
- **Growth Director** — stage-aware content ratios (95% viral at 0-1K followers
  → 50/50 at 100K+), one funnel objective per reel, watch-time structure
- **Learning loop** — Instagram insights + Shopify order attribution feed a
  viral memory (top/bottom 20% structures with inferred reasons), adaptive
  165-hashtag bank, hook A/B scoring, and a 60-day creative fatigue guard
- **Realism engineering** — every generated visual is prompt-engineered to pass
  as real (banned AI-tell words, physics-true motion, lived-in imperfections)
- **Never-miss-a-day resilience** — LLM provider cascade, image fallbacks,
  emergency best-by-score publishing, per-slot run locks

## Setup

Required GitHub Secrets: LLM keys (`GROQ_API_KEY`, …), `INSTAGRAM_ACCOUNT_ID`,
`INSTAGRAM_ACCESS_TOKEN` (renew every ~59 days), `HF_TOKEN`,
`SHOPIFY_STORE_DOMAIN`, `SHOPIFY_ADMIN_TOKEN` (read_orders).

```bash
pip install -r requirements.txt
python -m content_generator.scheduler.daily --now      # manual run
python -m content_generator.scheduler.daily --report   # 7-day report
```

## Daily founder workflow (the only manual step)

1. Open `output/ugc/tool_brief_<date>.json`
2. Paste Step 1 into Nano Banana Pro → generate the still frame
3. Paste Step 2 into Seedance → animate it
4. (Optional) OpenArt VFX to put yourself in the scene
5. Post as the day's reel — captions, hashtags, and triggers are already
   published by the engine
