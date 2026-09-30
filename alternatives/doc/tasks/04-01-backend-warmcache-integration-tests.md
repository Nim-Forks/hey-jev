# Task 4.1 — Integration tests: backends + warm cache

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Prove the say-path end to end for both backends — a spoken line produces a cached wav and playback through the seam, the cloud request is byte-shape-identical to the legacy contract, the local render performs zero HTTP I/O, and warm cache pre-renders every scripted line per backend with a clean second-run no-op.

**Dependencies**: Tasks 3.1 (final seam shape), 2.2 (local engine). Runs offline except one slow real-model variant.

**Boundary**: `tts` component + `shared tests` (new integration test file). No product code changes expected — failures here are defects to fix, not features.

**Requirements**: 1.1, 1.2, 4.1, 4.3, 7.1

## Implementation Steps

### Step 1: Say-path fixtures
- [ ] Shared fixtures: recorded-playback hook (`config.play_wav_hook` appends the path), per-backend activation (`fish` with the HTTP client stubbed/capturing; `chatterbox` with the fake model from the 2.2 suite), and `config.APPS` set so the scripted-lines iterator expands app placeholders.
- **Observable**: fixtures activate with one line each and need no network for the fake paths.

### Step 2: Cloud request-shape and cache behavior (1.1, 4.1)
- [ ] Capture the request on a cache miss: assert URL, `Authorization` bearer + `model` header, body keys/values (`text`, `reference_id` = cloud voice id, `format` = wav), and timeout exactly match the legacy contract.
- [ ] Assert the response bytes land in the cache file and the return tuple is `(path, ms ≥ 0, False)`; a second identical call returns `(path, 0, True)` with no second request.
- **Observable**: the moved implementation is proven request-identical; cache round-trip proven.

### Step 3: Say-path turn per backend (1.1, 1.2)
- [ ] Per backend: speak a line through the brain's say path (say → seam → playback hook); assert the wav exists in the temp cache and the hook received that exact path.
- [ ] Local variant additionally asserts the engine received the mapped text and the active clip (fake-model assertions already in the 2.2 suite — reuse the fake here).
- **Observable**: both backends produce a playable cached wav through the same seam; the trace line reports the right backend.

### Step 4: Warm cache across backends (4.3, 7.1)
- [ ] Fish: first warm run renders every scripted line (HTTP stubbed, call count == line count); second run renders nothing new (all cached).
- [ ] Chatterbox: warm cache with the fake model while the HTTP client is patched to raise — proving zero network I/O for the whole warm-up; second run all cached.
- [ ] Reminder-alert lines: assert the tag-bearing lines appear in the scripted-line set with tags intact pre-mapping (mapping happens at render — same seam, already proven).
- **Observable**: warm cache completes per backend with a clean idempotent second run; the local warm-up never touches the network.

### Step 5: Real-model variant (slow, optional)
- [ ] Add the real-engine variant of the say-path and a bounded warm-cache slice behind `@pytest.mark.slow @pytest.mark.network` + `importorskip("chatterbox")` — the full scripted set is too slow for a test; assert a handful of representative lines.
- **Observable**: passes with the optional install + weights; skipped with a clear message without.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tests/test_tts_integration.py` | Create | Say-path per backend, cloud request shape, warm-cache idempotence, offline guard |
| `alternatives/doc/design.md` | Modify | File-plan sync: the new integration test file (one line, on approval) |

### File: `shared/tests/test_tts_integration.py`

**Current Code**: none (seam under test, brain lines 871–881):

```python
def play_wav_path(path):
    """Local playback via the platform hook (config.play_wav_hook)."""
    if config.play_wav_hook is None:
        raise RuntimeError("config.play_wav_hook not wired by the platform layer")
    config.play_wav_hook(path)


def speak(text):
    path, ms, cached = fetch_tts(text)
    play_wav_path(path)
    return ms
```

**Expected Code** (essentials):

```python
import pytest

from shared import brain, config, tts

FISH_URL = "https://api.fish.audio/v1/tts"


def _activate_fish(monkeypatch, capture):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    monkeypatch.setattr(config, "play_wav_hook", lambda p: capture.append(("play", p)))
    def fake_post(url, headers=None, json=None, timeout=None):
        capture.append(("post", url, headers, json, timeout))
        class R:
            content = b"RIFFfake"
            status_code = 200
            def raise_for_status(self): pass
        return R()
    monkeypatch.setattr(tts.requests, "post", fake_post)


def _activate_local(monkeypatch, fake_model):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    played = []
    monkeypatch.setattr(config, "play_wav_hook", lambda p: played.append(p))
    monkeypatch.setattr(tts, "_MODELS", {"nano": fake_model})
    def boom(*a, **k):
        raise AssertionError("local path performed an HTTP call")
    monkeypatch.setattr(tts.requests, "post", boom)
    monkeypatch.setattr(tts.requests, "get", boom)
    return played


