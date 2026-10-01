import numpy as np
import soundfile as sf


def write_syllable_wav(path: str, seconds: float = 3.0, sr: int = 24000) -> str:
    """Write a small synthetic 'speech-like' wav: modulated 220 Hz carrier
    in 0.3 s syllables with silence gaps. Mono, int16, no network."""
    t = np.arange(int(sr * seconds)) / sr
    syllable = (np.sin(2 * np.pi * (t % 0.45) * 220.0 * (1 + (t % 0.45) * 8))
                * (0.6 + 0.4 * np.sin(2 * np.pi * t * 3)))
    envelope = (np.clip(np.sin(np.pi * (t % 0.45) / 0.45), 0, 1)
                * ((t % 0.45) < 0.30))
    audio = (syllable * envelope * 0.4 * 32767).astype(np.int16)
    sf.write(path, audio, sr, subtype="PCM_16")
    return path
