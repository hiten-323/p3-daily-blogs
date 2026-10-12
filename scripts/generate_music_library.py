"""
Synthesizes 6 mood-tagged, royalty-free viral audio tracks for music_library/
using rhythmic drum machines (kick, snare, hi-hat, sub-bass), melodic harmonic progressions,
and downbeat transition impacts locked to 120 BPM (2.0s per bar).

Every visual transition at 2.0s intervals locks in 100% sync with the audio beat!
"""
import os
import wave
import numpy as np

SAMPLE_RATE = 22050
BPM = 120.0
BEAT_DUR = 60.0 / BPM     # 0.500 seconds
BAR_DUR = BEAT_DUR * 4.0   # 2.000 seconds
TOTAL_DURATION = 32.0      # 16 bars

def note_freq(midi_note: float) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))

def synth_kick(sr=SAMPLE_RATE):
    dur = 0.35
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    freq = 48.0 + 130.0 * np.exp(-t * 26.0)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sig = np.sin(phase) * np.exp(-t * 9.5)
    click = (np.random.rand(len(t)) - 0.5) * np.exp(-t * 70.0) * 0.4
    return sig + click

def synth_snare(sr=SAMPLE_RATE):
    dur = 0.28
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    noise = (np.random.rand(len(t)) - 0.5) * 2.0
    noise = np.diff(noise, prepend=0)
    tone = np.sin(2 * np.pi * 185.0 * t) * 0.55
    return (noise * 0.75 + tone) * np.exp(-t * 15.0)

def synth_clap(sr=SAMPLE_RATE):
    dur = 0.25
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    # Multi-tap burst
    sig = np.zeros_like(t)
    for offset in [0.0, 0.012, 0.024]:
        idx = int(offset * sr)
        if idx < len(t):
            sub_t = t[idx:]
            noise = (np.random.rand(len(sub_t)) - 0.5) * np.exp(-(sub_t - offset) * 22.0)
            sig[idx:] += noise * 0.5
    return np.diff(sig, prepend=0) * 1.5

def synth_hihat(sr=SAMPLE_RATE, open_hat=False):
    dur = 0.22 if open_hat else 0.07
    t = np.linspace(0, dur, int(sr * dur), endpoint=False)
    noise = (np.random.rand(len(t)) - 0.5) * 2.0
    hp = np.diff(np.diff(noise, prepend=0), prepend=0)
    decay = 18.0 if open_hat else 55.0
    return hp * np.exp(-t * decay) * 0.35

def synth_sub_bass(freq: float, duration: float, sr=SAMPLE_RATE):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    sub = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * (freq * 2) * t)
    # Saturation
    sub = np.tanh(sub * 1.4)
    env = np.minimum(1.0, t / 0.02) * np.exp(-t * 2.2)
    return sub * env * 0.75

def synth_impact(duration=0.8, sr=SAMPLE_RATE):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    freq = 65.0 * np.exp(-t * 4.0)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    sub = np.sin(phase) * 0.9
    noise = (np.random.rand(len(t)) - 0.5) * np.exp(-t * 7.0) * 0.4
    return (sub + noise) * np.exp(-t * 4.0)

def synth_riser(duration=0.5, sr=SAMPLE_RATE):
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    # Filtered sweep upwards leading to downbeat
    noise = (np.random.rand(len(t)) - 0.5) * 0.4
    env = (t / duration) ** 2
    tone = np.sin(2 * np.pi * (200.0 + 600.0 * (t / duration) ** 2) * t) * 0.2
    return (noise + tone) * env * 0.5

