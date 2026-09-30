# Task 2.1 — TTS seam dispatch: tags, cache key, unchanged cloud path

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Create the TTS module that owns backend dispatch, the tag mapping, the clip-identity cache key, and the cloud render (moved verbatim), and turn the brain's render entry point into a thin delegate — so every existing caller (local say, remote wav streaming, reminder pre-render, warm cache) keeps working with the cloud backend behaving byte-identically apart from the one-time cache rebuild.

**Dependencies**: Tasks 1.2 (settings), 1.3 (bundled clip + constant), 1.1 (test infra). Task 1.2 before this one.

**Boundary**: `tts` component (new shared module) + the brain delegate + the brain console-trace line. The local engine's internals arrive in Task 2.2 — its dispatch slot raises a clear "not implemented" error here.

**Requirements**: 1.1, 2.1, 2.2, 2.3, 3.2, 3.4, 4.1, 4.2, 4.4, 6.2

## Implementation Steps

### Step 1: Create the TTS module with the cloud render moved verbatim
- [ ] Create the module with: the render error type, the Fish→Chatterbox tag table, the tag mapper, clip resolution, the voice-identity helper, the reply-cache key helper, and the two backend render functions.
- [ ] Move the cloud request **unchanged**: same URL, same headers (`Authorization` bearer + `model: s2.1-pro-free`), same body (`text`, `reference_id` = the cloud voice id, `format: "wav"`), same timeout, same `raise_for_status`, same wav write.
- [ ] Dispatch reads the backend setting at call time via the config module (per-turn patchable); unknown values raise the render error naming the valid ones — never a silent fallback.
- [ ] The chatterbox slot raises a clear "not implemented (task 2.2)" error for now.
- **Observable**: with the default backend, `--text` turns behave exactly as today (same request bytes semantics, same cached/served wavs after rebuild).

### Step 2: Tag mapping with strip fallback
- [ ] Known tags translated for the local backend: `chuckling→chuckle`, `laughing→laugh`, `sighing→sigh`, `clear throat→cough`; anything else (including `cheerful`) removed; tag-free text returned untouched.
- [ ] The cloud backend speaks its own tags: for it, the text passes through unchanged (identity mapping) — this keeps 1.1's byte-identical guarantee.
- [ ] Case-insensitive lookup; whitespace inside tags tolerated (`[Clear Throat]` maps, `[ happy ]` strips).
- **Observable**: unit tests cover the full table, the strip fallback, and the cloud pass-through; no unknown tag can reach synthesis on the local backend.

