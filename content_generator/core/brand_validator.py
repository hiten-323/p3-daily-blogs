"""
Brand copy validator — validates text assets against language requirements,
required brand facts, prohibited claims, and website references.
"""
import logging
from content_generator.core.brand_guard import (
    BRAND, FORBIDDEN_TERMS, BRAND_FACTS, WEBSITE_PATTERNS, BRAND_FACT_ALIASES,
    STRICT_LANGUAGE_MODE, MIN_COPY_LENGTH
)

logger = logging.getLogger(__name__)

def validate_language(text: str) -> bool:
    """
    Validate that the text is in English.
    For short text (under 50 characters), skip detection to avoid false positives.
    """
    cleaned = text.strip()
    if len(cleaned) < 50:
        return True
    try:
        from langdetect import detect
        return detect(cleaned) == "en"
    except Exception as e:
        logger.error("Language detection failed: %s", e)
        if STRICT_LANGUAGE_MODE:
            return False
        return True

def validate_brand_facts(text: str) -> bool:
    """
    Check if the text contains at least one of the required brand facts
    or their configured aliases.
    """
    text_lower = text.lower()
    
    # Check core claims from BRAND_FACTS
    for fact in BRAND_FACTS["core_claims"]:
        if fact.lower() in text_lower:
            return True
            
    # Check aliases from BRAND_FACT_ALIASES
    for fact_name, aliases in BRAND_FACT_ALIASES.items():
        for alias in aliases:
            if alias.lower() in text_lower:
                return True
                
    return False

def validate_brand_mention(text: str) -> bool:
    """Check if 'purity beans' is in text."""
    return "purity beans" in text.lower()

def validate_no_prohibited_claims(text: str) -> bool:
    """
    Verify that no forbidden medical/unsupported claims are made.
    Returns True if clean, False if forbidden term found.
    """
    text_lower = text.lower()
    for term in FORBIDDEN_TERMS:
        if term.lower() in text_lower:
            logger.warning("Prohibited claim detected: '%s'", term)
            return False
    return True

def validate_website(text: str) -> bool:
    """
    Validate that the Purity Beans website is referenced using approved patterns.
    """
    text_lower = text.lower()
    return any(pattern.lower() in text_lower for pattern in WEBSITE_PATTERNS)

def validate_asset_copy(
    text: str,
    check_brand_facts: bool = True,
    check_website: bool = False,
    check_brand_mention: bool = True,
    check_length: bool = True
) -> tuple[bool, list[str]]:
    """
    Perform all brand validations in order:
    1. Empty check
    2. Language check
    3. Brand mention check
    4. Brand facts check
    5. Prohibited claims check
    6. Website check
    7. Minimum length check
    """
    issues = []
    
    # 1. Empty check
    if not text or not text.strip():
        return False, ["Empty content"]
        
    # 2. Language check
    if not validate_language(text):
        issues.append("Language is not English")
        
    # 3. Brand mention check
    if check_brand_mention and not validate_brand_mention(text):
        issues.append("Missing brand mention")
        
    # 4. Brand facts check
    if check_brand_facts and not validate_brand_facts(text):
        issues.append("Missing required brand facts")
        
    # 5. Prohibited claims check
    if not validate_no_prohibited_claims(text):
        issues.append("Contains prohibited medical or weight loss claims")
        
    # 6. Website check
    if check_website and not validate_website(text):
        issues.append("Missing website reference")
        
    # 7. Minimum length check
    if check_length and len(text.strip()) < MIN_COPY_LENGTH:
        issues.append(f"Content too short (< {MIN_COPY_LENGTH} chars)")
        
    return len(issues) == 0, issues

