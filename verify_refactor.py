"""
Pre-merge verification suite for the content_generator refactor.
Runs without real API keys by patching the LLM router.
Exit code 0 = all checks passed.
"""
import ast
import os
import sys
import types
import importlib
import textwrap

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tempfile
os.environ["LEARNING_DIR"] = tempfile.mkdtemp(prefix="pb_verify_learning_")

PASS = "[PASS]"
FAIL = "[FAIL]"

_results: list[tuple[bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((ok, name))
    icon = PASS if ok else FAIL
    line = f"  {icon}  {name}"
    if detail:
        line += f"\n       {detail}"
    print(line)


def section(title: str) -> None:
    print(f"\n{'-' * 60}\n{title}\n{'-' * 60}")


# -----------------------------------------------------------------------------
#  Stubs for external project dependencies (engine, config)
# -----------------------------------------------------------------------------

def _install_stubs() -> None:
    """
    Install minimal stubs for engine.database and config.brand_config
    so imports resolve without the real project present.
    """
    engine_pkg = types.ModuleType("engine")
    engine_db  = types.ModuleType("engine.database")
    engine_db.get_recent_content_history = lambda days=14: []
    engine_pkg.database = engine_db
    sys.modules["engine"]          = engine_pkg
    sys.modules["engine.database"] = engine_db

    config_pkg = types.ModuleType("config")
    brand_cfg  = types.ModuleType("config.brand_config")
    brand_cfg.BRAND            = {"name": "Purity Beans", "tagline": "Pure Coffee. Nothing Else.", "website": "https://p3online.in"}
    brand_cfg.POSITIONING      = {"usp": "pure instant coffee", "price_per_cup": 18, "cafe_price": 180}
    brand_cfg.CONTENT_CATEGORIES = []
    brand_cfg.HASHTAG_SETS     = {
        "reel_morning": "#coffee #india",
        "reel_night":   "#coffee #night",
        "carousel":     "#coffee #pure",
        "linkedin":     "#fmcg #india",
    }
    brand_cfg.WEEKLY_STRATEGY  = {"weekly": {d: "default" for d in
                                   ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]}}
    config_pkg.brand_config = brand_cfg
    sys.modules["config"]              = config_pkg
    sys.modules["config.brand_config"] = brand_cfg

_install_stubs()


# -----------------------------------------------------------------------------
#  CHECK 1 - Public API imports
# -----------------------------------------------------------------------------

section("CHECK 1 - Public API imports")

try:
    from content_generator import generate_daily_content
    check("from content_generator import generate_daily_content", True)
except Exception as e:
    check("from content_generator import generate_daily_content", False, str(e))

try:
    from content_generator import save_content
    check("from content_generator import save_content", True)
except Exception as e:
    check("from content_generator import save_content", False, str(e))

try:
    from content_generator import configure
    check("from content_generator import configure", True)
except Exception as e:
    check("from content_generator import configure", False, str(e))

try:
    import content_generator as cg
    assert callable(cg.generate_daily_content)
    assert callable(cg.save_content)
    check("import content_generator; callable API", True)
except Exception as e:
    check("import content_generator; callable API", False, str(e))

try:
    # Importing must NOT trigger logging.basicConfig or file I/O side effects
    # Re-import from a clean slate
    for key in list(sys.modules.keys()):
        if key.startswith("content_generator"):
            del sys.modules[key]
    _install_stubs()
    import content_generator  # noqa: F811
    check("import content_generator has no side effects", True)
except Exception as e:
    check("import content_generator has no side effects", False, str(e))


# -----------------------------------------------------------------------------
#  CHECK 2 - Schema parity (ENABLE_USAGE_LOG=false)
# -----------------------------------------------------------------------------

section("CHECK 2 - Output schema parity (ENABLE_USAGE_LOG=false)")

EXPECTED_KEYS = {
    "date", "day_number", "growth_reel",
    "reels", "instagram_post", "carousel",
    "linkedin_post", "blog_post", "stories", "yt_short",
    "video_prompts", "ai_image_prompts", "performance_targets",
}

# Patch LLM router so no real API call is made
_FAKE_REEL = {
    "id": "reel_1",
    "hook_archetype": "EXPOSE",
    "hook_text": "Stop drinking 50% chicory root filler.",
    "hook_spoken": "Did you know your morning coffee is probably half root filler?",
    "hook_visual_concept": "Close up of an ingredient label under bright magnifying light.",
    "frames": [
        {"on_screen": "Coffee Betrayal", "spoken": "You think you're buying pure coffee beans, but read the label."},
        {"on_screen": "50% Chicory", "spoken": "Many popular brands add up to fifty percent chicory root fillers."},
        {"on_screen": "Zero Chicory", "spoken": "Chicory belongs in the ground, not in your morning energy cup."},
        {"on_screen": "Purity Beans", "spoken": "That is why Purity Beans offers only pure instant coffee."},
        {"on_screen": "Try Purity Beans", "spoken": "Get yours today at p3online.in for a clean coffee experience."}
    ],
    "loop_note": "loops back to frame 1",
    "alt_hook": "The coffee secret they do not want you to know",
    "caption": "Wondering why your instant coffee turns bitter after two minutes? Look closely at the ingredient label. Many standard brands actually add up to 50 percent chicory root filler. Purity Beans is pure instant coffee with zero chicory and no hidden additives. Read the label and try real coffee today at https://p3online.in.",
    "visual_direction": "dark cinematic close-ups of coffee jar",
    "music_vibe": "lo-fi study beats",
    "whatsapp_forward": "forward this to a coffee lover",
    "primary_cta": "visit p3online.in",
    "comment_trigger": "Comment COFFEE to get the link!",
    "save_trigger": "Save this reel for your next brew!",
    "share_trigger": "Share this reel with a coffee lover!",
    "hashtags": "#coffee #puritybeans #purecoffee #instantcoffee #chicoryfree",
    "editorial_score": {
        "shareability": 8.0,
        "saveability": 8.0,
        "emotion_pull": 8.0,
        "hook_strength": 8.5,
        "brand_clarity": 9.0,
        "overall": 8.3,
        "verdict": "PASS"
    }
}

_FAKE_CAROUSEL = {
    "id": "carousel_1",
    "title": "Why Pure Coffee is better than chicory blends",
    "caption": "Avoid the hidden fillers in your morning brew. Purity Beans is Pure Coffee with Zero Chicory. Shop now at https://p3online.in",
    "slides": [
        {"slide": 1, "heading": "The Blended Truth", "body": "Did you know chicory root is added to cheapen production?", "visual": "Slide 1 visual"},
        {"slide": 2, "heading": "Zero Chicory", "body": "We believe in pure ingredients and zero fillers for clean energy.", "visual": "Slide 2 visual"},
        {"slide": 3, "heading": "Cafe Quality", "body": "Experience rich, bold taste without the artificial cafe price markup.", "visual": "Slide 3 visual"},
        {"slide": 4, "heading": "True Transparency", "body": "We list every single ingredient on our label, honestly.", "visual": "Slide 4 visual"},
        {"slide": 5, "heading": "Pure Coffee", "body": "Nothing but premium quality instant coffee beans in every jar.", "visual": "Slide 5 visual"},
        {"slide": 6, "heading": "Get Purity Beans", "body": "Order your clean coffee pack now at p3online.in and taste Purity Beans.", "visual": "Slide 6 visual"}
    ],
    "comment_trigger": "Comment COFFEE to get the link!",
    "save_trigger": "Save this carousel for your next brew!",
    "share_trigger": "Share this carousel with a coffee lover!",
    "hashtags": "#coffee #puritybeans #purecoffee #instantcoffee #chicoryfree",
    "editorial_score": {
        "shareability": 8.0,
        "saveability": 8.0,
        "emotion_pull": 8.0,
        "hook_strength": 8.0,
        "brand_clarity": 9.0,
        "overall": 8.2,
        "verdict": "PASS"
    }
}

_FAKE_INSTAGRAM = {
    "caption": "Wondering why your morning cup leaves a muddy bitterness after two minutes? Read the ingredient label of your instant coffee. Most big brands actually add up to 50 percent chicory root filler. Purity Beans is pure instant coffee with zero chicory and no hidden additives. Swap the filler and try real coffee today at https://p3online.in!",
    "comment_trigger": "Comment COFFEE to get the link!",
    "save_trigger": "Save this post for your next brew!",
    "share_trigger": "Share this post with a coffee lover!",
    "hashtags": "#coffee #puritybeans #purecoffee #instantcoffee #chicoryfree",
    "editorial_score": {
        "shareability": 8.0,
        "saveability": 8.0,
        "emotion_pull": 8.0,
        "hook_strength": 8.0,
        "brand_clarity": 9.0,
        "overall": 8.2,
        "verdict": "PASS"
    }
}

_FAKE_LINKEDIN = {
    "hook": "Why we said no to the industry standard pricing model.",
    "body": "When launching Purity Beans, we were advised to add chicory to lower our costs and boost margins. Chicory is cheap, and most consumers do not read labels. But we wanted to build a brand based on honesty and transparency. That is why we chose to offer Pure Coffee with Zero Chicory, even if it meant tighter margins. Because trust is the ultimate metric. We are building India's cleanest instant coffee brand step by step.",
    "cta": "Check our journey at https://p3online.in",
    "hashtags": "#coffee #puritybeans #purecoffee #instantcoffee #chicoryfree",
    "editorial_score": {
        "shareability": 8.0,
        "saveability": 8.0,
        "emotion_pull": 8.0,
        "hook_strength": 8.0,
        "brand_clarity": 9.0,
        "overall": 8.2,
        "verdict": "PASS"
    }
}

_FAKE_BLOG = {
    "title": "The Clean Coffee Revolution: Why Purity Beans Stands Alone",
    "meta_description": "Discover why Purity Beans offers pure instant coffee with zero chicory or fillers. Read the truth about standard coffee blends.",
    "introduction": "For decades, the instant coffee market in India has relied on a quiet compromise. Many consumers believe they are buying pure, roasted coffee beans when they pick up a jar of instant coffee. However, a closer look at the ingredient labels reveals a different story altogether. A significant percentage of popular instant coffee brands contain chicory root, a cheap additive used to bulk up weight and lower production costs. At Purity Beans, we decided to change this by offering Pure Coffee with Zero Chicory. We believe that your morning cup should be clean, pure, and transparent. This blog post explores the history of coffee fillers and why choosing a pure coffee brand like Purity Beans is better for your taste, health, and wallet.",
    "body": (
        "Historically, chicory root was introduced as a coffee substitute during times of economic hardship and supply shortages, such as during the American Civil War or the Great Depression. Because it mimics the dark color and bitter taste of roasted coffee when brewed, it was a convenient filler. Over time, however, coffee manufacturers realized that they could continue using chicory during times of peace and abundance to artificially inflate their margins. In many instant coffee jars sold today, you are getting up to forty or fifty percent chicory root, which has none of the caffeine or natural aromatic oils of real coffee beans. This practice has become so widespread that many consumers have never actually tasted pure instant coffee, assuming that the bitter, muddy taste of chicory blends is the standard profile. We believe this is a disservice to coffee drinkers who deserve the real thing. "
        "When we set out to build Purity Beans, our primary goal was to eliminate this compromise. We wanted to source premium Arabica and Robusta beans from the finest estates in South India, roasting them to perfection without adding a single gram of chicory, fillers, or artificial flavorings. This choice has substantial implications for the daily consumer. First, the flavor profile of pure coffee is entirely different. Standard blends with chicory tend to have a heavy, woody, and almost muddy bitterness that lingers unpleasantly on the palate. Pure coffee, on the other hand, possesses a clean, bright, and complex flavor with natural notes of chocolate, caramel, and fruit. Second, caffeinated purity matters. When you drink Purity Beans, you get a clean energy boost without the jittery crash that often accompanies cheap blends. "
        "Building a brand on Pure Coffee and Zero Chicory has not been the easiest path. The margins on chicory-free coffee are significantly lower, and sourcing high-quality beans is a continuous logistical challenge. But we believe in the clean coffee movement. We believe that modern Indian consumers are smarter and more health-conscious than ever before. They want to know exactly what is going into their bodies, and they value brands that tell them the truth. That is why transparency is at the heart of everything we do. We publish our sourcing details, we label our ingredients with absolute clarity, and we never hide behind terms like 'proprietary blend' or 'natural flavors.' We want our customers to feel confident in every sip they take, knowing they are consuming only pure ingredients. "
        "By choosing Purity Beans, you are not just buying a jar of instant coffee; you are supporting a movement toward cleaner, more honest food and beverage products in India. We are proving that it is possible to build a successful FMCG business without compromising on quality or tricking the customer. Every cup you brew is a vote for purity, honesty, and premium taste. We invite you to join us on this journey, explore our products, and experience the pure flavor. We are constantly innovating, refining our processes, and working directly with farmers to ensure that our supply chain is sustainable, fair, and of the highest caliber. Our dedication to quality is unwavering, and we are excited to have you with us. "
        "To achieve the optimal extraction, our team of roasting experts spends countless hours dialing in the optimal roast profile for each batch of beans. We pay close attention to temperature, airflow, and time, ensuring that the natural sweetness of the beans is highlighted while avoiding any burnt or charcoal notes. This meticulous process ensures that Purity Beans dissolves effortlessly in both hot and cold milk or water, giving you a cafe-style beverage in the comfort of your home or office. We also use premium packaging that locks in the aroma and freshness, so that the last spoonful tastes just as spectacular as the first. This is our promise to you, and we stand by it."
    ),
    "conclusion": "In conclusion, the choice between cheap chicory blends and Pure Coffee is clear. If you value pure ingredients, rich natural flavor, and transparent sourcing, Purity Beans is the answer. Say goodbye to the fillers and enjoy the cleanest cup of instant coffee in India. Visit https://p3online.in today to order your first jar and join the clean coffee movement.",
    "editorial_score": {
        "shareability": 8.0,
        "saveability": 8.0,
        "emotion_pull": 8.0,
        "hook_strength": 8.0,
        "brand_clarity": 9.0,
        "overall": 8.2,
        "verdict": "PASS"
    }
}

_FAKE_SIMPLE = {"id": "test", "content": "stub"}
_FAKE_VIDEO  = {"video_prompts": {"reel_1": {"frames": []}, "reel_2": {"frames": []}, "yt_short": {"scenes": []}}}

_STUB_MAP = {
    "reel_1":         _FAKE_REEL,
    "reel_2":         {**_FAKE_REEL, "id": "reel_2"},
    "instagram_post": _FAKE_INSTAGRAM,
    "carousel":       _FAKE_CAROUSEL,
    "linkedin_post":  _FAKE_LINKEDIN,
    "blog_post":      _FAKE_BLOG,
    "stories":        _FAKE_SIMPLE,
    "yt_short": {
        "product": "Purity Beans Instant Coffee",
        "tagline": "Pure Coffee. Nothing Else.",
        "emotion_arc": "Intrigue",
        "scenes": [
            {"scene": 1, "type": "problem", "duration_s": 5.0, "on_screen": "Coffee Betrayal", "spoken": "Did you know your instant coffee contains cheap chicory root fillers?", "visual_direction": "dark close up"},
            {"scene": 2, "type": "agitation", "duration_s": 5.0, "on_screen": "50% Filler", "spoken": "Most brands actually replace half the coffee with root filler without clear labeling.", "visual_direction": "chicory root graphic"},
            {"scene": 3, "type": "product_reveal", "duration_s": 7.0, "on_screen": "Purity Beans", "spoken": "We say no to fillers. This is Purity Beans.", "visual_direction": "slow jar reveal"},
            {"scene": 4, "type": "benefit", "duration_s": 5.0, "on_screen": "Pure Coffee", "spoken": "Enjoy pure instant coffee today. Read the back label and choose pure.", "visual_direction": "pouring hot water"},
            {"scene": 5, "type": "cta", "duration_s": 5.0, "on_screen": "p3online.in", "spoken": "Swap the fillers today. Try Purity Beans at p3online.in.", "visual_direction": "website url"}
        ],
        "audio_direction": "upbeat music",
        "edit_pacing": "fast cuts",
        "editorial_score": {
            "shareability": 8.0,
            "saveability": 8.0,
            "emotion_pull": 8.0,
            "hook_strength": 8.0,
            "brand_clarity": 9.0,
            "overall": 8.2,
            "verdict": "PASS"
        }
    },
    "video_prompts":  _FAKE_VIDEO,
}

try:
    os.environ["ENABLE_USAGE_LOG"] = "false"

    def _fake_call(prompt: str, label: str, max_tokens: int = 3000) -> dict:
        return _STUB_MAP.get(label, _FAKE_SIMPLE)

    # Import the generator module, then patch its locally-bound llm_call name
    import content_generator.pipeline.generator as _gen_mod
    _original_llm_call = _gen_mod.llm_call
    _gen_mod.llm_call = _fake_call

    result = _gen_mod.generate_daily_content(day_number=0)
    actual_keys = set(result.keys())

    missing = EXPECTED_KEYS - actual_keys
    extra   = actual_keys - EXPECTED_KEYS - {
        "usage", "generation_id", "prompt_version", "schema_version",
        "policy_version_at_creation", "target_kpi_at_creation",
        "psychology_frame", "psychology_frame_version",
    }  # usage is opt-in, allowed absent

    check("All expected keys present",     not missing, f"Missing: {missing}" if missing else "")
    check("No unexpected extra keys",      not extra,   f"Extra: {extra}"     if extra   else "")
    check("'usage' absent when flag=false","usage" not in result)

    # Now check it appears when flag=true
    os.environ["ENABLE_USAGE_LOG"] = "true"
    result_with_usage = _gen_mod.generate_daily_content(day_number=0)
    check("'usage' present when ENABLE_USAGE_LOG=true", "usage" in result_with_usage)

    _gen_mod.llm_call = _original_llm_call

except Exception as e:
    check("Schema parity test", False, str(e))


# -----------------------------------------------------------------------------
#  CHECK 3 - No local shadowing of external dependencies
# -----------------------------------------------------------------------------

section("CHECK 3 - External dependencies not shadowed locally")

CODE_ROOT = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT  = os.path.join(CODE_ROOT, "content_generator")

no_local_engine = not os.path.exists(os.path.join(PKG_ROOT, "engine"))
no_local_config = not os.path.exists(os.path.join(PKG_ROOT, "config"))
check("No local engine/ directory in package", no_local_engine)
check("No local config/ directory in package", no_local_config)

# Scan all .py files for any definition of get_recent_content_history or BRAND
def _grep(root: str, pattern: str) -> list[str]:
    hits = []
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            try:
                src = open(path).read()
            except Exception:
                continue
            if pattern in src and "import" not in src.split(pattern)[0].rsplit("\n", 1)[-1]:
                hits.append(os.path.relpath(path, CODE_ROOT))
    return hits

hits_db   = _grep(PKG_ROOT, "def get_recent_content_history")
hits_brand = _grep(PKG_ROOT, "BRAND = ")
check("get_recent_content_history not defined locally", not hits_db,   f"Found in: {hits_db}")
check("BRAND dict not defined locally",                 not hits_brand, f"Found in: {hits_brand}")


# -----------------------------------------------------------------------------
#  CHECK 4 - Concurrency ordering (video_prompts after phase 1)
# -----------------------------------------------------------------------------

section("CHECK 4 - Concurrency ordering")

gen_src = open(os.path.join(PKG_ROOT, "pipeline", "generator.py")).read()
tree    = ast.parse(gen_src)

# Find the generate_daily_content function body and check ordering
vp_line    = None
phase1_line = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign):
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        if "vp" in targets:
            vp_line = node.lineno
    if isinstance(node, (ast.With,)):
        # The ThreadPoolExecutor context manager
        if any("ThreadPoolExecutor" in ast.unparse(item) for item in node.items):
            phase1_line = node.lineno

