# Task 2.3 — (P) Persona module: catalog, screening, clip cache, persistence

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Own the persona domain end to end: a curated public-domain-only catalog, automatic clip sourcing (download → decode → slice → resample → per-persona cached wav) with a double license screen, roster/lookup behavior, and restart-surviving active-persona persistence — so the "switch persona" command (Task 2.5) and the voice hookup (Task 3.1) only consume this module.

**Dependencies**: Tasks 1.1 (test infra + synthetic fixture), 1.2 (persona storage paths). Parallel-safe with 2.1/2.2: disjoint file (`personas.py` vs `tts.py`/`brain.py`), no shared resource beyond config.

**Boundary**: `personas` component (new shared module + its tests). No routing, no TTS changes.

**Requirements**: 9.3, 9.4, 9.6, 10.1, 10.2, 10.3, 10.4

## Implementation Steps

### Step 1: Catalog with construction-time license screening
- [ ] Define the persona entries as data: `name` (natural key, lowercase), `description` (short, spoken-friendly), `reader`, `source_url` (direct per-recording file), `source_license`, `start_s`, `duration_s` (~25 s target). The archive.org item identifier is parsed from the source URL (no extra field needed).
- [ ] The bundled persona `jev` has no source: it maps to the bundled default clip (no download ever).
- [ ] Build the catalog through one function that **rejects any entry whose license is not in the permissive set** (public domain / CC0) — a non-permissive curated entry is a programming error and fails loudly.
- **Observable**: importing the module yields the validated catalog; a deliberately added bad-license entry fails construction in tests.

### Step 2: Fetch + slice + resample + cache (download once)
- [ ] `clip_for(name)`: unknown name → `None`; bundled persona → the bundled clip path directly (no fetch); catalog persona → cached wav if present, else fetch.
- [ ] Fetch: re-check the source's license via the item metadata endpoint (license field of the item) — mismatch or failed check → `None` (unavailable, never a partial file); then download the file with a timeout and a sane size cap, decode in-process (soundfile, no ffmpeg), slice `[start_s, start_s+duration_s]`, downmix to mono, numpy-linear-resample to 24 kHz, and write `{name}.wav` into the persona cache.
- [ ] Idempotency: an existing `{name}.wav` short-circuits everything (second fetch of a persona performs no network call).
- **Observable**: with no network, a fresh start serves the bundled persona; after one successful fetch, restarts and repeated lookups hit only the local cache (unit-provable by making the HTTP client raise on second call).

### Step 3: Lookup, roster, persistence
- [ ] `resolve(name)`: exact (case-insensitive) match → canonical name, else `None` — the router (Task 2.5) decides the user-facing reply.
- [ ] `list_personas()`: `[{name, description, active}]` — roster announcements and the switch confirmation consume this.
- [ ] `set_active(name)` (validates via resolve) + `active()` (default `jev`): persisted as `{"persona": name}` in the persona state file, written atomically (temp file + replace, the timers-save pattern); a missing or corrupt file silently falls back to `jev`.
- **Observable**: persistence round-trip test passes; a corrupt state file yields `jev` without an error path.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/personas.py` | Create | Catalog + screening + fetch/slice/cache + lookup + persistence |
| `shared/tests/test_personas.py` | Create | Screening, slice/resample math, cache idempotency, persistence, unknown/unavailable behavior |

### File: `shared/personas.py`

**Current Code**: none.

**Expected Code**:

```python
"""Persona catalog + automatic voice-clip sourcing.

INVARIANT: reads mutable settings as `config.X` at call time. Clips are
fetched ONLY from curated catalog entries whose license is public domain /
CC0 — never from user-supplied URLs. The bundled persona never downloads.
"""
import io
import json
import os
import re
import time

import numpy as np
import requests

from shared import config

TARGET_SR = 24000
_PERMISSIVE = ("publicdomain", "cc0")  # substring match, lowercase
_ITEM_RE = re.compile(r"archive\.org/download/([^/]+)/", re.I)
_MAX_SOURCE_BYTES = 20 * 1024 * 1024

_PERSONAS = (
    {"name": "jev", "description": "the default Jev voice", "reader": "Elizabeth Klett",
     "source_url": None, "source_license": "publicdomain", "start_s": 0.0, "duration_s": 0.0},
    # two downloadable entries land in task 2.4 (same screening)
)


def _license_ok(license_str: str) -> bool:
    s = (license_str or "").lower()
    return any(p in s for p in _PERMISSIVE)


