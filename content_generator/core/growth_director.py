"""
Growth Director — the strategic brain that turns a Content Engine into a
Growth Engine.

Every morning, before any content is generated, it answers:
  "What is the fastest way to gain followers tomorrow?"

It does this with data the engine already has:
  - follower snapshots (from insights_fetcher) -> growth stage
  - growth stage -> viral/selling content ratio (Million Follower Mode)
  - day number -> today's single funnel objective per reel (never mixed)
  - viral memory + fatigue guard (injected separately by the generator)

Output: a strategy brief injected into every generation prompt.
"""
from __future__ import annotations
import json
import logging
import os

logger = logging.getLogger(__name__)

_LEARNING_DIR = os.getenv("LEARNING_DIR", os.path.join("output", "learning"))
_SNAP_PATH    = os.path.join(_LEARNING_DIR, "follower_snapshots.json")


# ── Million Follower Mode: stage-dependent content ratios ─────────────────────

GROWTH_STAGES = [
    #  min_followers, name,        viral%, selling%, focus
    (0,       "IGNITION (0-1K)",      95,  5,
     "Nobody knows you exist. 95% of content must be pure viral value — "
     "coffee culture, curiosity, education. Selling to strangers wastes reach. "
     "Every reel's only job: make a stranger tap Follow."),
    (1_000,   "TRACTION (1K-10K)",    85, 15,
     "You have proof of life. Keep viral dominant, introduce light brand "
     "presence — the jar can appear naturally, soft CTAs only."),
    (10_000,  "MOMENTUM (10K-100K)",  70, 30,
     "Audience trusts you. Balance viral discovery with conversion reels "
     "that route traffic to p3online.in."),
    (100_000, "SCALE (100K+)",        50, 50,
     "Authority established. Half discovery, half revenue. Launch-style "
     "content and direct product storytelling now convert."),
]


# ── Follower Funnel: one objective per reel, never mixed ──────────────────────

FUNNEL_OBJECTIVES = [
    ("DISCOVERY",  "Reach strangers. Broad-appeal topic, zero brand, maximum shareability. "
                   "Success metric: shares + reach."),
    ("FOLLOW",     "Convert viewers to followers. End with a follow-worthy promise "
                   "('Follow — tomorrow I show you X'). Success metric: follows per view."),
    ("AUTHORITY",  "Build trust. Teach something only an expert would know. "
                   "Success metric: saves."),
    ("CONVERSION", "Route to website. Product visible, clear buy CTA, https://p3online.in. "
                   "Success metric: link clicks. (Brand track only.)"),
    ("COMMUNITY",  "Spark conversation. Opinion bait, this-or-that, identity question, "
                   "or intent-comment mechanic (withhold price/variant info — "
                   "'Comment PRICE / BOLD / GIFT' — each comment is a lead). "
                   "Success metric: comments."),
]


def get_follower_count() -> int:
    """Latest follower count from snapshots; 0 if none recorded yet."""
    if not os.path.exists(_SNAP_PATH):
        return 0
    try:
        with open(_SNAP_PATH, "r", encoding="utf-8") as f:
            snaps = json.load(f)
        return int(snaps[-1]["count"]) if snaps else 0
    except Exception:
        return 0


def get_growth_stage(followers: int = None) -> dict:
    """Return the current growth stage config for Million Follower Mode."""
    if followers is None:
        followers = get_follower_count()
    stage = GROWTH_STAGES[0]
    for s in GROWTH_STAGES:
        if followers >= s[0]:
            stage = s
    return {
        "followers": followers,
        "name":      stage[1],
        "viral_pct": stage[2],
        "sell_pct":  stage[3],
        "focus":     stage[4],
    }


