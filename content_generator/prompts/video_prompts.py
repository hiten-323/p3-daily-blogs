"""
Video production prompt builder.
Reads already-generated reel and YT Short dicts and produces
frame-by-frame prompts for Runway / Pika / Kling / human videographers.
"""


def _summarise_reel(r: dict) -> str:
    lines = [
        f"Hook: {r.get('hook_text', '')}",
        f"Archetype: {r.get('hook_archetype', '')}",
    ]
    for i, f in enumerate(r.get("frames", []), 1):
        lines.append(f"Frame {i} on_screen: {f.get('on_screen', '')}")
        lines.append(f"Frame {i} spoken:    {f.get('spoken', '')}")
    return "\n".join(lines)


def build(reel1: dict, reel2: dict | None, yt_short: dict, product: str) -> str:
    r1_summary = _summarise_reel(reel1)
    r2_summary = _summarise_reel(reel2) if reel2 else ""
    short_summary = "\n".join(
        f"Scene {s.get('scene')} ({s.get('type','').upper()}, {s.get('duration_s',5)}s): "
        f"on_screen='{s.get('on_screen','')}' | spoken='{s.get('spoken','')}'"
        for s in yt_short.get("scenes", [])
    )

    return f"""You are a senior video director and AI-video prompt engineer for Purity Beans — a premium pure instant coffee brand in India.

Write production-ready video prompts for EVERY frame/scene listed below.
Each ai_video_prompt must paste directly into Runway Gen-4, Pika 2.0, Kling 1.6, or Sora.
Each human_shot_list must be actionable by a videographer who has never seen this brief.

BRAND VISUAL IDENTITY:
- Palette: deep espresso black (#0D0805), warm gold (#C9933A), cream white (#F5ECD7)
- Textures: dark marble, aged wood, raw concrete, matte ceramic
- Light: single-source directional — amber key, deep shadows, no fill
- Product: Purity Beans jar — dark label, gold type, always sharp, never obscured
- People: Indian — real-looking, not model-polished. Candid energy.
- Never: stock-photo look, over-lit flat scenes, generic coffee stock

Return ONLY a valid JSON object. No markdown fences.

REEL 1 (morning):
{r1_summary}

REEL 2 (evening/night):
{r2_summary}

YOUTUBE SHORT (product: {product}):
{short_summary}

{{
  "video_prompts": {{
    "reel_1": {{
      "aspect_ratio": "9:16",
      "total_duration_s": 30,
      "color_grade": "Warm espresso — lifted blacks, amber mids, desaturated greens, skin tones preserved",
      "audio_direction": "Music mood + tempo + when beat drop lands relative to hook frame",
      "frames": [
        {{
          "frame_id": "reel_1_frame_1",
          "duration_s": 3,
          "on_screen_text": "Exact text for this frame",
          "ai_video_prompt": "Camera: [shot type]. Subject: [exact description]. Lighting: [source, direction, quality]. Motion: [specific movement]. Atmosphere: [colour temp, mood, texture]. Style: [reference]. End frame: [cut-ready last millisecond].",
          "human_shot_list": "Location. Lens (mm). Aperture. Lighting rig. Talent direction if any. Duration. Cut point.",
          "transition_to_next": "Cut type and bridging element"
        }}
      ],
      "thumbnail_frame": "Frame number + why it stops the scroll before play",
      "loop_edit_note": "Exact edit instruction so last frame cuts back to frame 1 seamlessly"
    }},
    "reel_2": {{
      "aspect_ratio": "9:16",
      "total_duration_s": 30,
      "color_grade": "Cooler, moodier — night palette: deep blue-blacks, warm amber accent, lower brightness",
      "audio_direction": "Night audio — instrument, tempo, emotional arc",
      "frames": [
        {{
          "frame_id": "reel_2_frame_1",
          "duration_s": 3,
          "on_screen_text": "Exact text for this frame",
          "ai_video_prompt": "Camera: [shot type]. Subject: [exact description]. Lighting: [night-specific — lamp glow, screen light, city ambient]. Motion: [specific]. Atmosphere: [cool-warm contrast, intimate, late-night]. Style: [reference]. End frame: [cut-ready].",
          "human_shot_list": "Location. Lens. Aperture. Lighting rig. Action. Duration. Cut point.",
          "transition_to_next": "Transition type and bridging element"
        }}
      ],
      "thumbnail_frame": "Best thumbnail frame + scroll-stop reason",
      "loop_edit_note": "Loop cut instruction"
    }},
    "yt_short": {{
      "aspect_ratio": "9:16",
      "total_duration_s": 27,
      "color_grade": "Scenes 1-2 desaturated + cold. Scene 3 warm gold reveal. Scenes 4-5 warm and clear.",
      "audio_direction": "Music bed genre + tempo + voiceover tone (Indian accent) + sound design cues",
      "scenes": [
        {{
          "scene_id": "yt_scene_1",
          "scene_type": "problem",
          "duration_s": 5,
          "on_screen_text": "Exact on-screen text",
          "spoken_voiceover": "Exact words said aloud",
          "ai_video_prompt": "Camera: [shot type]. Subject: [exact Indian scenario]. Lighting: [heavy, real]. Motion: [slow or static]. Atmosphere: [muted, gritty, relatable]. Style: [documentary]. End frame: [cut-ready].",
          "human_shot_list": "Location. Lens. Aperture. Lighting rig. Talent direction. Duration. Cut point.",
          "transition_to_next": "Cut type and bridging element"
        }}
      ],
      "edit_pacing": "Cut timing map — e.g. 1.5s cuts scenes 1-2, 3s hold scene 3 reveal, snap cuts 4-5",
      "cta_card_spec": "Final frame — background, logo position, URL style, hold duration"
    }}
  }}
}}

RULES:
1. ai_video_prompt must specify: camera + subject + lighting + motion + style + end_frame.
2. human_shot_list must be actionable by someone who has never seen this brief.
3. Generate ALL frames for all 3 pieces — do not skip any.
4. Colour grade must differ: reel_1 (warm morning), reel_2 (cool night), yt_short (cold → warm arc)."""