def _item_from_url(url: str):
    m = _ITEM_RE.search(url or "")
    return m.group(1) if m else None


def _catalog() -> tuple:
    for p in _PERSONAS:
        if p["source_url"] is not None and not _license_ok(p["source_license"]):
            raise RuntimeError(f"persona {p['name']}: license not permissive: {p['source_license']}")
    return _PERSONAS


def resolve(name: str):
    n = (name or "").strip().lower()
    for p in _catalog():
        if p["name"] == n:
            return p["name"]
    return None


def list_personas() -> list:
    cur = active()
    return [{"name": p["name"], "description": p["description"], "active": p["name"] == cur}
            for p in _catalog()]


def _state_path():
    return config.PERSONA_FILE


def active() -> str:
    try:
        return json.load(open(_state_path())).get("persona") or "jev"
    except Exception:
        return "jev"


def set_active(name: str):
    canon = resolve(name)
    if canon is None:
        raise KeyError(name)
    tmp = _state_path() + ".tmp"
    json.dump({"persona": canon}, open(tmp, "w"))
    os.replace(tmp, _state_path())


def _cached_path(name: str) -> str:
    return os.path.join(config.PERSONAS_CACHE_DIR, f"{name}.wav")


def _slice_resample(data, sr, start_s: float, dur_s: float):
    if data.ndim > 1:
        data = data.mean(axis=1)
    a = int(start_s * sr)
    seg = data[a: a + int(dur_s * sr)]
    if len(seg) < sr // 2:
        raise ValueError("clip slice too short")
    n_out = int(len(seg) * TARGET_SR / sr)
    return np.interp(np.linspace(0, len(seg) - 1, n_out), np.arange(len(seg)), seg).astype(np.float32)


def _licenseurl_from_item(item: str):
    r = requests.get(f"https://archive.org/metadata/{item}", timeout=30)
    r.raise_for_status()
    return (r.json().get("metadata") or {}).get("licenseurl", "")


def _download_and_store(p: dict, dest: str):
    item = _item_from_url(p["source_url"])
    if not item or not _license_ok(_licenseurl_from_item(item)):
        raise ValueError("license check failed")
    r = requests.get(p["source_url"], timeout=60)
    r.raise_for_status()
    if len(r.content) > _MAX_SOURCE_BYTES:
        raise ValueError("source file too large")
    data, sr = __import__("soundfile").read(io.BytesIO(r.content), dtype="float32", always_2d=False)
    audio = _slice_resample(data, sr, p["start_s"], p["duration_s"])
    __import__("soundfile").write(dest, audio, TARGET_SR, subtype="PCM_16")


def clip_for(name: str):
    canon = resolve(name)
    if canon is None:
        return None
    p = next(x for x in _catalog() if x["name"] == canon)
    if p["source_url"] is None:            # bundled persona: no fetch, ever
        return config.DEFAULT_VOICE_CLIP
    dest = _cached_path(canon)
    if os.path.isfile(dest):               # cache hit: no network (10.2/10.3)
        return dest
    try:
        _download_and_store(p, dest)
    except Exception as e:
        print(f"  persona {canon}: clip unavailable: {e}")
        return None                        # 10.5: caller keeps the current voice
    return dest
```

### File: `shared/tests/test_personas.py`

**Current Code**: none.

**Expected Code** (essentials; `synthetic_clip` fixture from Task 1.1 provides a 24 kHz tone wav path):

```python
import json
import io

import numpy as np
import pytest
import soundfile as sf

from shared import config, personas


def test_catalog_screening_rejects_bad_license(monkeypatch):
    monkeypatch.setattr(personas, "_PERSONAS", (
        {"name": "x", "description": "", "reader": "", "source_url": "https://archive.org/download/i/f.mp3",
         "source_license": "CC-BY-NC", "start_s": 0, "duration_s": 5},
    ))
    with pytest.raises(RuntimeError, match="not permissive"):
        personas._catalog()


def test_resolve_unknown_and_bundled():
    assert personas.resolve("nope") is None
    assert personas.resolve("JEV") == "jev"
    assert personas.clip_for("jev") == config.DEFAULT_VOICE_CLIP