# Primary message angle — rotates so the brand isn't a one-note chicory sermon.
# The "zero chicory" differentiator still appears, but only EXPOSE/CONTRAST days
# lead with betrayal; other days lead with their own value to reach the ~95% who
# don't yet care about chicory. (Addresses the one-note-messaging risk.)
MESSAGE_ANGLES = [
    ("EDUCATION",   "Lead with genuinely useful coffee knowledge (brewing, storage, "
                    "caffeine, taste). Brand is a light touch at the end, not the point."),
    ("EXPOSE",      "Lead with the chicory/adulteration truth — the betrayal hook. "
                    "This is the differentiator day."),
    ("ASPIRATION",  "Lead with lifestyle/ritual/identity — the feeling of great coffee. "
                    "Aspirational, not accusatory."),
    ("FOUNDER",     "Lead with a founder story/lesson/decision. People follow people."),
    ("VALUE",       "Lead with practical value — money saved, a guide, a comparison. "
                    "Helpful first, brand second."),
    ("CONTRAST",    "Lead with an honest side-by-side (pure vs filler) without naming "
                    "competitors. Let the viewer conclude."),
]


def get_todays_message_angle(day: int) -> tuple:
    return MESSAGE_ANGLES[day % len(MESSAGE_ANGLES)]


def _creator_dna_line() -> str:
    dna = ("We are Purity Beans — 100% pure coffee for Indians done being fooled by chicory.")
    try:
        from content_generator.core.founder_policy import policy
        dna = policy().domain("brand").get("creator_dna", dna)
    except Exception as _e:
        logger.debug("[growth_director] optional step failed: %s", _e)
    return f"CREATOR DNA (our identity — stay in character): {dna}"


def _consistency_block() -> str:
    """Avatar + topic-lane lock — the #1 algorithmic fit-score lever (Kallaway)."""
    avatar = "Urban Indian coffee drinker, 22-40, who cares about what they consume"
    lane   = "The truth about instant coffee quality and how to drink better coffee"
    try:
        from content_generator.core.founder_policy import policy
        p = policy()
        avatar = p.domain("content").get("core_avatar", avatar)
        lane   = p.domain("content").get("core_topic_lane", lane)
    except Exception as _e:
        logger.debug("[growth_director] optional step failed: %s", _e)
    return (
        "AUDIENCE MATCHING (highest-leverage algo lever — stay consistent):\n"
        f"- CORE AVATAR (every post is for exactly this person): {avatar}\n"
        f"- CORE TOPIC LANE (stay inside this): {lane}\n"
        "Consistency builds the algorithm's fit score so it pushes you to the "
        "right non-followers. Do NOT chase a viral idea aimed at a different "
        "audience — even one off-avatar hit weakens your next several posts."
    )


