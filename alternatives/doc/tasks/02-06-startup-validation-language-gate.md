# Task 2.6 — Startup validation and the language gate

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Give the TTS module one function that answers "is the current speech configuration usable?" — backend name, local-engine availability, voice clip presence, and the English-only gate for the local backend — returning named-fix problems the platform entry points (Task 3.2) will surface before the mic opens.

**Dependencies**: Task 2.2 (the local backend this validates).

**Boundary**: `tts` component (the validator + its tests) only. The call wiring into the platform entry points is Task 3.2.

**Requirements**: 1.3, 3.3, 5.1, 5.2, 5.3

## Implementation Steps

### Step 1: The validator
- [ ] Add `validate_startup()` to the TTS module returning a list of human-readable blocking problems (empty = ready). Each message names the offending value or file and the fix.
- [ ] Unknown backend → one problem listing the valid names (early return — backend-specific checks would only add noise).
- [ ] Local backend selected → three checks in order:
  1. Engine importability (probe through a tiny helper so tests can stub it without touching the real import).
  2. Language gate: any configured language beyond English blocks the local backend, naming the languages and the two fixes (drop them, or use the cloud backend).
  3. Voice clip: a configured clip must exist (error names the file); unset means the bundled default, which must also exist (reinstall/set-a-clip hint).
- [ ] Cloud backend → no clip or language checks (the existing platform key checks stay where they are).
- **Observable**: every invalid combination produces exactly the message designed; valid combinations return an empty list.

### Step 2: Message wording (naming the fix)
- [ ] Unknown backend: `unknown TTS_BACKEND 'piper'; valid: fish, chatterbox (set TTS_BACKEND in .env)`
- [ ] Engine missing: `... local engine is not installed; run: pip install -r shared/requirements-tts-local.txt (Python >= 3.13)`
- [ ] Language gate: `... supports English replies only; configured languages ['de'] need the cloud backend (unset WHISPER_LANGUAGES or set TTS_BACKEND=fish)`
- [ ] Configured clip missing: `TTS_REF_CLIP not found: <path>`
- [ ] Bundled clip missing: `bundled voice clip missing: <path> (reinstall or set TTS_REF_CLIP)`
- **Observable**: unit tests assert each message on its triggering combination.

### Step 3: Tests
- [ ] Full matrix as unit tests with the per-test state isolation: unknown backend; chatterbox + engine stubbed present/absent; English-only passes; `en,de` fails; configured clip missing fails; unset clip with existing bundled default passes; cloud backend skips clip/language checks.
- **Observable**: the matrix passes offline (the engine probe is stubbed; no real import needed in unit tests).

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tts.py` | Modify | `validate_startup()` + engine-probe helper |
| `shared/tests/test_tts_cache.py` | Modify | Startup-matrix tests appended |

### File: `shared/tts.py`

**Current Code** (the dispatch tail after Tasks 2.1/2.2):

```python
def render(text: str):
    """brain.fetch_tts seam: -> (wav_path, render_ms, cached)."""
    backend = config.TTS_BACKEND
    mapped = map_tags(text)
    if backend == "fish":
        return _render_fish(mapped)
    if backend == "chatterbox":
        return _render_chatterbox(mapped)
    raise TTSRenderError(
        f"unknown TTS backend {backend!r}; valid: {', '.join(config.TTS_BACKENDS)}")
```

**Expected Code After Implementation** (appended after `render`):

```python
def _engine_importable() -> bool:
    try:
        import chatterbox  # noqa: F401  (probe only; the real load stays lazy)
        return True
    except ImportError:
        return False


def validate_startup() -> list:
    """Blocking TTS problems for the current settings; empty list = ready.
    Platform entry points print each problem and exit before the mic opens."""
    problems = []
    backend = config.TTS_BACKEND
    if backend not in config.TTS_BACKENDS:
        problems.append(f"unknown TTS_BACKEND {backend!r}; "
                        f"valid: {', '.join(config.TTS_BACKENDS)} (set TTS_BACKEND in .env)")
        return problems
    if backend != "chatterbox":
        return problems
    if not _engine_importable():
        problems.append("TTS_BACKEND=chatterbox but the local engine is not installed; "
                        "run: pip install -r shared/requirements-tts-local.txt (Python >= 3.13)")
    non_en = config.WHISPER_LANGUAGES - {"en"}
    if non_en:
        problems.append(f"TTS_BACKEND=chatterbox supports English replies only; configured "
                        f"languages {sorted(non_en)} need the cloud backend "
                        "(unset WHISPER_LANGUAGES or set TTS_BACKEND=fish)")
    if config.TTS_REF_CLIP:
        if not os.path.isfile(config.TTS_REF_CLIP):
            problems.append(f"TTS_REF_CLIP not found: {config.TTS_REF_CLIP}")
    elif not os.path.isfile(config.DEFAULT_VOICE_CLIP):
        problems.append(f"bundled voice clip missing: {config.DEFAULT_VOICE_CLIP} "
                        "(reinstall or set TTS_REF_CLIP)")
    return problems