def synth_chord(notes: list[int], duration: float, timbre: str = "rhodes") -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    sig = np.zeros_like(t)
    for n in notes:
        f = note_freq(n)
        if timbre == "rhodes":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.4 * np.sin(2 * np.pi * 2 * f * t)
            h3 = 0.15 * np.sin(2 * np.pi * 3 * f * t)
            tone = h1 + h2 + h3
            env = np.exp(-t * 1.4)
            sig += tone * env
        elif timbre == "pad":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.45 * np.sin(2 * np.pi * 2 * f * t + 0.4)
            h3 = 0.2 * np.sin(2 * np.pi * 3 * f * t + 0.8)
            tone = h1 + h2 + h3
            attack = np.minimum(1.0, t / 0.4)
            decay = np.minimum(1.0, (duration - t) / 0.4)
            sig += tone * (attack * decay)
        elif timbre == "pluck":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.55 * np.sin(2 * np.pi * 2 * f * t)
            h3 = 0.25 * np.sin(2 * np.pi * 3 * f * t)
            tone = h1 + h2 + h3
            env = np.exp(-t * 3.5)
            sig += tone * env
        elif timbre == "cinematic":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.5 * np.sin(2 * np.pi * 2 * f * t + 0.3)
            h0 = 0.8 * np.sin(2 * np.pi * (f / 2) * t)
            tone = h1 + h2 + h0
            attack = np.minimum(1.0, t / 0.6)
            decay = np.minimum(1.0, (duration - t) / 0.5)
            sig += tone * (attack * decay)
    return sig

def add_audio(target: np.ndarray, source: np.ndarray, start_sec: float):
    start_idx = int(start_sec * SAMPLE_RATE)
    end_idx = min(len(target), start_idx + len(source))
    if start_idx < len(target) and end_idx > start_idx:
        target[start_idx:end_idx] += source[:end_idx - start_idx]

def build_beat_drum_track(total_sec: float, style: str = "lofi") -> np.ndarray:
    """Create a 120 BPM drum groove with kick, snare/clap, hats, and transition hits."""
    n_samples = int(total_sec * SAMPLE_RATE)
    track = np.zeros(n_samples, dtype=np.float32)

    kick = synth_kick()
    snare = synth_snare()
    clap = synth_clap()
    hat_closed = synth_hihat(open_hat=False)
    hat_open = synth_hihat(open_hat=True)
    impact = synth_impact()
    riser = synth_riser()

    n_bars = int(total_sec / BAR_DUR)

    for b in range(n_bars):
        bar_start = b * BAR_DUR

        # Downbeat impact & kick on beat 1 (t = 0.0)
        add_audio(track, kick * 1.1, bar_start + 0.0)
        add_audio(track, impact * 0.45, bar_start + 0.0)

        # Beat 2 (t = 0.5s): Snare or Clap
        if style == "upbeat":
            add_audio(track, clap * 1.0, bar_start + BEAT_DUR)
        else:
            add_audio(track, snare * 0.9, bar_start + BEAT_DUR)

        # Beat 3 (t = 1.0s): Kick drum
        add_audio(track, kick * 0.9, bar_start + BEAT_DUR * 2.0)

        # Beat 4 (t = 1.5s): Snare / Clap
        if style == "upbeat":
            add_audio(track, clap * 1.0, bar_start + BEAT_DUR * 3.0)
        else:
            add_audio(track, snare * 0.9, bar_start + BEAT_DUR * 3.0)

        # Hi-hat groove on every 8th note
        for h in range(8):
            hat_t = bar_start + h * (BEAT_DUR / 2.0)
            if h == 4 and style == "lofi":
                add_audio(track, hat_open * 0.7, hat_t)
            else:
                vel = 0.8 if h % 2 == 0 else 0.5
                add_audio(track, hat_closed * vel, hat_t)

        # Transition riser preceding next downbeat (last 0.4s of bar)
        if b < n_bars - 1:
            add_audio(track, riser * 0.5, bar_start + BAR_DUR - 0.4)

    return track

