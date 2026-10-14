"""
Schema validation using Pydantic. Defines expected structure for content assets.
"""
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional

class EditorialScore(BaseModel):
    shareability: float
    saveability: float
    emotion_pull: float
    hook_strength: float
    brand_clarity: float
    overall: float
    verdict: str
    feedback: Optional[str] = ""

class ReelFrame(BaseModel):
    on_screen: str = Field(..., min_length=1)
    spoken: str = Field(..., min_length=1)

class ReelSchema(BaseModel):
    id: Optional[str] = None
    hook_archetype: Optional[str] = None
    hook_text: str = Field(..., min_length=1)
    hook_spoken: Optional[str] = None
    frames: List[ReelFrame] = Field(..., min_length=5)
    primary_cta: Optional[str] = None
    cta: Optional[str] = None
    loop_note: Optional[str] = None
    alt_hook: Optional[str] = None
    caption: str = Field(..., min_length=50)
    comment_trigger: str = Field(..., min_length=10)
    save_trigger: str = Field(..., min_length=10)
    share_trigger: str = Field(..., min_length=10)
    hashtags: str = Field(..., min_length=10)
    seo_keywords: Optional[List[str]] = None
    visual_direction: Optional[str] = None
    music_vibe: Optional[str] = None
    whatsapp_forward: Optional[str] = None
    ai_image_hook_prompt: Optional[str] = None
    ai_video_motion_prompt: Optional[str] = None
    hook_options: Optional[List[str]] = None
    hook_ab: Optional[list] = None
    thumbnail_options: Optional[list] = None
    reference_jar_paths: Optional[List[str]] = None
    hook_visual_concept: Optional[str] = None
    hook_text_overlay: Optional[str] = None
    editorial_score: Optional[EditorialScore] = None
    objective: Optional[str] = None
    success_metric: Optional[str] = None
    target: Optional[int] = None
    psychology_frame: Optional[str] = None

class CarouselSlide(BaseModel):
    slide: int
    heading: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    visual: str = Field(..., min_length=1)

class CarouselSchema(BaseModel):
    id: Optional[str] = None
    save_mechanic: Optional[str] = None
    title: str = Field(..., min_length=1)
    slides: List[CarouselSlide] = Field(..., min_length=6, max_length=8)
    caption: str = Field(..., min_length=50)
    cta: Optional[str] = None
    comment_trigger: str = Field(..., min_length=10)
    save_trigger: str = Field(..., min_length=10)
    share_trigger: str = Field(..., min_length=10)
    hashtags: str = Field(..., min_length=10)
    seo_keywords: Optional[List[str]] = None
    editorial_score: Optional[EditorialScore] = None
    objective: Optional[str] = None
    primary_cta: Optional[str] = None
    success_metric: Optional[str] = None
    target: Optional[int] = None
    psychology_frame: Optional[str] = None

    @model_validator(mode="after")
    def validate_final_slide(self) -> 'CarouselSchema':
        if not self.slides:
            return self
        final_slide = self.slides[-1]
        text = (final_slide.heading + " " + final_slide.body).lower()
        if "p3online.in" not in text:
            raise ValueError("Final carousel slide missing website")
        if "purity beans" not in text:
            raise ValueError("Final carousel slide missing product mention")
        return self

class InstagramSchema(BaseModel):
    caption: str = Field(..., min_length=50)
    cta: Optional[str] = None
    comment_trigger: str = Field(..., min_length=10)
    save_trigger: str = Field(..., min_length=10)
    share_trigger: str = Field(..., min_length=10)
    hashtags: str = Field(..., min_length=10)
    seo_keywords: Optional[List[str]] = None
    image_prompt: Optional[str] = None
    image_alt: Optional[str] = None
    post_type: Optional[str] = None
    hook_line: Optional[str] = None
    editorial_score: Optional[EditorialScore] = None
    objective: Optional[str] = None
    primary_cta: Optional[str] = None
    success_metric: Optional[str] = None
    target: Optional[int] = None

class LinkedinSchema(BaseModel):
    hook: str = Field(..., min_length=20)
    body: str = Field(..., min_length=300)
    cta: str = Field(..., min_length=20)
    hashtags: str = Field(..., min_length=10)
    angle: Optional[str] = None
    brand_bridge: Optional[str] = None
    closing_question: Optional[str] = None
    image_prompt: Optional[str] = None
    objective: Optional[str] = None
    primary_cta: Optional[str] = None
    success_metric: Optional[str] = None
    target: Optional[int] = None

class BlogSchema(BaseModel):
    title: str = Field(..., min_length=1)
    meta_description: str = Field(..., min_length=1)
    introduction: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1000)
    conclusion: str = Field(..., min_length=1)
    objective: Optional[str] = None
    primary_cta: Optional[str] = None
    success_metric: Optional[str] = None
    target: Optional[int] = None

    @model_validator(mode="after")
    def validate_length(self) -> 'BlogSchema':
        intro = self.introduction or ""
        body = self.body or ""
        conclusion = self.conclusion or ""
        total_words = len((intro + " " + body + " " + conclusion).split())
        if total_words < 800:
            raise ValueError("Blog must contain at least 800 words")
        return self

class YoutubeShortScene(BaseModel):
    scene: int
    type: str = Field(..., min_length=1)
    duration_s: float
    on_screen: str = Field(..., min_length=1)
    spoken: str = Field(..., min_length=1)
    visual_direction: str = Field(..., min_length=1)

class YoutubeShortSchema(BaseModel):
    # Format 1 (simplified)
    hook: Optional[str] = Field(None, min_length=10)
    script: Optional[str] = Field(None, min_length=50)
    cta: Optional[str] = Field(None, min_length=10)

    # Format 2 (scene-based)
    product: Optional[str] = Field(None, min_length=1)
    tagline: Optional[str] = Field(None, min_length=1)
    emotion_arc: Optional[str] = Field(None, min_length=1)
    scenes: Optional[List[YoutubeShortScene]] = Field(None, min_length=5)
    audio_direction: Optional[str] = Field(None, min_length=1)
    edit_pacing: Optional[str] = Field(None, min_length=1)

    title: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    objective: Optional[str] = None
    primary_cta: Optional[str] = None
    success_metric: Optional[str] = None
    target: Optional[int] = None
    audience: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_target(cls, data):
        """Models often write the target AUDIENCE into `target` (run 38602719185:
        'Urban Indian coffee drinkers ...'). Keep a numeric target as int; move
        prose into `audience` instead of failing the whole Short."""
        if isinstance(data, dict) and "target" in data:
            data = dict(data)
            data["target"] = coerce_target(data.get("target"), data)
        return data

    @model_validator(mode="after")
    def validate_youtube_short(self) -> 'YoutubeShortSchema':
        has_format1 = (
            self.hook is not None
            and self.script is not None
            and self.cta is not None
        )
        has_format2 = (
            self.product is not None
            and self.tagline is not None
            and self.scenes is not None
            and len(self.scenes) >= 5
        )
        if not (has_format1 or has_format2):
            raise ValueError(
                "YouTube Short must contain either (hook, script, cta) or (product, tagline, scenes >= 5)"
            )
        return self

def validate_or_fail(schema, payload):
    """Validate payload against Pydantic schema. Raises ValidationError on failure."""
    return schema.model_validate(payload)


def coerce_target(value, data: dict | None = None):
    """Return an int target or None. Non-numeric prose is moved to data['audience']."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip().replace(",", "")
    if text.isdigit():
        return int(text)
    if data is not None and text and not data.get("audience"):
        data["audience"] = str(value).strip()
    return None