```

### File: `shared/tests/test_tts_cache.py`

**Current Code** (end of file after Task 2.1's additions; appended below):

```python
def test_cache_key_changes_with_backend_and_voice(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    k_fish = tts._cache_path("hi")
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    k_local = tts._cache_path("hi")
    assert k_fish != k_local
    # key is stable for repeated calls
    assert tts._cache_path("hi") == k_local
```

**Expected Code After Implementation** (appended):

```python
def test_startup_unknown_backend(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "piper")
    problems = tts.validate_startup()
    assert len(problems) == 1 and "piper" in problems[0] and "chatterbox" in problems[0]


def test_startup_chatterbox_valid(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_engine_importable", lambda: True)
    assert tts.validate_startup() == []          # 5.1: English-only + bundled clip


def test_startup_engine_missing(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_engine_importable", lambda: False)
    problems = tts.validate_startup()
    assert any("requirements-tts-local" in p for p in problems)


def test_startup_language_gate(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_engine_importable", lambda: True)
    monkeypatch.setattr(config, "WHISPER_LANGUAGES", {"en", "de"})
    problems = tts.validate_startup()
    assert any("de" in p and "cloud" in p for p in problems)   # 5.2


def test_startup_configured_clip_missing(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_engine_importable", lambda: True)
    monkeypatch.setattr(config, "TTS_REF_CLIP", "/no/such/clip.wav")
    assert any("/no/such/clip.wav" in p for p in tts.validate_startup())  # 3.3


def test_startup_cloud_backend_skips_clip_checks(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    monkeypatch.setattr(config, "TTS_REF_CLIP", "/no/such/clip.wav")  # irrelevant on cloud
    assert tts.validate_startup() == []
```

## Testing Approach

### Unit Tests (offline)
1. Unknown backend: single problem naming valid values; early return (no backend-specific noise)
2. Valid local combo: empty problems (English-only, bundled clip, engine stubbed present) (5.1)
3. Engine absent: problem with the install command
4. Language gate: `en,de` → problem naming the languages and both fixes (5.2, 5.3)
5. Clip checks: configured-missing names the file (3.3); unset-with-bundled passes; cloud backend skips both
6. No unit test imports the real engine (probe stubbed); the real import is exercised by Task 2.2's slow test

### Integration Tests
The platform call wiring (voice path and the remote path, which today exits before the key checks) lands in Task 3.2 with a `--text` observable.

## Acceptance Criteria

- [ ] Every invalid combination returns exactly one named-fix message; valid combinations return an empty list
- [ ] The language gate blocks the local backend for any non-English configured language and names both fixes
- [ ] Configured-but-missing clip and missing bundled clip each produce their own message
- [ ] The cloud backend is unaffected by clip/language checks; existing key checks untouched
- [ ] Unit matrix passes offline from both platform folders
- [ ] All requirements covered: 1.3, 3.3, 5.1, 5.2, 5.3

## Notes

- Wiring split by design: this task delivers the validator and proves it; Task 3.2 adds the `problems = tts.validate_startup(); if problems: sys.exit("\n".join(problems))` call to both platforms — **including the `--remote` path**, which today returns before the Fish-key checks (the server process renders speech too, so it must validate as well).
- The engine probe imports the top-level package only (cheap-ish: it does pull torch); acceptable at startup **only when the local backend is selected** — cloud users never pay it.
- `validate_startup` intentionally does not pre-load the model (first render does, inside the turn's Speaking state); a future `--warm` flag could pre-load, out of scope.
- `WHISPER_LANGUAGES - {"en"}` mirrors the linux multilingual STT logic's set arithmetic — the gate is consistent with how languages are already configured.