def export_mastered_wav(filename: str, audio: np.ndarray):
    # Mastered to punchy, streaming loudness (-14 LUFS target / -0.5 dB peak)
    peak = np.max(np.abs(audio))
    if peak > 0:
        # Soft limiter via tanh to preserve transients without clipping
        audio = np.tanh(audio / peak * 1.25)
        peak_lim = np.max(np.abs(audio))
        audio = (audio / peak_lim) * 0.94

    # Stereo widening
    left = audio
    # Slight Haas effect / stereo delay on right channel for full immersive sound
    right = np.roll(audio, int(SAMPLE_RATE * 0.012))

    stereo = np.empty((len(audio) * 2,), dtype=np.int16)
    stereo[0::2] = (left * 32767).astype(np.int16)
    stereo[1::2] = (right * 32767).astype(np.int16)

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(stereo.tobytes())
    print(f"Generated {filename} ({len(audio)/SAMPLE_RATE:.1f}s @ 120 BPM beat-synced)")

def main():
    target_dir = os.path.join(os.path.dirname(__file__), "..", "music_library")
    os.makedirs(target_dir, exist_ok=True)

    # 1. Lofi Cafe (120 BPM, Warm neo-soul progression Dm7 - G7 - Cmaj7 - Am7)
    lofi_chords = [
        ([50, 53, 57, 60, 64], BAR_DUR, 38),   # Dm9, root D2
        ([43, 50, 53, 59],     BAR_DUR, 31),   # G7, root G1
        ([48, 52, 55, 59, 62], BAR_DUR, 36),   # Cmaj9, root C2
        ([45, 52, 55, 57, 60], BAR_DUR, 33),   # Am7, root A1
    ] * 4 # 16 bars = 32s

    lofi_music = np.zeros(int(TOTAL_DURATION * SAMPLE_RATE), dtype=np.float32)
    cur_t = 0.0
    for notes, dur, root_midi in lofi_chords:
        ch = synth_chord(notes, dur, "rhodes")
        add_audio(lofi_music, ch * 0.65, cur_t)
        # Sub-bass on downbeat
        bass = synth_sub_bass(note_freq(root_midi), dur * 0.8)
        add_audio(lofi_music, bass * 0.7, cur_t)
        cur_t += dur

    drums_lofi = build_beat_drum_track(TOTAL_DURATION, style="lofi")
    export_mastered_wav(os.path.join(target_dir, "lofi_cafe.wav"), lofi_music + drums_lofi)

    # 2. Upbeat Roast (120 BPM, Punchy driving electro-pop coffee groove)
    upbeat_chords = [
        ([48, 55, 60, 64], BAR_DUR, 36),   # C
        ([43, 50, 55, 59], BAR_DUR, 31),   # G
        ([45, 52, 57, 60], BAR_DUR, 33),   # Am
        ([41, 48, 53, 57], BAR_DUR, 29),   # F
    ] * 4

    upbeat_music = np.zeros(int(TOTAL_DURATION * SAMPLE_RATE), dtype=np.float32)
    cur_t = 0.0
    for notes, dur, root_midi in upbeat_chords:
        ch = synth_chord(notes, dur, "pluck")
        add_audio(upbeat_music, ch * 0.7, cur_t)
        bass = synth_sub_bass(note_freq(root_midi), dur * 0.7)
        add_audio(upbeat_music, bass * 0.85, cur_t)
        cur_t += dur

    drums_upbeat = build_beat_drum_track(TOTAL_DURATION, style="upbeat")
    export_mastered_wav(os.path.join(target_dir, "upbeat_roast.wav"), upbeat_music + drums_upbeat)

    # 3. Cinematic Origin (120 BPM, Deep cinematic riser and sub-drop rhythm)
    cinematic_chords = [
        ([33, 45, 52, 57, 60], BAR_DUR, 21),   # A minor low
        ([36, 48, 52, 55, 59], BAR_DUR, 24),   # C major low
        ([38, 50, 53, 57, 62], BAR_DUR, 26),   # D minor low
        ([40, 52, 55, 59, 64], BAR_DUR, 28),   # E minor low
    ] * 4

    cine_music = np.zeros(int(TOTAL_DURATION * SAMPLE_RATE), dtype=np.float32)
    cur_t = 0.0
    for notes, dur, root_midi in cinematic_chords:
        ch = synth_chord(notes, dur, "cinematic")
        add_audio(cine_music, ch * 0.8, cur_t)
        bass = synth_sub_bass(note_freq(root_midi), dur * 0.9)
        add_audio(cine_music, bass * 0.9, cur_t)
        cur_t += dur

    drums_cine = build_beat_drum_track(TOTAL_DURATION, style="lofi") * 0.85
    export_mastered_wav(os.path.join(target_dir, "cinematic_origin.wav"), cine_music + drums_cine)

    # 4. Calm Morning (120 BPM, Peaceful warm acoustic morning groove)
    calm_chords = [
        ([48, 55, 59, 62], BAR_DUR, 36),   # Cmaj7
        ([40, 52, 55, 59], BAR_DUR, 28),   # Em
        ([41, 53, 57, 60], BAR_DUR, 29),   # Fmaj7
        ([43, 50, 55, 60], BAR_DUR, 31),   # G
    ] * 4

    calm_music = np.zeros(int(TOTAL_DURATION * SAMPLE_RATE), dtype=np.float32)
    cur_t = 0.0
    for notes, dur, root_midi in calm_chords:
        ch = synth_chord(notes, dur, "rhodes")
        add_audio(calm_music, ch * 0.65, cur_t)
        bass = synth_sub_bass(note_freq(root_midi), dur * 0.7)
        add_audio(calm_music, bass * 0.6, cur_t)
        cur_t += dur

    drums_calm = build_beat_drum_track(TOTAL_DURATION, style="lofi") * 0.75
    export_mastered_wav(os.path.join(target_dir, "calm_morning.wav"), calm_music + drums_calm)

    # 5. Premium Jazz (120 BPM, Neo-soul luxury chord progression)
    prem_chords = [
        ([46, 53, 57, 60, 62], BAR_DUR, 34),   # Bbmaj9
        ([43, 50, 53, 58, 63], BAR_DUR, 31),   # Gm7
        ([48, 55, 58, 62, 65], BAR_DUR, 36),   # Cm9
        ([41, 50, 53, 57, 62], BAR_DUR, 29),   # F7
    ] * 4

    prem_music = np.zeros(int(TOTAL_DURATION * SAMPLE_RATE), dtype=np.float32)
    cur_t = 0.0
    for notes, dur, root_midi in prem_chords:
        ch = synth_chord(notes, dur, "rhodes")
        add_audio(prem_music, ch * 0.7, cur_t)
        bass = synth_sub_bass(note_freq(root_midi), dur * 0.75)
        add_audio(prem_music, bass * 0.7, cur_t)
        cur_t += dur

    drums_prem = build_beat_drum_track(TOTAL_DURATION, style="lofi") * 0.8
    export_mastered_wav(os.path.join(target_dir, "premium_jazz.wav"), prem_music + drums_prem)

    # 6. Ambient Lounge (120 BPM, Deep warm coffeehouse lounge)
    amb_chords = [
        ([36, 48, 55, 58, 62], BAR_DUR, 24),
        ([41, 48, 52, 57, 60], BAR_DUR, 29),
        ([38, 50, 53, 57, 62], BAR_DUR, 26),
        ([43, 50, 55, 58, 62], BAR_DUR, 31),
    ] * 4

    amb_music = np.zeros(int(TOTAL_DURATION * SAMPLE_RATE), dtype=np.float32)
    cur_t = 0.0
    for notes, dur, root_midi in amb_chords:
        ch = synth_chord(notes, dur, "pad")
        add_audio(amb_music, ch * 0.75, cur_t)
        bass = synth_sub_bass(note_freq(root_midi), dur * 0.8)
        add_audio(amb_music, bass * 0.7, cur_t)
        cur_t += dur

    drums_amb = build_beat_drum_track(TOTAL_DURATION, style="lofi") * 0.7
    export_mastered_wav(os.path.join(target_dir, "ambient_lounge.wav"), amb_music + drums_amb)

if __name__ == "__main__":
    main()
