# Task 4.3* — Realtime-factor measurement harness (optional)

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Give the operator a one-command way to measure the local backend's realtime factor (RTF = render wall time ÷ audio duration) on real hardware — the evidence for the CPU performance envelope — without touching CI gates or product code.

**Dependencies**: Task 2.2 (the local engine being measured). Optional task (`*`): deferrable, operator-run evidence.

**Boundary**: `shared tests` (a runnable harness script + one math unit test). No product code.

**Requirements**: 8.1

## Implementation Steps

### Step 1: Harness script
- [ ] Create a runnable script (direct `python` invocation from a platform folder) that: bootstraps the repo import path the same way the test conftest does; verifies the engine is installed (clear install hint + non-zero exit otherwise); redirects the reply cache to a fresh temp directory (a measurement must never read cache hits); loads the model once and reports the load time separately.
- [ ] Render a fixed set of six reply-length lines (roughly today's reply sizes — short confirmations, a status line, a timer line, one line carrying a `[chuckle]` tag) via the normal seam, and for each line print: render ms (from the seam's own return), audio seconds (frames ÷ rate via soundfile), and the ratio.
- [ ] Print a summary block (mean and max RTF, PASS/FAIL against the envelope target RTF < 1.0) and exit 0 regardless of the verdict — it is evidence, not a gate.
- **Observable**: running the harness on the dev box prints the per-line table and summary with no failures; every rendered file lands in the temp cache, leaving the real cache untouched.

### Step 2: Math helper + unit test
- [ ] Keep the ratio computation in a tiny pure function (render ms, audio seconds → float ratio) so the arithmetic is unit-testable without the engine.
- [ ] Unit test: known inputs → exact ratio; zero/negative render ms handled; the summary verdict helper (ratio list → mean, max, pass flag).
- **Observable**: math unit passes offline; CI can assert the harness's math without any engine install.

### Step 3: Operator runbook
- [ ] Document the invocation (command per platform folder) and what to record (machine CPU, Python version, engine variant, mean/max RTF) in the harness header comment.
- **Observable**: an operator can run the harness cold by following only the header comment.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tests/measure_rtf.py` | Create | The runnable RTF harness |
| `shared/tests/test_tts_local.py` | Modify | RTF math unit test |
| `alternatives/doc/design.md` | Modify | File-plan sync (harness script line) — applied at approval |

### File: `shared/tests/measure_rtf.py`

**Current Code**: none. (Seam under measurement — the render contract from Task 2.1/2.2: `tts.render(text) -> (path, render_ms, cached)`.)

**Expected Code**:

```python
"""RTF harness: measure the local TTS backend's realtime factor on this machine.

Run from a platform folder:   python ../shared/tests/measure_rtf.py
Records: machine CPU, Python version, engine variant, mean/max RTF.
Requires the optional local engine (see shared/requirements-tts-local.txt).
The first run may download model weights; measurements start after the load.
"""
import os
import sys
import tempfile
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
    mean = sum(ratios) / len(ratios)
    return {"mean": mean, "max": max(ratios), "pass": max(ratios) < RTF_TARGET}


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
    t0 = __import__("time").time()
    first_path, _, _ = tts.render(LINES[0])                     # loads the model
    load_s = __import__("time").time() - t0
    rows = []
    for line in LINES:
        path, ms, cached = tts.render(line)
        assert not cached, f"unexpected cache hit while measuring: {line!r}"
        data, sr = sf.read(path)
        rows.append((line, ms, len(data) / sr))
    print(f"\nengine load: {load_s:.1f}s   cache: {config.CACHE_DIR}")
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
```

### File: `shared/tests/test_tts_local.py`

**Current Code** (end of file after Task 2.2):

```python
@pytest.mark.slow
@pytest.mark.network
def test_real_model_render(state_isolation):
    pytest.importorskip("chatterbox")
    path, ms, cached = tts.render("Jev here, all systems nominal.")
    import soundfile as sf
    data, sr = sf.read(path)
    assert sr == 24000 and len(data) > sr
```

**Expected Code After Implementation** (appended):

```python
def test_rtf_math():
    from measure_rtf import rtf_ratio, verdict
    assert rtf_ratio(500, 1.0) == 0.5
    assert verdict([0.5, 1.5]) == {"mean": 1.0, "max": 1.5, "pass": False}
    assert verdict([0.9, 0.8])["pass"] is True
```

(Import path for the harness module settles at implementation — same repo-root bootstrap as conftest, or a conftest-registered helper; the test must stay offline.)

### File: `alternatives/doc/design.md`

**Current Code** (File Structure Plan, tests block after Task 4.2's sync):

```
    ├── test_tts_integration.py   # backend + warm-cache integration (task 4.1)
    └── test_persona_turn.py      # turn-level persona flows (task 4.2)
```

**Expected Code After Implementation** (applied at this task's approval):

```
    ├── test_tts_integration.py   # backend + warm-cache integration (task 4.1)
    ├── test_persona_turn.py      # turn-level persona flows (task 4.2)
    └── measure_rtf.py            # operator RTF harness, not a CI gate (task 4.3)
```

## Testing Approach

### Unit Tests (offline)
1. Ratio math: known ms/seconds → exact ratio; verdict mean/max/pass
   - Input: fixed numbers
   - Expected: exact values above

### Manual Verification
1. `python ../shared/tests/measure_rtf.py` from a platform folder with the engine installed → table + summary printed, temp cache populated, real cache untouched
2. Without the engine installed → clear hint, exit code 1

## Acceptance Criteria

- [ ] Harness runs on a GPU-less machine, measures through the product seam only (no internals), and never reads cache hits while measuring
- [ ] Per-line table (render ms, audio s, RTF) + mean/max summary printed; exit code independent of the verdict
- [ ] Model load time reported separately from per-line RTF
- [ ] Ratio math unit-tested offline (CI can verify the harness without the engine)
- [ ] All requirements covered: 8.1

## Notes

- Optional-task status: deferrable without blocking the feature; the envelope (8.1) is operator-verified evidence, and CI asserts only the math.
- First run may download model weights (engine installation); measurements start after the load — the load time is reported separately so it never pollutes per-line RTF.
- The harness deliberately measures through `tts.render` (the real seam, including tag mapping) rather than calling the engine directly — numbers reflect what users experience.
- Line set mirrors real reply sizes; extend it only with the same character budget so numbers stay comparable across runs/machines.
- Design file-plan sync (the `measure_rtf.py` line) accompanies this task's approval.