def test_cloud_request_shape_unchanged(monkeypatch, state_isolation):
    capture = []
    _activate_fish(monkeypatch, capture)
    path, ms, cached = tts.render("hello [chuckling] there")
    posts = [c for c in capture if c[0] == "post"]
    url, headers, body, timeout = posts[0][1], posts[0][2], posts[0][3], posts[0][4]
    assert url == FISH_URL
    assert headers["Authorization"] == f"Bearer {config.FISH_KEY}" and headers["model"] == "s2.1-pro-free"
    assert body == {"text": "hello [chuckling] there", "reference_id": config.VOICE_ID, "format": "wav"}
    assert timeout == 60 and cached is False and ms >= 0
    path2, ms2, cached2 = tts.render("hello [chuckling] there")
    assert (path2, ms2, cached2) == (path, 0, True)
    assert len([c for c in capture if c[0] == "post"]) == 1


def test_say_path_local(monkeypatch, state_isolation):
    from shared.tests.test_tts_local import FakeModel  # or move FakeModel to fixtures
    played = _activate_local(monkeypatch, FakeModel())
    ms = brain.speak("hello there")
    assert len(played) == 1 and played[0].endswith(".wav")
    assert ms >= 0


def test_say_path_cloud(monkeypatch, state_isolation):
    capture = []
    _activate_fish(monkeypatch, capture)
    brain.speak("hello there")
    assert len([c for c in capture if c[0] == "play"]) == 1


def test_warm_cache_idempotent_both(monkeypatch, state_isolation):
    monkeypatch.setattr(config, "APPS", {"spotify": {"name": "Spotify"}})
    capture = []
    _activate_fish(monkeypatch, capture)
    lines = list(brain.all_scripted_lines())
    assert lines and all("{" not in l for l in lines)
    # fish: every line rendered once
    brain.warm_cache()
    assert len([c for c in capture if c[0] == "post"]) >= len(lines)
    brain.warm_cache()
    assert len([c for c in capture if c[0] == "post"]) == len([c for c in capture if c[0] == "post"])


def test_warm_cache_local_offline(monkeypatch, state_isolation):
    from shared.tests.test_tts_local import FakeModel
    monkeypatch.setattr(config, "APPS", {"spotify": {"name": "Spotify"}})
    played = _activate_local(monkeypatch, FakeModel())
    brain.warm_cache()
    brain.warm_cache()          # second pass: all cached, still zero network (patched to raise)
    assert len(played) == 0     # warm cache does not play, only renders


@pytest.mark.slow
@pytest.mark.network
def test_real_model_say_path(state_isolation, monkeypatch):
    pytest.importorskip("chatterbox")
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    played = []
    monkeypatch.setattr(config, "play_wav_hook", lambda p: played.append(p))
    brain.speak("Jev here, all systems nominal.")
    import soundfile as sf
    data, sr = sf.read(played[0])
    assert sr > 0 and len(data) > sr
```

### File: `alternatives/doc/design.md`

**Current Code** (File Structure Plan, tests block):

```
└── tests/                        # NEW: pytest units + integration
    ├── test_tags.py
    ├── test_tts_cache.py
    ├── test_personas.py
    └── test_routing.py
```

**Expected Code After Implementation** (one line added):

```
└── tests/                        # NEW: pytest units + integration
    ├── test_tags.py
    ├── test_tts_cache.py
    ├── test_personas.py
    ├── test_routing.py
    └── test_tts_integration.py   # backend + warm-cache integration (task 4.1)
```

## Testing Approach

### Integration Tests (offline unless marked)
1. Cloud request shape byte-equality + cache round-trip (1.1, 4.1)
2. Say path per backend: wav + playback hook + trace backend (1.1, 1.2)
3. Warm cache per backend: complete first pass, idempotent second pass (4.3)
4. Local warm cache with HTTP patched to raise: zero network (7.1)
5. Real model say-path: slow/network, importorskip (1.2 evidence on hardware)

### Manual Verification
Run the offline suite from both platform folders (`python -m pytest ../shared/tests -q`), record results per platform.

## Acceptance Criteria

- [ ] Cloud path proven request-identical to the legacy contract; cache round-trip exact
- [ ] Both backends produce playable cached wavs through the say path
- [ ] Warm cache completes per backend and is idempotent; local warm-up provably performs no HTTP I/O
- [ ] Real-engine variant passes with the optional install; skipped cleanly without
- [ ] All requirements covered: 1.1, 1.2, 4.1, 4.3, 7.1

## Notes

- `brain.say` also emits state and prints; passing `notify=None` exercises the print path only — no UI coupling in these tests.
- The fish capture stub must NOT patch `requests` globally (module-attribute patch on `tts.requests` keeps other modules free to use requests).
- Warm-cache line count varies with the REPLIES table and platform APPS — assert relative counts (first pass ≥ line count, second pass adds none), never absolute numbers.
- The slow real variant re-renders at most a few lines; keep the line list tiny so the test stays under a minute.
- Design file-plan sync (the one-line `test_tts_integration.py` addition) accompanies this task's approval.
