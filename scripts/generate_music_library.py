"""
Synthesizes 6 mood-tagged, royalty-free audio tracks for music_library/
using clean harmonic synthesis (sine/harmonics + envelopes) via numpy and wave.

Moods:
- lofi: Warm jazz chords (Dm7 - G7 - Cmaj7 - Am7) with soft vinyl warmth
- calm: Gentle acoustic piano / Rhodes harmonics with smooth envelope
- upbeat: Energetic coffeehouse acoustic groove
- ambient: Deep warm ambient coffee lounge pads
- cinematic: Deep swell and resolution cinematic harmony
- premium: Sophisticated luxury jazz neo-soul progression
"""
import os
import wave
import numpy as np

SAMPLE_RATE = 22050

def note_freq(midi_note: float) -> float:
    return 440.0 * (2.0 ** ((midi_note - 69.0) / 12.0))

def synth_chord(notes: list[int], duration: float, timbre: str = "rhodes") -> np.ndarray:
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    sig = np.zeros_like(t)
    for n in notes:
        f = note_freq(n)
        if timbre == "rhodes":
            # Fundamental + soft harmonics
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.4 * np.sin(2 * np.pi * 2 * f * t)
            h3 = 0.15 * np.sin(2 * np.pi * 3 * f * t)
            h4 = 0.05 * np.sin(2 * np.pi * 4 * f * t)
            tone = h1 + h2 + h3 + h4
            env = np.exp(-t * 1.8)
            sig += tone * env
        elif timbre == "pad":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.5 * np.sin(2 * np.pi * 2 * f * t + 0.5)
            h3 = 0.25 * np.sin(2 * np.pi * 3 * f * t + 1.0)
            tone = h1 + h2 + h3
            # Slow attack and decay
            attack = np.minimum(1.0, t / 0.8)
            decay = np.minimum(1.0, (duration - t) / 0.8)
            sig += tone * (attack * decay)
        elif timbre == "acoustic":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.6 * np.sin(2 * np.pi * 2 * f * t)
            h3 = 0.3 * np.sin(2 * np.pi * 3 * f * t)
            tone = h1 + h2 + h3
            env = np.exp(-t * 3.0)
            sig += tone * env
        elif timbre == "cinematic":
            h1 = np.sin(2 * np.pi * f * t)
            h2 = 0.6 * np.sin(2 * np.pi * 2 * f * t + 0.2)
            h3 = 0.3 * np.sin(2 * np.pi * 3 * f * t + 0.4)
            h0 = 0.8 * np.sin(2 * np.pi * (f / 2) * t) # sub
            tone = h1 + h2 + h3 + h0
            attack = np.minimum(1.0, t / 1.2)
            decay = np.minimum(1.0, (duration - t) / 1.0)
            sig += tone * (attack * decay)
    return sig

def export_wav(filename: str, audio: np.ndarray):
    # Normalize to -1.5 dB
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.85
    # Stereo
    left = audio
    right = audio
    stereo = np.empty((audio.size * 2,), dtype=np.int16)
    stereo[0::2] = (left * 32767).astype(np.int16)
    stereo[1::2] = (right * 32767).astype(np.int16)

    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(stereo.tobytes())
    print(f"Generated {filename} ({len(audio)/SAMPLE_RATE:.1f}s)")

def main():
    target_dir = os.path.join(os.path.dirname(__file__), "..", "music_library")
    os.makedirs(target_dir, exist_ok=True)

    # 1. Lofi Cafe (64 seconds seamless loop)
    lofi_prog = [
        ([50, 53, 57, 60, 64], 4.0),
        ([43, 50, 53, 59], 4.0),
        ([48, 52, 55, 59, 62], 4.0),
        ([45, 52, 55, 57, 60], 4.0),
    ] * 2
    lofi_audio = np.concatenate([synth_chord(ch, dur, "rhodes") for ch, dur in lofi_prog])
    noise = (np.random.rand(len(lofi_audio)) - 0.5) * 0.015
    export_wav(os.path.join(target_dir, "lofi_cafe.wav"), lofi_audio + noise)

    # 2. Calm Morning (64 seconds)
    calm_prog = [
        ([48, 55, 59, 62], 4.0),
        ([40, 52, 55, 59], 4.0),
        ([41, 53, 57, 60], 4.0),
        ([43, 50, 55, 60], 4.0),
    ] * 2
    calm_audio = np.concatenate([synth_chord(ch, dur, "rhodes") for ch, dur in calm_prog])
    export_wav(os.path.join(target_dir, "calm_morning.wav"), calm_audio)

    # 3. Upbeat Roast (64 seconds)
    upbeat_prog = [
        ([48, 55, 60, 64], 2.0),
        ([43, 50, 55, 59], 2.0),
        ([45, 52, 57, 60], 2.0),
        ([41, 48, 53, 57], 2.0),
        ([48, 55, 60, 64], 2.0),
        ([43, 50, 55, 59], 2.0),
        ([41, 48, 53, 57], 2.0),
        ([43, 50, 55, 59], 2.0),
    ] * 2
    upbeat_audio = np.concatenate([synth_chord(ch, dur, "acoustic") for ch, dur in upbeat_prog])
    export_wav(os.path.join(target_dir, "upbeat_roast.wav"), upbeat_audio)

    # 4. Ambient Lounge (64 seconds)
    ambient_prog = [
        ([36, 48, 55, 58, 62], 5.33),
        ([41, 48, 52, 57, 60], 5.33),
        ([38, 50, 53, 57, 62], 5.34),
    ] * 2
    ambient_audio = np.concatenate([synth_chord(ch, dur, "pad") for ch, dur in ambient_prog])
    export_wav(os.path.join(target_dir, "ambient_lounge.wav"), ambient_audio)

    # 5. Cinematic Origin (64 seconds)
    cinematic_prog = [
        ([33, 45, 52, 57, 60], 4.0),
        ([36, 48, 52, 55, 59], 4.0),
        ([38, 50, 53, 57, 62], 4.0),
        ([40, 52, 55, 59, 64], 4.0),
    ] * 2
    cinematic_audio = np.concatenate([synth_chord(ch, dur, "cinematic") for ch, dur in cinematic_prog])
    export_wav(os.path.join(target_dir, "cinematic_origin.wav"), cinematic_audio)

    # 6. Premium Jazz (64 seconds)
    premium_prog = [
        ([46, 53, 57, 60, 62], 4.0),
        ([43, 50, 53, 58, 63], 4.0),
        ([48, 55, 58, 62, 65], 4.0),
        ([41, 50, 53, 57, 62], 4.0),
    ] * 2
    premium_audio = np.concatenate([synth_chord(ch, dur, "rhodes") for ch, dur in premium_prog])
    export_wav(os.path.join(target_dir, "premium_jazz.wav"), premium_audio)

if __name__ == "__main__":
    main()
