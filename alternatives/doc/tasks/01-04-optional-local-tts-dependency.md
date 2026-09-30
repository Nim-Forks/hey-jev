# Task 1.4 — Add the optional local-TTS dependency set

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Provide the optional, clearly separated dependency set for the local Chatterbox engine so that normal installs stay byte-identical to today, and record the interpreter/pin constraints discovered from the vendor's own dependency metadata.

**Dependencies**: none (independent of 1.1–1.3; pure packaging).

**Boundary**: shared optional requirements file + pointer comments in the two platform requirements files. No code, no imports.

**Requirements**: 1.2, 8.1

## Implementation Steps

### Step 1: Create the optional requirements file
- [ ] Create `shared/requirements-tts-local.txt` containing the local engine pin (`chatterbox-tts>=0.1.7` — latest verified on PyPI today, MIT, Python ≥3.10) plus a reaffirming `soundfile>=0.13` (mp3 read needs libsndfile ≥ 1.2, bundled by soundfile ≥ 0.13).
- [ ] Header comments document the three operational facts:
  1. Install order: the vendor pins exact torch/torchaudio versions, and PyPI's same-version CUDA wheel outranks the CPU build, so torch/torchaudio must be pre-installed from the PyTorch CPU index first, then this file.
  2. Interpreter floor: on Python < 3.13 the vendor pins `numpy<2.0`, which conflicts with the platforms' `numpy>=2.0`; the local backend therefore requires a Python ≥ 3.13 venv (≥ 3.14 switches the vendor pins to torch ≥ 2.9).
  3. Install command: `pip install -r requirements.txt -r ../shared/requirements-tts-local.txt` from the platform folder.
- **Observable**: the file exists with the pin and the three documented constraints.

### Step 2: Point both platform requirement files at it
- [ ] Append a short comment block to `win11/requirements.txt` and `linux/requirements.txt` referencing the optional file and the install command — comments only, no dependency changes.
- **Observable**: `git diff` on the two platform files shows added comment lines only; a fresh `pip install -r requirements.txt` resolves exactly as before.

### Step 3: Verify and record the environment facts
- [ ] Record the Python version inside each platform venv (`win11/.venv`, `linux` venv) — this decides whether the local backend needs a venv upgrade before Tasks 2.2/2.6.
- [ ] On the dev box, run a dry-run resolution of platform + optional files together (`pip install --dry-run -r ... -r ...`) with the CPU torch pre-install and record success/failure.
- [ ] Verify mp3 decode in the current environment: `soundfile.read` on a small mp3 (or check the bundled libsndfile version ≥ 1.2) — this validates the no-ffmpeg persona slice design early.
- **Observable**: a short findings note (in the task's implementation PR description) with: both venv Python versions, dry-run result, libsndfile version; any venv below 3.13 flagged with the upgrade decision for Tasks 2.2/2.6.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/requirements-tts-local.txt` | Create | Optional local-engine dependency set with documented constraints |
| `win11/requirements.txt` | Modify | Pointer comment only |
| `linux/requirements.txt` | Modify | Pointer comment only |

### File: `shared/requirements-tts-local.txt`

**Current Code**: none.

**Expected Code**:

```
# Optional local TTS engine for hey-jev (Chatterbox, MIT).
# NOT installed by the platform requirements; opt in with:
#   pip install -r requirements.txt -r ../shared/requirements-tts-local.txt
#
# Constraints (verified against chatterbox-tts 0.1.7 metadata, 2026-09-30):
# 1. Python >= 3.13 required: older interpreters pin numpy<2.0 which conflicts
#    with the platforms' numpy>=2.0. On >= 3.14 the vendor pins torch>=2.9.
# 2. Install torch from the CPU index FIRST (PyPI's same-version CUDA wheel
#    would otherwise win):
#      pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cpu
#    (adjust the pin to the vendor's requirement for your interpreter version)
# 3. First import/render downloads model weights (Nano ~ small, Turbo larger).
--extra-index-url https://download.pytorch.org/whl/cpu
chatterbox-tts>=0.1.7
soundfile>=0.13
```

### File: `win11/requirements.txt`

**Current Code** (lines 1–9):

```
requests>=2.32
python-dotenv>=1.0
numpy>=2.0
sounddevice>=0.5
soundfile>=0.13
pynput>=1.8
faster-whisper>=1.2
pystray>=0.19
Pillow>=10.0
```

**Expected Code After Implementation** (appended):

```

# optional, local TTS backend (Chatterbox): Python >= 3.13 venv, install torch from
# the CPU index first — see ../shared/requirements-tts-local.txt
```

### File: `linux/requirements.txt`

**Current Code** (lines 1–9):

```
requests>=2.32
python-dotenv>=1.0
numpy>=2.0
sounddevice>=0.5
soundfile>=0.13
faster-whisper>=1.2
# optional, X11 only:
# pynput>=1.8        # push-to-talk hotkey
# python3-tk (apt)   # status window
```

**Expected Code After Implementation** (appended):

```

# optional, local TTS backend (Chatterbox): Python >= 3.13 venv, install torch from
# the CPU index first — see ../shared/requirements-tts-local.txt
```

## Testing Approach

### Unit Tests
None — packaging only. Importability of the engine is validated at startup by Task 2.6 (`validate_startup`), not here.

### Manual Verification
1. Base install untouched: fresh `pip install -r requirements.txt --dry-run` resolves identical to pre-task (record hashes/versions)
2. Combined dry-run: platform + optional file with CPU torch pre-installed resolves (record output)
3. mp3 decode: `soundfile.read` succeeds on a small mp3, or bundled libsndfile ≥ 1.2 confirmed

## Acceptance Criteria

- [ ] Optional file exists with the verified pin and the three documented constraints (install order, interpreter floor, install command)
- [ ] Platform requirements files carry comments only; base resolution unchanged
- [ ] Venv Python versions recorded; dry-run result recorded; libsndfile/mp3 capability confirmed
- [ ] All requirements covered: 1.2, 8.1

## Notes

- The vendor wheel pulls `gradio==6.8.0` and other heavy pins — accepted for the optional set (their pyproject, not ours); do not try to shrink it with `--no-deps` games.
- Pin chosen today (`0.1.7`, released 2026-03-26); re-check for a newer release at implementation time and update the comment header if the constraints change.
- If either venv is < 3.13, do NOT relax the platform `numpy>=2.0` pin in this task — record the finding; the upgrade/decision lands with Tasks 2.2/2.6 where the engine is actually exercised.
- The CPU-index pre-install step exists because PEP 440 ranks `2.6.0` above `2.6.0+cpu`; documenting the order is what keeps Windows machines from pulling a multi-GB CUDA wheel.