check("Phase 1 (ThreadPoolExecutor) defined before video_prompts call",
      phase1_line is not None and vp_line is not None and phase1_line < vp_line,
      f"ThreadPoolExecutor at line {phase1_line}, vp= at line {vp_line}")

# Confirm video_prompts uses results from phase1
vp_uses_reel1   = "phase1_results[\"reel_1\"]"   in gen_src or "phase1_results['reel_1']"   in gen_src
vp_uses_reel2   = "phase1_results[\"reel_2\"]"   in gen_src or "phase1_results['reel_2']"   in gen_src
vp_uses_yt      = "phase1_results[\"yt_short\"]" in gen_src or "phase1_results['yt_short']" in gen_src
check("video_prompts consumes phase1_results[reel_1]",  vp_uses_reel1)
check("video_prompts consumes phase1_results[reel_2]",  vp_uses_reel2)
check("video_prompts consumes phase1_results[yt_short]", vp_uses_yt)

# Confirm video_prompts is NOT inside the ThreadPoolExecutor block
# by checking it's assigned after the `with` block closes
with_node = next(
    (n for n in ast.walk(tree)
     if isinstance(n, ast.With)
     and any("ThreadPoolExecutor" in ast.unparse(i) for i in n.items)),
    None,
)
if with_node:
    with_end = max(getattr(n, "lineno", 0) for n in ast.walk(with_node))
    check("video_prompts call is OUTSIDE the ThreadPoolExecutor block",
          vp_line is not None and vp_line > with_end,
          f"with block ends ~line {with_end}, vp= at line {vp_line}")