def test_clip_for_fetches_once_then_cache_only(monkeypatch, state_isolation, synthetic_clip):
    data, sr = sf.read(synthetic_clip, dtype="float32")
    calls = {"n": 0}
    def fake_get(url, timeout=0, **k):
        calls["n"] += 1
        class R:
            content = open(synthetic_clip, "rb").read()
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"metadata": {"licenseurl": "http://creativecommons.org/licenses/publicdomain/"}}
        return R()
    monkeypatch.setattr(personas.requests, "get", fake_get)
    monkeypatch.setattr(personas, "_PERSONAS", (
        {"name": "k", "description": "test", "reader": "r",
         "source_url": "https://archive.org/download/item_x/file_64kb.mp3",
         "source_license": "publicdomain", "start_s": 0.5, "duration_s": 2.0},
    ))
    p1 = personas.clip_for("k")
    assert p1 and p1.endswith("k.wav")
    p2 = personas.clip_for("k")
    assert p1 == p2 and calls["n"] == 1  # second call: cache only
    d, s = sf.read(p1)
    assert s == personas.TARGET_SR and d.ndim == 1


def test_license_mismatch_is_unavailable(monkeypatch, state_isolation, synthetic_clip):
    def fake_get(url, timeout=0, **k):
        class R:
            content = b""
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"metadata": {"licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/"}}
        return R()
    monkeypatch.setattr(personas.requests, "get", fake_get)
    monkeypatch.setattr(personas, "_PERSONAS", (
        {"name": "k", "description": "", "reader": "", "source_url": "https://archive.org/download/i/f.mp3",
         "source_license": "publicdomain", "start_s": 0, "duration_s": 5},
    ))
    assert personas.clip_for("k") is None


def test_persistence_roundtrip_and_corrupt(state_isolation):
    personas.set_active("jev")
    assert personas.active() == "jev"
    with open(config.PERSONA_FILE, "w") as f:
        f.write("{ not json")
    assert personas.active() == "jev"
    with pytest.raises(KeyError):
        personas.set_active("ghost")


def test_slice_resample_math():
    sr = 48000
    t = np.arange(sr * 2) / sr
    data = (np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    out = personas._slice_resample(data, sr, 1.0, 1.0)
    assert len(out) == personas.TARGET_SR  # 1 s @ 24 kHz from the 1-2 s window
```

## Testing Approach

### Unit Tests (all offline)
1. Catalog screening: non-permissive curated entry fails construction (10.4)
2. Resolution: unknown → None (9.3); bundled persona never downloads (10.1)
3. Fetch-once: first call downloads (fixture bytes via patched client) and stores; second call is cache-only — HTTP client patched to raise on the second call (10.2, 10.3)
4. License mismatch at fetch time → `None` (10.4 second screen, 10.5 shape)
5. Slice/resample: 48 kHz stereo input → correct-length 24 kHz mono output (design math)
6. Persistence: round-trip, corrupt file → bundled default, unknown name rejected (9.6)

### Integration Tests
Persona end-to-end through the turn handler lands in Task 4.2.

## Acceptance Criteria

- [ ] Catalog entries carry name/description/reader/source/license/trim and are screened at construction; bundled persona never downloads
- [ ] `clip_for` fetches once per persona, stores one 24 kHz mono wav, and serves only from cache afterwards (offline reuse)
- [ ] License is screened twice: catalog construction + item-metadata re-check before download; mismatch → unavailable
- [ ] Active persona persists atomically and survives corrupt/missing state
- [ ] Unknown persona resolves to `None`; roster returns active flag per entry
- [ ] All requirements covered: 9.3, 9.4, 9.6, 10.1, 10.2, 10.3, 10.4

## Notes

- `(P)` justification: only files touched are `personas.py` + its tests; 2.1/2.2 own `tts.py`/`brain.py`; the only coupling is the `active_clip()` consumption which Task 3.1 wires — this module ships that contract (bundled persona already returns the same path `active_clip()` resolves).
- Decode note: `soundfile` reads mp3 from a BytesIO buffer when libsndfile ≥ 1.2 (verified as a Task 1.4 step); if mp3 decode proves unavailable in a venv, prefer cataloging ogg/vorbis sources (libsndfile-native) over adding ffmpeg.
- Cache staleness: persona clips are content-stable per catalog entry; re-curation of a persona = new name or a manual cache clear — documented behavior, not handled logic.
- `clip_for` prints (not raises) on unavailability — the caller (Task 3.1) speaks the "kept your voice" line; the print is the console trace.
- State file naming follows the timers pattern; the platform layers set the path overrides in Task 3.2 (defaults under `shared/` work for tests today).