### Step 3: Voice identity + reply-cache key
- [ ] Voice identity: cloud backend → the configured cloud voice id string; local backend → first 16 hex of the SHA-256 of the active clip file, cached per (path, mtime) so an overwritten clip auto-refreshes (persona switch = cache invalidation for exactly that voice's lines).
- [ ] Active clip resolution: configured clip if set, else the bundled default constant; a configured-but-missing clip raises the render error naming the file.
- [ ] Cache filename: `sha1(f"{backend}|{voice_identity}|{mapped_text}")` under the cache dir; hits return `(path, 0, True)`.
- **Observable**: unit tests show key stability for repeated text and key change when the backend or clip identity changes; the cloud key changes vs the old formula (one-time rebuild — accepted by design).

### Step 4: Brain delegate + trace line
- [ ] Replace the brain render function's body with a delegate call into the new module (docstring kept); import the module the same way the brain imports config today.
- [ ] Update the console trace line to name the active backend and cached/ms (it hardcodes "fish" today).
- **Observable**: remote server, warm cache, and reminder pre-render need zero changes and keep working; the console trace prints `tts fish cached` / `tts fish 812ms` style lines.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tts.py` | Create | Backend dispatch, tag map, clip identity, cache key, cloud render (moved verbatim), chatterbox stub |
| `shared/brain.py` | Modify | Render entry point becomes a delegate; trace line names the backend |
| `shared/tests/test_tags.py` | Create | Tag table, strip fallback, cloud pass-through |
| `shared/tests/test_tts_cache.py` | Create | Clip resolution, cache-key stability/change, dispatch errors |

### File: `shared/brain.py`

**Current Code** (lines 856–868, and line 913):

```python
def fetch_tts(text):
    """Return a wav path for this line, generating it once and caching on disk. Returns (path, ms, cached)."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = os.path.join(config.CACHE_DIR, hashlib.sha1(f"{config.VOICE_ID}|{text}".encode()).hexdigest() + ".wav")
    if os.path.exists(path):
        return path, 0, True
    t = time.time()
    r = requests.post("https://api.fish.audio/v1/tts",
                      headers={"Authorization": f"Bearer {config.FISH_KEY}", "model": "s2.1-pro-free"},
                      json={"text": text, "reference_id": config.VOICE_ID, "format": "wav"}, timeout=60)
    r.raise_for_status()
    open(path, "wb").write(r.content)
    return path, int((time.time() - t) * 1000), False
```

```python
    print(f"  fish {'cached' if tts_ms == 0 else str(tts_ms) + 'ms'}")
```

**Expected Code After Implementation**:

```python
def fetch_tts(text):
    """Return a wav path for this line, generating it once and caching on disk. Returns (path, ms, cached)."""
    return tts.render(text)
```

```python
    print(f"  tts {config.TTS_BACKEND} {'cached' if tts_ms == 0 else str(tts_ms) + 'ms'}")
```

(plus `from shared import tts` added beside the existing shared import — match the file's current import style.)

### File: `shared/tts.py`

**Current Code**: none.

**Expected Code**:

```python
"""TTS backends behind the brain.fetch_tts seam.

INVARIANT: reads every mutable setting as `config.X` at call time (the remote
server and tests patch config per turn). The cloud path is byte-identical to
the pre-feature implementation; the local path (task 2.2) performs no network
I/O and never falls back to the cloud backend on failure.
"""
import hashlib
import os
import re
import time

import requests

from shared import config


class TTSRenderError(RuntimeError):
    """Raised when a line cannot be rendered; callers report it, backends never swap."""


_TAG_RE = re.compile(r"\[([^\]\r\n]+)\]")
FISH_TO_CHATTERBOX = {
    "chuckling": "chuckle",
    "laughing": "laugh",
    "sighing": "sigh",
    "clear throat": "cough",
    # "cheerful" and anything unknown: stripped (no local equivalent)
}


def map_tags(text: str) -> str:
    """Cloud backend speaks Fish tags natively (pass-through). Local backend:
    known tags translated, unknown stripped — a tag is never spoken aloud."""
    if config.TTS_BACKEND != "chatterbox":
        return text

    def repl(m):
        tag = m.group(1).strip().lower()
        mapped = FISH_TO_CHATTERBOX.get(tag)
        return f"[{mapped}]" if mapped else ""

    return _TAG_RE.sub(repl, text)


def active_clip() -> str:
    """Absolute clip path defining the local voice: configured clip, else the
    bundled default. A configured-but-missing clip fails, naming the file."""
    clip = config.TTS_REF_CLIP or config.DEFAULT_VOICE_CLIP
    if not os.path.isfile(clip):
        raise TTSRenderError(f"voice reference clip not found: {clip}")
    return clip


_CLIP_HASHES = {}  # (path, mtime) -> sha256[:16]; refreshed when a clip is overwritten


def voice_identity() -> str:
    """Stable voice token for the cache key: cloud voice id, or clip content hash."""
    if config.TTS_BACKEND != "chatterbox":
        return config.VOICE_ID
    path = active_clip()
    key = (path, os.path.getmtime(path))
    h = _CLIP_HASHES.get(key)
    if h is None:
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
        _CLIP_HASHES.clear()  # keep only the active voice's hash
        _CLIP_HASHES[key] = h
    return h


def _cache_path(mapped_text: str) -> str:
    key = hashlib.sha1(f"{config.TTS_BACKEND}|{voice_identity()}|{mapped_text}".encode()).hexdigest()
    return os.path.join(config.CACHE_DIR, key + ".wav")


def _render_fish(text: str):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = _cache_path(text)  # map_tags is identity for the cloud backend
    if os.path.exists(path):
        return path, 0, True
    t = time.time()
    r = requests.post("https://api.fish.audio/v1/tts",
                      headers={"Authorization": f"Bearer {config.FISH_KEY}", "model": "s2.1-pro-free"},
                      json={"text": text, "reference_id": config.VOICE_ID, "format": "wav"}, timeout=60)
    r.raise_for_status()
    open(path, "wb").write(r.content)
    return path, int((time.time() - t) * 1000), False


def _render_chatterbox(text: str):
    raise TTSRenderError("chatterbox backend not implemented (task 2.2)")


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

### File: `shared/tests/test_tags.py`

**Current Code**: none.

**Expected Code** (essentials):

```python
import pytest

from shared import config, tts


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")


def test_known_tags_map(local):
    assert tts.map_tags("[chuckling] hi") == "[chuckle] hi"
    assert tts.map_tags("[laughing] [sighing] [clear throat]") == "[laugh] [sigh] [cough]"


def test_unknown_tags_stripped(local):
    assert tts.map_tags("[cheerful] hi [shrug]") == " hi "
    assert "[" not in tts.map_tags("[whatever] ok")


def test_tag_free_untouched(local):
    assert tts.map_tags("plain text") == "plain text"


def test_cloud_passthrough(monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    assert tts.map_tags("[chuckling] hi [cheerful]") == "[chuckling] hi [cheerful]"
```

### File: `shared/tests/test_tts_cache.py`

**Current Code**: none.

**Expected Code** (essentials; state_isolation fixture from task 1.1):

```python
import pytest

from shared import config, tts


def test_clip_resolution_bundled(state_isolation):
    import os
    assert tts.active_clip() == config.DEFAULT_VOICE_CLIP
    assert os.path.isfile(tts.active_clip())


def test_clip_resolution_missing_configured_fails(state_isolation):
    monkey = pytest.MonkeyPatch()
    monkey.setattr(config, "TTS_REF_CLIP", "/no/such/clip.wav")
    with pytest.raises(tts.TTSRenderError, match="/no/such/clip.wav"):
        tts.active_clip()
    monkey.undo()


def test_unknown_backend_raises(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "piper")
    with pytest.raises(tts.TTSRenderError, match="piper"):
        tts.render("hi")


def test_chatterbox_stub_raises(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    with pytest.raises(tts.TTSRenderError, match="2.2"):
        tts.render("hi")


def test_cache_key_changes_with_backend_and_voice(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    k_fish = tts._cache_path("hi")
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    k_local = tts._cache_path("hi")
    assert k_fish != k_local
    # key is stable for repeated calls
    assert tts._cache_path("hi") == k_local
```

## Testing Approach

### Unit Tests
1. Tag table: every Fish tag maps or strips exactly as designed (local backend); cloud backend passes through untouched
   - Input: each reply tag / unknown tag / tag-free line
   - Expected: mapped `[chuckle] [laugh] [sigh] [cough]`; unknown removed; plain text identical
2. Clip resolution: unset → bundled default exists; configured missing → error names the file
   - Input: isolated config state
   - Expected: as above
3. Cache key: stable for same inputs; changes with backend or clip identity; cloud key differs from the legacy `VOICE_ID|text` key (rebuild-once accepted)
   - Input: same text across patched settings
   - Expected: equality/inequality as designed
4. Dispatch: unknown backend and chatterbox-stub raise the render error (no fallback)
   - Input: patched backend values
   - Expected: `TTSRenderError` with the offending value in the message

### Integration Tests
Deferred to Task 4.1 (real cloud call + both backends end-to-end).

## Acceptance Criteria

- [ ] Cloud render request is byte-for-byte the same as the pre-feature implementation (URL, headers, model string, body keys, timeout)
- [ ] Default backend behaves identically for callers; one-time cache rebuild is the only observable difference
- [ ] Tag handling: known → mapped, unknown → stripped, none → untouched; reminder alert lines inherit it automatically (same seam)
- [ ] Cache key includes backend + voice identity; voice identity = clip content hash on the local backend, cloud voice id on the cloud backend
- [ ] Dispatch never falls back silently; unknown backend and the not-yet-implemented local path raise the dedicated error
- [ ] Trace line reports the active backend with cached/ms
- [ ] All requirements covered: 1.1, 2.1, 2.2, 2.3, 3.2, 3.4, 4.1, 4.2, 4.4, 6.2

## Notes

- Import style inside `shared/tts.py` must match `brain.py` (same package-import shape for config) — check the existing header before writing.
- `map_tags` is called once per render inside `render`; `warm_cache` and reminder prep therefore get identical treatment with zero changes of their own.
- The cloud cache-key change orphans the old `sha1(VOICE_ID|text)` files — leave them; the disk cost is trivial and a cleanup is explicitly out of scope.
- `speak()` (brain) needs no edit: it already calls `fetch_tts` then the playback hook.
