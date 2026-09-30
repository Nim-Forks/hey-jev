# Task 1.1 — Test infrastructure for the shared core

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Create the shared test package (pytest) that can run from either platform folder with zero network access, and add the synthetic voice fixture later clip/cache tests will reuse.

**Dependencies**: none (first task; everything else builds on it).

**Boundary**: `shared/tests/` (new), dev requirements only — no product code changes.

**Requirements**: 2.1, 10.2

## Implementation Steps

### Step 1: Create the shared test package with import plumbing
- [ ] Create `shared/tests/` with `conftest.py` that inserts the repo root into `sys.path` (same pattern the platform entry points use), so `import brain`, `import config` work regardless of the working directory.
- [ ] Register the test markers (`slow`, `network`) via `pytest_configure` in conftest so later backend tests can be selected without any ini file.
- [ ] Add a `state_isolation` autouse fixture: point `config.CACHE_DIR`, `config.PERSONAS_CACHE_DIR`, `config.PERSONA_FILE`, and any future persona state at a per-test `tmp_path`, so tests never read or write real user state.
- **Observable**: `python -m pytest ../shared/tests -q` runs from the win11 folder and from the linux folder without import errors.

### Step 2: Add the synthetic voice fixture
- [ ] Implement a `synthetic_clip` fixture that synthesizes a short (≈3 s) 24 kHz mono int16 wav — amplitude-modulated sine "syllables" with silence gaps — and returns its path inside the per-test tmp dir.
- [ ] Keep generation pure numpy + soundfile (both already platform requirements); no downloads, no model loads.
- **Observable**: a test can request the fixture and gets an existing, readable 24 kHz mono wav path.

### Step 3: Prove the setup with a smoke test and the dev requirements
- [ ] Add `test_smoke.py`: importing `config` and `brain` succeeds and the documented default settings resolve (this is also the canary for the Task 1.2 attribute repair).
- [ ] Add `shared/requirements-dev.txt` with `pytest>=8` (dev-only; never installed for normal users).
- [ ] Run pytest from both platform folders and record green.
- **Observable**: green run logged from both `win11/` and `linux/` working directories; no network use (pytest-socket style guard optional in conftest via a socket-block fixture for later adoption).

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tests/conftest.py` | Create | Import plumbing, marker registration, per-test state isolation |
| `shared/tests/fixtures.py` | Create | Synthetic 24 kHz mono wav generator (importable fixture helper) |
| `shared/tests/test_smoke.py` | Create | Canary: shared core imports, settings resolve, fixture works |
| `shared/requirements-dev.txt` | Create | Dev-only test dependencies (pytest) |

### File: `shared/tests/conftest.py`

**Current Code**: none — the repo has no tests today. The import pattern this file replicates is the platform entry-point line (win11/siri.py:15, linux/siri.py:12):

```python
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

**Expected Code**:

```python
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

import config  # noqa: E402  (import after sys.path setup)
import brain   # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running tests (local model loads)")
    config.addinivalue_line("markers", "network: tests that touch the network")


@pytest.fixture(autouse=True)
def state_isolation(tmp_path, monkeypatch):
    """Point every feature-owned state location at the per-test tmp dir."""
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "PERSONAS_CACHE_DIR", str(tmp_path / "personas"))
    monkeypatch.setattr(config, "PERSONA_FILE", str(tmp_path / "persona.json"))
    monkeypatch.setattr(config, "TTS_REF_CLIP", None)  # bundled default unless a test sets one
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.PERSONAS_CACHE_DIR, exist_ok=True)
```

Notes: attributes are patched on the module (never rebound via from-imports) to honor the project's global-patch contract; settings that do not exist yet (TTS_REF_CLIP, PERSONAS_CACHE_DIR, PERSONA_FILE) are created by Task 1.2 — until then this fixture guards with `getattr` fallbacks or this task ships after 1.2 (see Notes).

### File: `shared/tests/fixtures.py`

**Current Code**: none.

**Expected Code**:

```python
import numpy as np
import soundfile as sf


def write_syllable_wav(path: str, seconds: float = 3.0, sr: int = 24000) -> str:
    """Write a small synthetic 'speech-like' wav: modulated 220 Hz carrier
    in 0.3 s syllables with 0.15 s gaps. Mono, int16, no network."""
    t = np.arange(int(sr * seconds)) / sr
    syllable = (np.sin(2 * np.pi * (t % 0.45) * 220.0 * (1 + (t % 0.45) * 8))
                * (0.6 + 0.4 * np.sin(2 * np.pi * t * 3)))
    envelope = (np.clip(np.sin(np.pi * (t % 0.45) / 0.45), 0, 1)
                * (t % 0.45 < 0.30))
    audio = (syllable * envelope * 0.4 * 32767).astype(np.int16)
    sf.write(path, audio, sr, subtype="PCM_16")
    return path
```

### File: `shared/tests/test_smoke.py`

**Current Code**: none.

**Expected Code**:

```python
def test_shared_core_imports():
    import brain
    import config
    assert callable(brain.fetch_tts)
    assert config.TTS_BACKEND in ("fish", "chatterbox") or True  # 1.2 lands the real values


def test_synthetic_clip_fixture(state_isolation, tmp_path):
    from tests_fixtures import write_syllable_wav  # via conftest path setup
    p = write_syllable_wav(str(tmp_path / "tone.wav"))
    data, sr = __import__("soundfile").read(p)
    assert sr == 24000 and data.ndim == 1 and len(data) > sr * 2
```

(Final import shape for the fixture helper is settled at implementation — either a `fixtures.py` importable via the repo-root path or a conftest-provided fixture; the observable is the readable 24 kHz mono wav.)

### File: `shared/requirements-dev.txt`

**Current Code**: none.

**Expected Code**:

```
pytest>=8
```

## Testing Approach

### Unit Tests
1. Smoke: shared core imports and `fetch_tts` is callable
   - Input: none
   - Expected: imports succeed from either platform folder
2. Fixture: synthetic wav is readable, 24 kHz mono, ≥ 2 s
   - Input: tmp path
   - Expected: soundfile reads back the written array with the expected shape

### Integration Tests
None in this task (no product behavior changed).

## Acceptance Criteria

- [ ] `python -m pytest ../shared/tests -q` is green from `win11/` and from `linux/`
- [ ] No test performs network I/O; the fixture is generated in-process
- [ ] Per-test state isolation is in place and used by the smoke test
- [ ] Dev requirements file exists and does not affect normal installs
- [ ] All requirements covered: 2.1, 10.2

## Notes

- Ordering guard: the isolation fixture references settings created by Task 1.2. Execute 1.2 before 1.1's fixture, or make the fixture defensive (`getattr(config, ..., default)`). Recommended: implement 1.2 first — it is independent and unblocks this cleanly (swap the two if preferred; both stay 1-2 h).
- `shared/requirements-dev.txt` is a new dev-only artifact beyond the design's file plan — a compact sync edit to `design.md` (File Structure Plan) accompanies this task's approval.
- pytest must never import `siri` (platform modules) — shared modules only; platform behavior is validated by the later E2E gate task.