def get_todays_objectives(day: int) -> dict:
    """
    Assign ONE funnel objective per asset for today. Never mixed.

    Growth reel and Shorts cycle the primary audience-building objectives
    (FOLLOW, DISCOVERY).
    Brand reels and Carousels cycle AUTHORITY, COMMUNITY, and CONVERSION.
    In early stages (IGNITION), CONVERSION is strictly capped to <= 5% across
    the asset mix to maximize viral follower discovery.
    """
    stage = get_growth_stage()
    viral_mode = stage["viral_pct"] >= 85  # IGNITION or TRACTION

    # FUNNEL_OBJECTIVES:
    # 0: DISCOVERY, 1: FOLLOW, 2: AUTHORITY, 3: CONVERSION, 4: COMMUNITY
    
    # Growth reel: alternating FOLLOW and DISCOVERY — its sole job is stranger acquisition
    growth_obj = FUNNEL_OBJECTIVES[1] if day % 2 == 1 else FUNNEL_OBJECTIVES[0]

    # Brand reel (reel_2):
    if viral_mode:
        # Conversion appears at most 1 day in 7 during IGNITION, else AUTHORITY / COMMUNITY
        brand_obj = FUNNEL_OBJECTIVES[3] if day % 7 == 0 else (
            FUNNEL_OBJECTIVES[2] if day % 2 == 0 else FUNNEL_OBJECTIVES[4]
        )
    else:
        conv_every = 3 if stage["viral_pct"] >= 70 else 2
        brand_obj = FUNNEL_OBJECTIVES[3] if day % conv_every == 0 else (
            FUNNEL_OBJECTIVES[2] if day % 2 == 0 else FUNNEL_OBJECTIVES[4]
        )

    # Reel 1: morning reel — DISCOVERY on odd days, FOLLOW on even days
    reel_1_obj = FUNNEL_OBJECTIVES[0] if day % 2 == 1 else FUNNEL_OBJECTIVES[1]

    # Carousel: AUTHORITY (saves & reference frameworks) or FOLLOW
    carousel_obj = FUNNEL_OBJECTIVES[2] if day % 2 == 0 else FUNNEL_OBJECTIVES[1]

    # Instagram feed post: COMMUNITY (debate & comments) or FOLLOW
    ig_post_obj = FUNNEL_OBJECTIVES[4] if day % 2 == 0 else FUNNEL_OBJECTIVES[1]

    # YouTube Short: FOLLOW (high completion & subscribe CTA) or DISCOVERY
    yt_obj = FUNNEL_OBJECTIVES[1] if day % 2 == 0 else FUNNEL_OBJECTIVES[0]

    # Facebook post: DISCOVERY (relatable discussion shared to friends/family)
    fb_obj = FUNNEL_OBJECTIVES[0] if day % 2 == 0 else FUNNEL_OBJECTIVES[4]

    # Threads post: COMMUNITY (hot takes, truth bombs, reply magnets)
    th_obj = FUNNEL_OBJECTIVES[4] if day % 2 == 1 else FUNNEL_OBJECTIVES[1]

    # LinkedIn post: AUTHORITY (founder transparency, food science insights)
    li_obj = FUNNEL_OBJECTIVES[2] if day % 2 == 0 else FUNNEL_OBJECTIVES[1]

    # Blog post: AUTHORITY (deep educational SEO) or CONVERSION (buyers guide)
    blog_obj = FUNNEL_OBJECTIVES[3] if (not viral_mode and day % 3 == 0) else FUNNEL_OBJECTIVES[2]

    # Stories: COMMUNITY on odd days, CONVERSION on even days
    stories_obj = FUNNEL_OBJECTIVES[4] if day % 2 == 1 else FUNNEL_OBJECTIVES[3]

    return {
        "growth_reel":    growth_obj,
        "brand_reel":     brand_obj,
        "reel_1":         reel_1_obj,
        "reel_2":         brand_obj,
        "carousel":       carousel_obj,
        "instagram_post": ig_post_obj,
        "yt_short":       yt_obj,
        "facebook_post":  fb_obj,
        "threads_post":   th_obj,
        "linkedin_post":  li_obj,
        "blog_post":      blog_obj,
        "stories":        stories_obj,
    }


