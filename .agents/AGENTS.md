# Purity Beans Creative Asset Generation Policy

## Non-negotiable product integrity
The exact real Purity Beans jar must be used as an immutable asset. Never redraw or regenerate the jar, label, logo, typography, colors, cap, shape, proportions, glass, neck label, or packaging. Never invent certifications, awards, claims, ingredients, or packaging. If no matching verified product image is available, hold the asset rather than inventing one.

## Art direction and photorealism
Create premium editorial lifestyle photography, not generic AI stock art. Each brief must specify:
- A believable location and human context where useful (real kitchen, office pantry, café, breakfast table).
- One clear subject and visual story, with intentional foreground/background separation.
- A plausible camera angle, lens/depth of field, natural or motivated lighting, correct contact shadow and reflections.
- Realistic hands, skin, cups, liquid, steam and coffee texture; avoid impossible anatomy, floating objects, plastic-looking surfaces, warped geometry and contradictory shadows.
- A different composition for each slide/frame. Do not repeat the same centered jar-on-gradient layout across a carousel.
- Avoid excessive props, fake UI, fake labels, decorative text generated inside the image, and generic luxury clichés.
- Composite the authentic product photo into the generated scene; do not ask a text-to-image model to recreate package artwork.

## Carousel design standard
A carousel must have one explicit audience problem, one hook/cover, a logical sequence of useful information, and a clear final action. Each slide should do one job. Vary framing and image/text balance while maintaining a consistent brand system. Use legible mobile typography, generous margins, deliberate hierarchy, and restrained color. Keep visible copy short; no template labels such as "Slide 1", "Headline" or "Body text". Render then inspect every slide at mobile size; regenerate or hold any weak, repetitive, clipped, low-contrast or visibly artificial slide. One SKU per hero creative unless a multi-SKU composition is explicitly requested.

## Reels and audio
Reels need a first-second hook, a shot-by-shot motion plan, a strong payoff, and a clean loop or intentional ending. Audio metadata must distinguish a creative suggestion from a verified track. Never claim a sound is trending unless it was returned by a live authorized catalogue query. Verify account/region availability and commercial usage rights. If no licensed audio is actually attached or a native selection is required, mark the Reel as requiring manual/native audio and do not silently treat a suggestion as an attached soundtrack.

## Release gate
A successful image-generation API response is not a visual QA pass. Validate the actual rendered assets and product provenance. Require a visual QA result for carousel/story/reel assets; fail closed on missing product references, malformed output, broken text, implausible composition, or unverified audio when audio is required. Regenerate once with a more specific art direction; if it still fails, hold it and surface the reason. Never lower the quality threshold just to fill a posting slot.

## Reporting
For each generated asset, record product asset used, scene/art direction, aspect ratio, image provider, QA status/issues, audio track ID/name/source when available, rights/availability verification, and final publish mode. Do not log tokens or credentials.