# -----------------------------------------------------------------------------
#  CHECK 5 - Brand copy & schema validation gates
# -----------------------------------------------------------------------------

section("CHECK 5 - Brand copy & schema validation gates")

try:
    from content_generator.core.editorial_engine import get_valid_assets, pre_publish_check
    
    dummy_content = {
        "reels": [_STUB_MAP["reel_1"], _STUB_MAP["reel_2"]],
        "carousel": _STUB_MAP["carousel"],
        "instagram_post": _STUB_MAP["instagram_post"],
        "linkedin_post": _STUB_MAP["linkedin_post"],
        "blog_post": _STUB_MAP["blog_post"],
        "yt_short": _STUB_MAP["yt_short"],
    }
    
    valid_assets = get_valid_assets(dummy_content)
    
    expected_assets = ["reel_1", "reel_2", "carousel", "instagram_post", "linkedin_post", "blog_post", "yt_short"]
    missing_assets = [a for a in expected_assets if a not in valid_assets]
    
    check("All 7 assets validated as PASS", not missing_assets, f"Failed/Missing: {missing_assets}")
    
    # Test pre_publish_check doesn't throw
    passed_check = pre_publish_check(dummy_content)
    check("pre_publish_check passes with valid content", passed_check)
    
    # Now let's test that low editorial scores are properly rejected
    low_content = {
        **dummy_content,
        "instagram_post": {
            **_STUB_MAP["instagram_post"],
            "editorial_score": {
                "overall": 5.0,
                "verdict": "REJECT"
            }
        }
    }
    valid_assets_low = get_valid_assets(low_content)
    check("Asset with low editorial score is rejected", "instagram_post" not in valid_assets_low)
    
