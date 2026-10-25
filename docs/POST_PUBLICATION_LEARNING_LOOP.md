# Post-Publication Learning Loop — Implementation Contract

Status: implementation specification; not a claim that all items below are already implemented.
Repository: `hiten-323/p3-daily-blogs`

## Objective

Every successfully published content item must become a measurable experiment. Collect real platform-native results, diagnose the result against the item's original objective, persist evidence-backed lessons, and inject those lessons into the next day's generation for the same platform and content type. This is a closed feedback loop, not merely a report.

## Required lifecycle

1. **Register on confirmed publication.** For every published post, Reel, Story, carousel, Short, LinkedIn post, Facebook post, Threads post, and Shopify blog, save a unique record with platform, native media/post ID, canonical URL, published timestamp (UTC and IST), content/asset ID, content type, topic, hook, CTA, creative format, hashtags, intended audience, KPI/objective at creation, prompt/policy version, and generation parameters. Never register a failed/held publish as a successful post.
2. **Measure after publication.** Schedule measurements at approximately 24 hours, 72 hours, and 7 days (respect API availability, rate limits, and platform-specific retention). Each platform adapter must fetch only metrics that platform actually exposes for that account and media type. Keep raw observations, timestamp, source endpoint, measurement window, and fetch status. A missing metric is `null`/unknown, never zero. Do not substitute account-level metrics for post-level results or fabricate metrics.
3. **Diagnose each item.** Compare results to the item's creation-time KPI and a comparable baseline (same platform, format, and objective; use a rolling window where enough samples exist). Produce a structured diagnosis: what worked, what underperformed, likely contributing factors, confidence, evidence, sample size, and next experiment. Separate correlation from causation; avoid confident conclusions from one post.
4. **Persist lessons.** Store append-only measurement snapshots and versioned lessons in the existing learning storage. Deduplicate by platform + native media ID + measurement window. Retries must be idempotent. Preserve historical observations; never overwrite a prior snapshot without an auditable correction record.
5. **Use lessons tomorrow.** Before generating the next day's content, load the latest eligible lessons separately for each platform and content type. Inject a compact evidence-backed strategy context into that platform's prompt: repeat patterns with sustained positive evidence, repair recurring weaknesses, and define one testable change. Do not copy yesterday's post; transfer only validated principles.
6. **Verify adaptation.** Record which lesson/decision was applied to each new asset and its decision/policy version. After measurement, evaluate whether the change improved the intended KPI. Keep, revise, or retire the lesson based on repeated evidence. Write a daily learning report with measured posts, missing data, lessons accepted/rejected, changes applied, and unresolved failures.

## Platform adapter contract

Implement a common interface such as `fetch_post_metrics(post_record, window) -> MetricObservation`, with adapters for Instagram (posts/Reels/Stories where API permissions allow), Facebook, Threads, YouTube, LinkedIn, and Shopify blog/website analytics where connected. Each adapter must explicitly declare supported metrics and unsupported fields. Treat HTTP 401/403, permission errors, expired tokens, rate limits, deleted posts, and unavailable insights as distinct states; apply bounded retries with backoff and alert on persistent failures. Do not report a post as measured just because its public URL opens.

Suggested common metric vocabulary (only when actually available): impressions/views, reach, watch time, average view duration, completion/retention, likes/reactions, comments/replies, shares/reposts, saves, profile/page visits, follows/subscribers attributed, link clicks, website sessions, attributed orders, and revenue. Keep attribution confidence and source with conversion data.

## Learning and decision rules

- Optimize to the KPI stamped at creation time; do not silently rescore historical posts under a new objective.
- Compare like with like: platform × content type × objective, and segment paid vs organic.
- Use confidence/sample-size gates. A single post is a clue, not a rule. Maintain exploration so the engine does not overfit to yesterday's outlier.
- Account for post age and measurement window; compare 24h with 24h, not with 7-day totals.
- Distinguish content quality from distribution, audience size, posting time, outages, and API/data gaps.
- A low result should create a specific improvement experiment (e.g. revise hook clarity, first-frame readability, CTA, pacing, topic, caption, or format) only when evidence supports that hypothesis.
- Do not optimize for vanity metrics alone when the declared goal is qualified traffic, leads, or sales. Do not claim revenue attribution without valid source evidence.
- Preserve brand guardrails, product truth, approved product imagery, platform policies, legal requirements, and human-approval gates. Learning must never authorize fabricated claims, unapproved discounts, or unsafe automatic actions.

## Suggested storage

Extend the existing `output/learning/published_posts.json` records with stable identity, platform, URLs, creation-time objective, decision metadata, and measurement status; retain snapshots per window. Extend `performance_log.json` or add a versioned `platform_performance_log.json` for normalized observations. Add a versioned `platform_lessons.json` / `daily_learning_reports.json` if needed. Keep backward compatibility with current records and use atomic writes/locking or the project's established persistence helper.

## Daily workflow integration

- **After every publish attempt:** record success/failure per platform and register successful items immediately.
- **Every scheduled recovery/measurement run:** fetch due observations, retry transient failures safely, and persist diagnostic state.
- **Before content generation:** load eligible per-platform lessons and feed them into prompt/strategy selection.
- **After generation:** record the exact lesson IDs and decisions used for each asset.
- **After measurements:** evaluate experiments and update lesson confidence without deleting history.
- **Alert:** surface stale/unmeasurable posts, authentication/permission failures, repeated publish failures, and persistence errors.
- **Dry-run:** exercise adapters with fixtures/mocks; never publish or mutate live accounts in dry-run mode.

## Required tests

1. Every supported platform/type registers only confirmed successful publications.
2. Repeated callbacks and recovery runs do not duplicate posts or observations.
3. Missing metrics remain unknown rather than zero; account-level data is never attributed to a post.
4. Platform errors and token expiry are classified and retried/alerted appropriately.
5. 24h, 72h, and 7d observations are kept distinct; one post is not counted as three independent experiments.
6. Objective-at-creation and comparable-baseline rules are honored.
7. Lessons require evidence/sample thresholds and retain an exploration path.
8. Tomorrow's platform prompts demonstrably receive eligible lessons; lesson/decision IDs are logged.
9. A failed or low-confidence hypothesis is not promoted as a proven rule.
10. Dry-run has no live publishing side effects; regression suite and existing governance/brand-guard tests remain green.

## Definition of done

The feature is complete only when an end-to-end test demonstrates: publish fixture → idempotent post registration → due metric collection for each supported adapter → evidence-based diagnosis → persisted lesson → next-day prompt consumes the lesson → resulting asset records its decision provenance. Report adapter coverage and real API permission gaps separately. Do not label the system production-ready merely because unit tests pass.
