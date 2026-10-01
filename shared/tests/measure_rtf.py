"""RTF harness: measure the local TTS backend's realtime factor on this machine.

Run from a platform folder:   python ../shared/tests/measure_rtf.py
Records: machine CPU, Python version, engine variant, mean/max RTF.
Requires the optional local engine (see shared/requirements-tts-local.txt).
The first run may download model weights; measurements start after the load.
"""
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

LINES = [
    "Timer set for five minutes.",
    "[chuckle] Good one. I filed that away.",
    "Spotify is open and playing.",
    "Volume set to medium.",
    "Dark mode is on. It is easier on the eyes at night.",
    "Running on battery, about three hours left, processor is mostly idle.",
]
RTF_TARGET = 1.0


def rtf_ratio(render_ms: float, audio_s: float) -> float:
    return render_ms / 1000.0 / audio_s


def verdict(ratios):
    return {"mean": sum(ratios) / len(ratios), "max": max(ratios), "pass": max(ratios) < RTF_TARGET}


def main() -> int:
    try:
        import chatterbox  # noqa: F401
    except ImportError:
        print("local engine not installed; see shared/requirements-tts-local.txt")
        return 1
    import soundfile as sf
    from shared import config, tts

    config.TTS_BACKEND = "chatterbox"
    config.CACHE_DIR = tempfile.mkdtemp(prefix="heyjev-rtf-")   # fresh cache: no hits
    t0 = time.time()
    tts.render("Loading the voice engine.")                     # loads the model
    load_s = time.time() - t0
    rows = []
    for line in LINES:
        path, ms, cached = tts.render(line)
        assert not cached, f"unexpected cache hit while measuring: {line!r}"
        data, sr = sf.read(path)
        rows.append((line, ms, len(data) / sr))
    print(f"\nengine load: {load_s:.1f}s   cache: {config.CACHE_DIR}")
    print(f"machine: {platform.processor()}  python {platform.python_version()}  "
          f"variant: {config.TTS_CHATTERBOX_VARIANT}")
    print(f"{'line':<40} {'render_ms':>9} {'audio_s':>8} {'RTF':>6}")
    ratios = []
    for line, ms, audio_s in rows:
        r = rtf_ratio(ms, audio_s)
        ratios.append(r)
        print(f"{line[:40]:<40} {ms:>9} {audio_s:>8.2f} {r:>6.2f}")
    v = verdict(ratios)
    print(f"\nmean RTF {v['mean']:.2f}   max RTF {v['max']:.2f}   "
          f"target < {RTF_TARGET}: {'PASS' if v['pass'] else 'FAIL'} (evidence only, not a gate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