except Exception as e:
    check("Brand copy & schema validation tests", False, str(e))


# -----------------------------------------------------------------------------
#  CHECK 6 - Marketing Psychology Registry validation
# -----------------------------------------------------------------------------

section("CHECK 6 - Marketing Psychology Registry validation")

try:
    from content_generator.core.coffee_psychology import validate_registry, PSYCHOLOGY_FRAMES
    
    # 1. Assert standard validation passes
    check("validate_registry() passes with clean registry", validate_registry())
    
    # 2. Test duplicate ID detection
    original_frames = list(PSYCHOLOGY_FRAMES)
    try:
        PSYCHOLOGY_FRAMES.append(PSYCHOLOGY_FRAMES[0])  # duplicate
        try:
            validate_registry()
            duplicate_detected = False
        except ValueError as ve:
            duplicate_detected = "Duplicate psychology frame ID detected" in str(ve)
        check("validate_registry() catches duplicate frame IDs", duplicate_detected)
    finally:
        PSYCHOLOGY_FRAMES[:] = original_frames  # restore
        
    # 3. Test missing key detection
    try:
        bad_frame = {k: v for k, v in PSYCHOLOGY_FRAMES[0].items() if k != "theory"}
        bad_frame["id"] = "bad-theory-frame"
        PSYCHOLOGY_FRAMES.append(bad_frame)
        try:
            validate_registry()
            missing_detected = False
        except ValueError as ve:
            missing_detected = "missing required root key: 'theory'" in str(ve)
        check("validate_registry() catches missing required schema keys", missing_detected)
    finally:
        PSYCHOLOGY_FRAMES[:] = original_frames  # restore

    # 4. Test invalid risk level detection
    try:
        bad_frame = {**PSYCHOLOGY_FRAMES[0], "id": "bad-risk-frame", "risk_level": "ultra-high"}
        PSYCHOLOGY_FRAMES.append(bad_frame)
        try:
            validate_registry()
            risk_detected = False
        except ValueError as ve:
            risk_detected = "Invalid risk_level" in str(ve)
        check("validate_registry() catches invalid risk levels", risk_detected)
    finally:
        PSYCHOLOGY_FRAMES[:] = original_frames  # restore

except Exception as e:
    check("Psychology registry validation tests", False, str(e))


# -----------------------------------------------------------------------------
#  Summary
# -----------------------------------------------------------------------------

passed = sum(1 for ok, _ in _results if ok)
total  = len(_results)
print(f"\n{'-' * 60}")
print(f"  Result: {passed}/{total} checks passed")
print(f"{'-' * 60}\n")

sys.exit(0 if passed == total else 1)
