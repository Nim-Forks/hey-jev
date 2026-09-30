# Task 1.2 — Feature settings and prerequisite repair

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Give the feature its overridable settings (backend switch, reference clip, local-model variant, persona storage paths) in the shared config module, and repair the latent startup failure by defining the STT attributes the remote server and both platforms already reference (`WHISPER_MODEL`, `WHISPER_LANGUAGES`).

**Dependencies**: none (independent; recommended first executable task — Task 1.1's isolation fixture consumes these settings).

**Boundary**: shared config module only (settings + a small parse helper); no product logic.

**Requirements**: 1.4, 3.2, 3.3, 5.2

## Implementation Steps

### Step 1: Add the TTS backend settings
- [ ] Add `TTS_BACKEND` read from the environment with `"fish"` as default, normalized (trimmed, lowercased).
- [ ] Add the tuple of valid backend names (`"fish"`, `"chatterbox"`) as a module constant so startup validation (Task 2.6) and tests share one source of truth. Validation itself is not in this task.
- [ ] Add `TTS_REF_CLIP` (environment override; empty/None means "use the bundled default clip" — the resolution to a real path happens in the TTS module, not here).
- [ ] Add `TTS_CHATTERBOX_VARIANT` (environment; `"nano"` default, `"turbo"` allowed).
- **Observable**: importing the shared core exposes all three settings with the documented defaults, and an environment change is the only thing needed to flip them.

### Step 2: Add the persona storage paths
- [ ] Add `PERSONAS_CACHE_DIR` (default under the shared cache folder, per-persona clips one file each) and `PERSONA_FILE` (default next to the timers state), both following the existing "platform layer overrides to its own folder" pattern.
- [ ] Update the module docstring so the path-override list includes the two new paths alongside timers and cache.
- **Observable**: both paths resolve under the shared folder on a fresh checkout and are plain module attributes a platform layer can rebind.

### Step 3: Repair the STT attributes
- [ ] Define `WHISPER_MODEL` (environment override, default the current English model name) — the remote server, both platform modules, and the legacy mac layer reference it today while it exists nowhere in the shared config.
- [ ] Define `WHISPER_LANGUAGES` as a set of language codes parsed from a comma-separated environment value, defaulting to English-only; extract the parsing into a tiny named helper so tests can cover it without reloading the module.
- [ ] Keep the set-typed value: callers (the linux multilingual STT spec logic) do set arithmetic on it.
- **Observable**: with no environment set, the two STT attributes resolve to the current English defaults; setting the environment variable to `en,de` yields the set `{"en", "de"}`.
- [ ] Do NOT extend `reload_keys()` or the remote server's client-key cleaning: these settings are operator configuration, not per-turn client-patchable values (boundary note from design).

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/config.py` | Modify | Add TTS/persona settings + STT attribute repair + parse helper |
| `shared/tests/test_config.py` | Create | Unit tests for defaults, env parsing, valid-backend set (lands with Task 1.1's infrastructure) |

### File: `shared/config.py`

**Current Code** (lines 44–51):

```python
# paths (platform layer overrides both to its own folder)
TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")

# hooks the platform layer must wire (see doc/01-migration-plan.md)
machine_context_hook = None   # () -> str
play_wav_hook = None          # (path) -> None
stt_spec_hook = None          # () -> (model_name, language)
```

**Expected Code After Implementation** (lines 44–62, insertion after `CACHE_DIR`, hooks unchanged below):

```python
# paths (platform layer overrides both to its own folder)
TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
# persona storage (platform layer overrides both to its own folder)
PERSONAS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "personas")
PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")

# TTS backend switch. "fish" = cloud API (current behavior, default).
# "chatterbox" = local open-source engine (optional install, English-only).
TTS_BACKENDS = ("fish", "chatterbox")
TTS_BACKEND = os.getenv("TTS_BACKEND", "fish").strip().lower()
TTS_REF_CLIP = os.getenv("TTS_REF_CLIP", "").strip() or None  # None -> bundled default clip
TTS_CHATTERBOX_VARIANT = os.getenv("TTS_CHATTERBOX_VARIANT", "nano").strip().lower()

# STT spec, shared-resolved (doc/02-risks-invariants.md #8). Previously referenced
# by remote_server + platforms but defined only in the legacy mac layer.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small.en")

def _parse_languages(raw: str) -> set:
    return {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}

WHISPER_LANGUAGES = _parse_languages(os.getenv("WHISPER_LANGUAGES", "en"))

# hooks the platform layer must wire (see doc/01-migration-plan.md)
machine_context_hook = None   # () -> str
play_wav_hook = None          # (path) -> None
stt_spec_hook = None          # () -> (model_name, language)
```

Also update the module docstring's list of per-turn values only if it names paths explicitly (it names TIMERS_FILE/CACHE_DIR as the platform-overridden paths — extend that sentence with the two persona paths; the TTS settings are operator configuration and intentionally not listed as per-turn patchable).

### File: `shared/tests/test_config.py`

**Current Code**: none.

**Expected Code**:

```python
def test_defaults_resolve():
    import config
    assert config.TTS_BACKEND == "fish"
    assert config.TTS_REF_CLIP is None
    assert config.TTS_CHATTERBOX_VARIANT == "nano"
    assert config.WHISPER_MODEL == "small.en"
    assert config.WHISPER_LANGUAGES == {"en"}
    assert "fish" in config.TTS_BACKENDS and "chatterbox" in config.TTS_BACKENDS

def test_language_parsing():
    import config
    assert config._parse_languages("en") == {"en"}
    assert config._parse_languages("en, de ; pt-BR") == {"en", "de", "pt-BR"}
    assert config._parse_languages("  ") == set()

def test_settings_are_patchable_module_attributes(monkeypatch):
    import config
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(config, "PERSONAS_CACHE_DIR", "/tmp/x")
    assert config.TTS_BACKEND == "chatterbox"  # per-turn/global patch contract honored
```

## Testing Approach

### Unit Tests
1. Defaults: fresh import yields the documented values (backend `fish`, clip `None`, variant `nano`, model `small.en`, languages `{"en"}`)
   - Input: module import with no environment overrides
   - Expected: values above
2. Language parsing: `"en"`, `"en, de ; pt-BR"`, blank
   - Input: raw string
   - Expected: `{"en"}` / `{"en","de","pt-BR"}` / empty set
3. Patchability: monkeypatching the module attributes works
   - Input: `monkeypatch.setattr(config, ...)`
   - Expected: reads reflect the patch (the global-patch contract)

### Integration Tests
None in this task (settings only; startup validation lands in Task 2.6).

## Acceptance Criteria

- [ ] All new settings exist as module attributes with environment overrides and documented defaults
- [ ] `WHISPER_MODEL` / `WHISPER_LANGUAGES` resolve at import (no more reference-to-undefined)
- [ ] Valid backend names are a single shared constant; the language parse helper is unit-tested
- [ ] `reload_keys()` and client-key cleaning are untouched (operator-only settings)
- [ ] All requirements covered: 1.4, 3.2, 3.3, 5.2

## Notes

- `TTS_REF_CLIP=None` means "bundled default" by contract; only the TTS module turns that into a path (Task 2.1) and only startup validation fails on a set-but-missing clip (Task 2.6, requirement 3.3) — this task only guarantees the attribute and its default semantics.
- Normalization choice: lowercase/trim the backend and variant values here so validation later compares against the constants without repeating cleanup.
- Do not import anything new; the file keeps its stdlib + requests + dotenv + secrets-store imports only.
