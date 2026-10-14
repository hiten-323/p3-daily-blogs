# Music Library — drop royalty-free tracks here

The Audio Director auto-embeds a mood-matched track into the reel VIDEOS the
engine renders (so they're not silent). Instagram/Facebook won't let any API
attach their in-app trending audio — for that, the engine gives you a one-tap
recommendation to apply in-app when you post hero content by hand.

## What to add
Drop a few **royalty-free, commercial-safe** tracks here (mp3/m4a/wav).
Free, safe sources:
- YouTube Audio Library (studio.youtube.com → Audio Library) — free for commercial use
- Pixabay Music (pixabay.com/music) — free, no attribution
- Uppbeat, Chosic — free tiers

## Naming (so the engine matches mood to content)
Include the mood in the filename. The engine picks by these mood tags:
`lofi`, `calm`, `upbeat`, `ambient`, `cinematic`, `premium`

Examples:
- `lofi_cafe_1.mp3`      → coffee aesthetic, lifestyle
- `calm_piano.mp3`       → morning routine, wellness
- `upbeat_1.mp3`         → productivity, behind-the-scenes
- `cinematic_founder.mp3`→ founder stories, motivation
- `premium_jazz.mp3`     → product launches, luxury

3-6 tracks is plenty to start. No tracks = reels post silent (still valid).
Files here are gitignored by default if large — commit small ones so CI can use them.

## Licences
See [LICENSES.md](LICENSES.md). Every track in this folder is an original
in-repo synthesis under CC0; third-party music is not accepted without a
licence row in that file.
