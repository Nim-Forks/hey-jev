# Task 1.3 — Ship the bundled default voice clip

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Promote the sourced public-domain clip into the shared runtime assets and give the codebase a single, overridable constant for "the bundled default voice", so a fresh checkout can resolve the default voice path without any configuration or download.

**Dependencies**: Task 1.2 (the TTS settings block this constant sits beside; tests infra from 1.1).

**Boundary**: repo `assets/` (binary asset), one new constant in shared config, one test — no TTS logic (resolution semantics land in Task 2.1).

**Requirements**: 3.2

## Implementation Steps

### Step 1: Copy the clip into the shared runtime assets
- [ ] Copy `alternatives/doc/voice-ref-clip.wav` to `assets/voice-default.wav` (repo-root `assets/`, where the app icon already lives).
- [ ] Verify the copy is byte-identical (same SHA-256) and still verifies as 25 s / 24 kHz / mono PCM wav.
- [ ] Keep `alternatives/doc/voice-ref-clip.wav` untouched as the sourcing artifact; it is not referenced at runtime.
- **Observable**: `assets/voice-default.wav` exists on the branch, byte-identical to the sourcing artifact.

### Step 2: Expose the bundled default as a config constant
- [ ] Add `DEFAULT_VOICE_CLIP` to the shared config next to the TTS settings: absolute path computed from the config module's own location up to the repo-root `assets` folder (same relative pattern the remote server uses for the favicon), overridable as a plain module attribute.
- [ ] Do not change `TTS_REF_CLIP` semantics here: unset still means "bundled default"; the mapping of unset → `DEFAULT_VOICE_CLIP` is Task 2.1's resolution logic.
- **Observable**: with no environment set, the constant points at an existing 25 s wav on a fresh checkout.

### Step 3: Prove it in tests and document the swap path
- [ ] Extend the config test: the default clip path exists and soundfile reads 24 kHz mono with a duration of ≈25 s (±1 s).
- [ ] Document the swap path in the feature docs: replacing the bundled voice = overwrite `assets/voice-default.wav` or set the reference-clip environment override (both already covered in `research.md` — add the constant name to that note).
- **Observable**: config tests pass on both platforms; the docs mention the constant and both swap mechanisms.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `assets/voice-default.wav` | Create | The bundled default persona clip (25 s, 24 kHz mono PCM, public domain) |
| `shared/config.py` | Modify | `DEFAULT_VOICE_CLIP` constant beside the Task 1.2 TTS settings |
| `shared/tests/test_config.py` | Modify | Default-clip existence/format test |
| `alternatives/doc/research.md` | Modify | Name the constant in the reference-clip sourcing note |

### File: `shared/config.py`

**Current Code** (state after Task 1.2, TTS settings block):

```python
# TTS backend switch. "fish" = cloud API (current behavior, default).
# "chatterbox" = local open-source engine (optional install, English-only).
TTS_BACKENDS = ("fish", "chatterbox")
TTS_BACKEND = os.getenv("TTS_BACKEND", "fish").strip().lower()
TTS_REF_CLIP = os.getenv("TTS_REF_CLIP", "").strip() or None  # None -> bundled default clip
TTS_CHATTERBOX_VARIANT = os.getenv("TTS_CHATTERBOX_VARIANT", "nano").strip().lower()
```

**Expected Code After Implementation** (block extended by one constant):

```python
# TTS backend switch. "fish" = cloud API (current behavior, default).
# "chatterbox" = local open-source engine (optional install, English-only).
TTS_BACKENDS = ("fish", "chatterbox")
TTS_BACKEND = os.getenv("TTS_BACKEND", "fish").strip().lower()
TTS_REF_CLIP = os.getenv("TTS_REF_CLIP", "").strip() or None  # None -> bundled default clip
TTS_CHATTERBOX_VARIANT = os.getenv("TTS_CHATTERBOX_VARIANT", "nano").strip().lower()
# Bundled default voice (public domain; swap by overwriting the file or setting TTS_REF_CLIP).
_DEFAULT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_VOICE_CLIP = os.path.join(os.path.dirname(_DEFAULT_DIR), "assets", "voice-default.wav")
```

### File: `shared/tests/test_config.py`

**Current Code** (end of the file after Task 1.2):

```python
def test_settings_are_patchable_module_attributes(monkeypatch):
    import config
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(config, "PERSONAS_CACHE_DIR", "/tmp/x")
    assert config.TTS_BACKEND == "chatterbox"  # per-turn/global patch contract honored
```

**Expected Code After Implementation** (appended):

```python
def test_bundled_default_clip():
    import os
    import soundfile as sf
    import config
    assert os.path.isfile(config.DEFAULT_VOICE_CLIP)
    data, sr = sf.read(config.DEFAULT_VOICE_CLIP)
    assert sr == 24000 and data.ndim == 1
    assert 24.0 <= len(data) / sr <= 26.0
```

### File: `assets/voice-default.wav`

**Current Code**: none (new binary asset).

**Expected Content**: exact copy of `alternatives/doc/voice-ref-clip.wav` — 25.00 s, 24 000 Hz, mono, s16 PCM, ~1.2 MB. Sourcing: LibriVox, *The Sonnets*, read by Elizabeth Klett (archive.org item `sonnets_etk_librivox`, public domain) — full provenance in `alternatives/doc/research.md`.

### File: `alternatives/doc/research.md`

**Current Code** (sourcing note, last sentence):

```
... Swap by pointing `TTS_REF_CLIP` at another clip; the cache key changes with it, so no stale audio reuse.
```

**Expected Code After Implementation** (sentence extended):

```
... Swap by pointing `TTS_REF_CLIP` at another clip or overwriting `assets/voice-default.wav`
(referenced at runtime via `config.DEFAULT_VOICE_CLIP`); the cache key changes with it, so no
stale audio reuse.
```

## Testing Approach

### Unit Tests
1. Bundled clip: exists, 24 kHz mono, ≈25 s
   - Input: `config.DEFAULT_VOICE_CLIP`
   - Expected: file present; soundfile reads sr 24000, mono, duration within ±1 s

### Integration Tests
None in this task (asset + constant only).

## Acceptance Criteria

- [ ] `assets/voice-default.wav` exists and is byte-identical to the sourcing artifact
- [ ] `DEFAULT_VOICE_CLIP` resolves to the existing file on a fresh checkout, overridable as a module attribute
- [ ] Config test verifies format and duration; passes from both platform folders
- [ ] Sourcing artifact retained in the feature docs; swap path documented with the constant name
- [ ] All requirements covered: 3.2

## Notes

- Keep the wav out of any future LFS/cleanup decisions until the repo decides on binary policy — it is 1.2 MB, committed once.
- The relative path goes one directory up from the config module (shared → repo root) — the same convention the remote server uses for the icon, so packaged launches that already locate the icon will locate the clip.
- No backend logic may read `DEFAULT_VOICE_CLIP` before Task 2.1; until then the constant is documentation + testable path.