def get_strategy_brief(day: int) -> str:
    """
    The daily strategy brief — injected into every generation prompt.
    This is what makes the engine ask 'what grows followers fastest tomorrow'
    instead of 'what content do I generate today'.
    """
    stage = get_growth_stage()
    objs  = get_todays_objectives(day)
    angle = get_todays_message_angle(day)
    try:
        from content_generator.analytics.social_seo import social_seo_directive
        seo = "\n\n" + social_seo_directive(day)
    except Exception:
        seo = ""

    # Founder policy bias (target KPI, voice, priority segments) — the founder
    # steers the engine by editing founder_policies.yaml, never the prompts.
    policy_line = ""
    try:
        from content_generator.core.founder_policy import policy
        policy_line = policy().strategy_bias() + "\n\n"
    except Exception as _e:
        logger.debug("[growth_director] optional step failed: %s", _e)

    return f"""{policy_line}GROWTH DIRECTOR — TODAY'S STRATEGY (this overrides generic instincts):

CURRENT STAGE: {stage['name']} — {stage['followers']} followers
CONTENT RATIO: {stage['viral_pct']}% viral value / {stage['sell_pct']}% selling
STAGE FOCUS: {stage['focus']}

{_consistency_block()}

TODAY'S MESSAGE ANGLE: [{angle[0]}] {angle[1]}
Vary the ANGLE, never the avatar or topic lane above. Do NOT make every post a
chicory exposé — only EXPOSE/CONTRAST days lead with betrayal; today leads as
above. The "zero chicory, 100% coffee" fact may appear as a light touch.

STRANGER TEST (every hook + caption): would this work for someone who has NEVER
seen Purity Beans and couldn't care less? If it only lands for existing fans, rewrite.

HOOK STYLE — 2026 (heyDominik): people are HOOK-BLIND. Clever/loud/ALL-CAPS
"bait" hooks trigger a 'this is an ad, skip' reflex. Write hooks that DON'T
sound like hooks — like a real person sharing something, or something overheard:
"Did you know most instant coffee in India isn't actually coffee?" beats
"3 SHOCKING COFFEE SECRETS". Conversational, real, curiosity that feels honest.
{_creator_dna_line()}

ALGORITHM ENGAGEMENT — the sample group (~200 mostly-strangers) must engage or
the post dies in "200-view jail". Hit all four (Kallaway's four horsemen):
1. Solve a REAL problem the avatar has (relevant)
2. Say something non-obvious AND tactically usable (new + actionable)
3. Make it instantly understandable (high absorption)
4. Short distance to act — small action, big result

DRIVE COMMENTS (algorithmic boost): take a hard, slightly contrarian stance in
the BODY; amplify the framing; attach strong emotion. Hedging kills comments.
(The hook stays conversational; the stance lives in the payload.)

TODAY'S FUNNEL OBJECTIVES (one per asset — NEVER mix objectives in one asset):
- growth_reel    -> [{objs['growth_reel'][0]}] {objs['growth_reel'][1]}
- reel_1         -> [{objs['reel_1'][0]}] {objs['reel_1'][1]}
- reel_2         -> [{objs['reel_2'][0]}] {objs['reel_2'][1]}
- carousel       -> [{objs['carousel'][0]}] {objs['carousel'][1]}
- instagram_post -> [{objs['instagram_post'][0]}] {objs['instagram_post'][1]}
- yt_short       -> [{objs['yt_short'][0]}] {objs['yt_short'][1]}
- facebook_post  -> [{objs['facebook_post'][0]}] {objs['facebook_post'][1]}
- threads_post   -> [{objs['threads_post'][0]}] {objs['threads_post'][1]}
- linkedin_post  -> [{objs['linkedin_post'][0]}] {objs['linkedin_post'][1]}

WATCH-TIME STRUCTURE (Instagram ranks by watch time, not likes):
0-2s hook | 2-5s retention lock | 5-10s curiosity build | 10-20s reward | final 5s CTA.
Every frame/beat must earn the next 3 seconds. If a beat only exists to fill
time, cut it — shorter with full retention beats longer with drop-off.

{seo}

CROSS-PLATFORM VIRALITY & MAX FOLLOWER ENGINE:
Views alone are vanity. A viral post that gains 0 followers is a failed post.
Every single platform must pair high viral reach with an explicit FOLLOWER CONVERSION BRIDGE:
1. REELS & SHORTS: Ranked by SHARES (Send to DM) and Completion/Loop Rate. Give a selfish reason to follow: "Follow @puritybeans so you never drink roasted root again."
2. CAROUSELS: Ranked by SAVES. Slide 1 must have an impossible-to-ignore curiosity gap; Slides 2-6 must be screenshot-worthy utility; Final Slide MUST command: "Save this guide + Follow @puritybeans for daily pure coffee truths."
3. LINKEDIN: Ranked by COMMENTS & DWELL TIME. Hook must provoke in the first 2 lines (before "see more"); end with a debate-igniting question; CTA must invite following Hiten Jain for unfiltered beverage science.
4. THREADS: Ranked by REPLIES & QUOTES. Short, punchy truth-bombs (<480 chars); expose industry tricks; prompt quick debate; end with "Follow for daily coffee truths Big Coffee hides."

THE ONLY QUESTION THAT MATTERS TODAY:
What is the fastest way to gain followers tomorrow? Generate for that."""