def validate_asset(label: str, piece: dict,
                   psychology_governance: dict = None) -> tuple[bool, list[str]]:
    """
    Validate a complete content asset dictionary based on its type.

    psychology_governance carries the selected frame's risk rules. These are
    ENFORCED here, not described:

      require_claim_verification  -> every factual assertion must be backed by
                                     the verified-fact set, or the asset fails
      require_source_backing      -> additionally, nothing that would need a
                                     citation may remain
      require_manual_review       -> high-risk frames never auto-publish

    The earlier form was `if require_claim_verification: pass`, so a medium-risk
    frame promised verification and performed none.
    """
    if psychology_governance:
        from content_generator.core.claim_verifier import (
            verify_piece, requires_source_backing,
        )
        findings = []
        if (psychology_governance.get("require_claim_verification")
                or psychology_governance.get("require_source_backing")):
            findings = verify_piece(piece)

        if psychology_governance.get("require_claim_verification") and findings:
            return False, [f"unverified {f['type']}: {f['claim']} ({f['reason']})"
                           for f in findings]

        if psychology_governance.get("require_source_backing"):
            needs_source = requires_source_backing(findings)
            if needs_source:
                return False, [f"claim needs source backing: {f['claim']}"
                               for f in needs_source]

        if psychology_governance.get("require_manual_review"):
            return False, ["High risk frame requires explicit manual review before publish"]

    if not isinstance(piece, dict) or not piece:
        return False, ["Empty content dictionary"]

    # Normalize labels
    clean_label = label.lower().strip()
    is_valid = True
    issues = []

    # 1. Run brand validations
    if clean_label in ("reel_1", "reel_2"):
        caption = piece.get("caption", "")
        # Validate Reel caption (requires brand facts, website, mention, length)
        is_ok, caption_issues = validate_asset_copy(caption, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)
        if not is_ok:
            is_valid = False
            issues.extend([f"Reel caption error: {caption_issues}"])
            
        # Validate Reel overlays (on_screen text inside frames) - naturally short, no facts/website/length/mention
        frames = piece.get("frames") or []
        for i, frame in enumerate(frames):
            if isinstance(frame, dict):
                on_screen = frame.get("on_screen", "")
                is_frame_ok, frame_issues = validate_asset_copy(
                    on_screen, 
                    check_brand_facts=False, 
                    check_website=False, 
                    check_brand_mention=False, 
                    check_length=False
                )
                if not is_frame_ok:
                    is_valid = False
                    issues.extend([f"Reel frame {i+1} overlay error: {frame_issues}"])

    elif clean_label == "carousel":
        caption = piece.get("caption", "")
        # Validate Carousel caption (requires brand facts, website, mention, length)
        is_ok, caption_issues = validate_asset_copy(caption, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)
        if not is_ok:
            is_valid = False
            issues.extend([f"Carousel caption error: {caption_issues}"])
            
        # Validate Carousel slides (heading/body) - naturally short
        slides = piece.get("slides") or []
        for i, slide in enumerate(slides):
            if isinstance(slide, dict):
                slide_text = f"{slide.get('heading', '')} {slide.get('body', '')}"
                is_slide_ok, slide_issues = validate_asset_copy(
                    slide_text,
                    check_brand_facts=False,
                    check_website=False,
                    check_brand_mention=False,
                    check_length=False
                )
                if not is_slide_ok:
                    is_valid = False
                    issues.extend([f"Carousel slide {i+1} error: {slide_issues}"])

    elif clean_label == "instagram_post":
        caption = piece.get("caption", "")
        is_valid, issues = validate_asset_copy(caption, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)

    elif clean_label == "linkedin_post":
        combined_text = f"{piece.get('hook', '')} {piece.get('body', '')} {piece.get('cta', '')}"
        is_valid, issues = validate_asset_copy(combined_text, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)

    elif clean_label == "blog_post":
        combined_text = " ".join(
            str(piece.get(key) or "")
            for key in ("title", "introduction", "intro", "body", "body_html", "conclusion", "meta_description")
        )
        is_valid, issues = validate_asset_copy(combined_text, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)
        from content_generator.core.blog_quality import assess
        extra = assess(piece)
        if extra:
            is_valid = False
            issues.extend(extra)

    elif clean_label == "threads_post":
        # Threads is intentionally native, short, and link-light. Do not impose
        # the website/brand-fact requirements used for sales-oriented assets.
        native_text = str(piece.get("text") or piece.get("body") or piece.get("content") or "").strip()
        is_valid, issues = validate_asset_copy(
            native_text,
            check_brand_facts=False,
            check_website=False,
            check_brand_mention=False,
            check_length=True,
        )
        if len(native_text) > 480:
            is_valid = False
            issues.append("Threads native text exceeds 480 characters")

    elif clean_label == "yt_short":
        # Support both Format 1 (hook/script/cta) and Format 2 (scenes)
        if "scenes" in piece and piece["scenes"]:
            scenes = piece.get("scenes") or []
            combined_text = " ".join([f"{s.get('on_screen', '')} {s.get('spoken', '')}" for s in scenes if isinstance(s, dict)])
            combined_text = f"{piece.get('product', '')} {piece.get('tagline', '')} {combined_text}"
        else:
            combined_text = f"{piece.get('hook', '')} {piece.get('script', '')} {piece.get('cta', '')}"
            
        is_valid, issues = validate_asset_copy(combined_text, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)

    elif clean_label == "growth_reel" or str(piece.get("track") or "").strip().lower() == "growth":
        # Growth-track reels are non-branded on purpose. Requiring "Purity Beans"
        # here rejected every growth reel the prompt is instructed to write.
        caption = piece.get("caption", "")
        is_ok, caption_issues = validate_asset_copy(
            caption,
            check_brand_facts=False,
            check_website=False,
            check_brand_mention=False,
            check_length=True,
        )
        if not is_ok:
            is_valid = False
            issues.extend([f"Growth reel caption error: {caption_issues}"])

    else:
        # Fallback validation for any other type
        combined_text = " ".join([str(v) for v in piece.values() if isinstance(v, str)])
        is_valid, issues = validate_asset_copy(combined_text, check_brand_facts=True, check_website=True, check_brand_mention=True, check_length=True)

    # 2. Instagram Native Quality Gate integration
    if clean_label in ("reel_1", "reel_2", "growth_reel", "carousel", "instagram_post", "stories"):
        try:
            from content_generator.creative.instagram_quality_gate import publish_decision
            
            # Map pieces to quality gate parameters
            if clean_label in ("reel_1", "reel_2"):
                copy_text = piece.get("hook_text") or piece.get("caption") or ""
                surface = "reel"
                reel_plan = piece
            elif clean_label == "growth_reel":
                copy_text = piece.get("chosen_hook") or piece.get("caption") or ""
                surface = "reel"
                reel_plan = piece
            elif clean_label == "carousel":
                copy_text = piece.get("title") or piece.get("caption") or ""
                surface = "carousel"
                reel_plan = None
            elif clean_label == "stories":
                copy_text = piece.get("hook") or piece.get("chosen_hook") or piece.get("caption") or ""
                surface = "story"
                reel_plan = None
            else:  # instagram_post
                copy_text = piece.get("caption") or ""
                surface = "post"
                reel_plan = None
                
            gate_res = publish_decision(copy_text=copy_text, surface=surface, reel_plan=reel_plan)
            if not gate_res["allow_publish"]:
                is_valid = False
                issues.extend(gate_res["issues"])
        except Exception as e:
            logger.warning("[validator] instagram quality gate exception: %s", e)

    return is_valid, issues
