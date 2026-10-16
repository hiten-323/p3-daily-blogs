# Architecture

Status: **FROZEN** (see docs/ADR-001.md). Structural changes require a new ADR.

## Daily operating loop (3 GitHub Actions runs, IST)

```
06:13  GENERATE ─────────────────────────────────────────────────────────
       0.5 insights_fetch        yesterday's IG metrics → learning engine
       0.6 revenue_attribution   Shopify orders → day-level attribution
       1   research              trends + strategy context
       2   generate              LLM cascade; prompts carry: viral memory,
                                 fatigue guard, Growth Director brief,
                                 realism rules, elite/growth mode context
       3   brand injection + hook A/B + editorial gate (8.0)
       4-8 images (jar-referenced), UGC tool brief, LinkedIn/blog/YouTube
           publish. Instagram HELD. Content + images committed to repo.

09:53  MORNING ── loads committed content → IG carousel + FB mirror
21:53  EVENING ── loads committed content → IG reel-style post + FB mirror
```

The production schedule is defined once in `content_generator/core/slot_registry.py`:
06:13, 09:53 and 21:53 IST (off round minutes; GitHub drops many :00/:30 schedule events). GitHub Actions cron entries and `FORCE_SLOT` are
derived from that registry and protected by `tests/test_config_drift.py`.

The 8.0 editorial threshold is also constitutional: `brand_guard.py` defines
8.0 and `founder_policies.yaml` carries the same value as the founder-editable
policy. The editorial engine consumes the policy value at runtime.

## Module map

| Layer | Module | Responsibility |
|---|---|---|
| Constitution | `core/brand_guard.py` | Brand facts, all system-prompt blocks (LANGUAGE, REALISM, ELITE, GROWTH, MASTER), jar references |
| Strategy | `core/growth_director.py` | Stage detection, funnel objectives, daily strategy brief |
| Generation | `pipeline/generator.py` + `prompts/*` | Two-phase parallel LLM generation, context assembly |
| Quality | `core/editorial_engine.py`, `core/schema_validation.py`, `core/brand_validator.py` | Score gate, Pydantic schemas, brand compliance |
| Creative | `creative/jar_composer.py`, `ugc_generator.py`, `flux_generator.py` | Avatar/UGC/hook prompts with real jar refs; image provider cascade |
| Distribution | `publisher/dispatcher.py`, `instagram.py`, `linkedin.py`, … | Multi-platform posting; slot-aware Instagram hold |
| Scheduling | `scheduler/daily.py`, `slots.py`, `run_lock.py`, `watchdog.py`, `retry_manager.py` | Orchestration, slot routing, locks, timeouts, retries |
| Intelligence | `analytics/insights_fetcher.py`, `revenue_attribution.py`, `hashtag_bank.py`, `hook_selector.py`, `optimizer.py` | Measurement + attribution + selection |
| Memory | `core/learning_engine.py` + `output/learning/*.json` | Viral memory, scores, snapshots — committed each run |

## External dependencies

- **LLM**: Groq → Cerebras → Gemini → DeepSeek → OpenRouter (free-tier cascade)
- **Images**: HuggingFace FLUX → Pollinations → fal.ai → Pillow placeholder
- **Instagram**: Meta Graph API v24.0 (publish + insights; long-lived token renewal ritual documented)
- **Shopify**: Admin API 2026-07, read_orders only
- **Runtime**: GitHub Actions ubuntu-latest, stateless; state persists via repo commits

## Key architectural decisions (rationale)

1. **State in the repo, not a database** — CI runners are stateless; JSON files
   in `output/learning/` committed each run are simple, diffable, and free.
2. **Deterministic heuristics where LLM calls are avoidable** (hook scoring,
   hashtag selection) — free-tier TPM budget is the binding constraint.
3. **Three-slot publishing over a scheduler service** — cron granularity is
   sufficient; a queue/scheduler would add infrastructure for marginal gain.
4. **Day-level revenue attribution** — Instagram captions can't carry links;
   pretending per-post precision would violate the honesty principle.
