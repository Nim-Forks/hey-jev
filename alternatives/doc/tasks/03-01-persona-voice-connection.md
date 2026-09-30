# Task 3.1 — Integration: connect persona switching to the speaking voice

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Close the loop: the TTS layer must resolve its voice from the active persona (operator override still wins), so a successful switch is heard in the new persona's voice immediately, a failed fetch keeps the old voice, switch-backs are instant from cache, and the persona survives restarts — all through the existing cache-key mechanics, with no new state.

**Dependencies**: Tasks 2.2 (local engine), 2.3 (personas), 2.5 (routing/branch). Explicit integration task: touches the seam between `tts` and `personas`.

**Boundary**: `tts` component (one function) + cross-component integration tests (`personas` + `tts` + the routing helper, offline via fake engine and stubbed HTTP). `brain.py` and `personas.py` logic unchanged.

**Requirements**: 3.1, 4.2, 9.1, 9.2, 10.1, 10.2, 10.5, 10.6

## Implementation Steps

### Step 1: Persona-driven clip resolution in the TTS layer
- [ ] Change `active_clip()` resolution to: a configured reference clip (operator override) wins; otherwise the active persona's clip from the persona module — which for the bundled persona is exactly the bundled default path, so behavior without any switch is unchanged.
- [ ] An unresolvable clip (persona clip vanished mid-session) raises the render error naming the persona/clip — the existing error envelope handles it.
- **Observable**: with no switch, `active_clip()` still returns the bundled default; after `set_active("kara")`, it returns Kara's cached clip.

### Step 2: Cache mechanics do the rest (verify, don't add)
- [ ] Confirm by test: voice identity is the clip content hash, so switching personas changes only that persona's cache keys — the previous persona's lines remain cached and play instantly on switch-back.
- [ ] Confirm the confirmation line itself renders with the new voice: the switch branch (Task 2.5) persists the persona before speaking, and the persona clip is already cached by the availability check, so the confirmation is a cache-resident render — no extra calls.
- **Observable**: cache-key set for persona A's voice is disjoint from persona B's; switching back to A re-serves A's cached lines with no re-render.

### Step 3: Integration tests (offline: fake engine + stubbed HTTP)
- [ ] Full switch flow through the routing helper with a fake engine: switch → confirmation wav renders with the new persona's clip → state file records it → a second call (simulated restart: fresh personas state read) keeps the persona.
- [ ] Fetch failure: license mismatch → unavailable reply renders with the OLD persona's voice (assert via cache key/identity), persona unchanged.
- [ ] Operator override: configured clip set → persona switch persists but the voice identity (cache key) stays the operator's clip.
- [ ] Switch-back: cached lines of the previous persona replay without any network call (HTTP client patched to raise).
- **Observable**: the offline integration suite proves requirements 9.1, 9.2, 10.1, 10.2, 10.5, 10.6 end to end without network or model weights.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tts.py` | Modify | `active_clip()` resolves the active persona's clip (operator override first) |
| `shared/tests/test_personas.py` | Modify | Cross-component integration section (routing helper + fake engine + stubbed HTTP) |

### File: `shared/tts.py`

**Current Code** (Task 2.1):

```python
def active_clip() -> str:
    """Absolute clip path defining the local voice: configured clip, else the
    bundled default. A configured-but-missing clip fails, naming the file."""
    clip = config.TTS_REF_CLIP or config.DEFAULT_VOICE_CLIP
    if not os.path.isfile(clip):
        raise TTSRenderError(f"voice reference clip not found: {clip}")
    return clip
```

**Expected Code After Implementation**:

```python
def active_clip() -> str:
    """Absolute clip path defining the local voice: an operator-configured clip
    wins; otherwise the active persona's clip (the bundled persona resolves to
    the bundled default). Missing clips fail, naming persona or file."""
    from shared import personas  # local import: no cycle at module load
    clip = config.TTS_REF_CLIP or personas.clip_for(personas.active())
    if not clip or not os.path.isfile(clip):
        who = personas.active() if not config.TTS_REF_CLIP else config.TTS_REF_CLIP
        raise TTSRenderError(f"voice reference clip not available for {who!r}: {clip}")
    return clip
```

(Startup validation already covers the bundled/configured file presence — Task 2.6; this runtime check only guards the vanish-mid-session case.)

### File: `shared/tests/test_personas.py`

**Current Code**: the Task 2.3 suite + Task 2.4's slow network tests.

**Expected Code After Implementation** (appended integration section; reuses `FakeModel` shape from Task 2.2's suite):

```python
@pytest.fixture
def fake_engine(monkeypatch):
    import tts as tts_mod
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts_mod, "_MODELS", {"nano": FakeModel()})
    return tts_mod


def _stub_persona_sources(monkeypatch, synthetic_clip, licenseurl="http://creativecommons.org/licenses/publicdomain/"):
    data = {"calls": 0}
    def fake_get(url, timeout=0, **k):
        data["calls"] += 1
        class R:
            content = open(synthetic_clip, "rb").read()
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"metadata": {"licenseurl": licenseurl}}
        return R()
    monkeypatch.setattr(personas.requests, "get", fake_get)
    return data


def test_switch_confirmation_renders_in_new_voice(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    import tts as tts_mod
    counts = _stub_persona_sources(monkeypatch, synthetic_clip)
    monkeypatch.setattr(personas, "_PERSONAS", (
        {"name": "jev", "description": "d", "reader": "r", "source_url": None,
         "source_license": "publicdomain", "start_s": 0, "duration_s": 0},
        {"name": "kara", "description": "d", "reader": "r",
         "source_url": "https://archive.org/download/i/f_64kb.mp3",
         "source_license": "publicdomain", "start_s": 0.5, "duration_s": 2.0},
    ))
    path_jev, _, _ = tts_mod.render("hello there")
    line = brain._persona_reply(("switch", "kara"))          # routing helper from task 2.5
    assert "kara" in line and personas.active() == "kara"
    path_kara, _, cached = tts_mod.render("persona switched to kara")
    assert path_kara != path_jev and cached is False          # new voice = new key, fresh render
    assert os.path.dirname(path_kara) == config.CACHE_DIR
    # restart: state file read gives kara again; clip resolves from cache with no new download
    before = counts["calls"]
    assert personas.active() == "kara" and tts_mod.active_clip() == personas.clip_for("kara")
    assert counts["calls"] == before                          # 10.2/10.6: cache-only


def test_switch_back_is_instant_from_cache(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    _stub_persona_sources(monkeypatch, synthetic_clip)
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())  # jev + kara as above
    tts.render("greeting line")
    brain._persona_reply(("switch", "kara")); brain._persona_reply(("switch", "jev"))
    before = _http_call_count(monkeypatch)
    path, ms, cached = tts.render("greeting line")            # jev voice line again
    assert cached is True and ms == 0                          # 4.2: instant switch-back


def test_fetch_failure_keeps_old_voice(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    _stub_persona_sources(monkeypatch, synthetic_clip, licenseurl="https://creativecommons.org/licenses/by-nc/4.0/")
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    old_identity = tts.voice_identity()
    line = brain._persona_reply(("switch", "kara"))
    assert "couldn't fetch" in line and personas.active() == "jev"
    assert tts.voice_identity() == old_identity                # 10.5: voice unchanged


def test_operator_override_beats_persona(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    _stub_persona_sources(monkeypatch, synthetic_clip)
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    monkeypatch.setattr(config, "TTS_REF_CLIP", config.DEFAULT_VOICE_CLIP)
    brain._persona_reply(("switch", "kara"))
    assert personas.active() == "kara"                          # persisted…
    assert tts.active_clip() == config.DEFAULT_VOICE_CLIP       # …but voice is the override
```

(`_two_persona_catalog()` is a small shared test helper building the jev+kara catalog; the fake-engine and `_persona_reply` shapes come from Tasks 2.2/2.5 — final helper placement settled at implementation to avoid duplication.)

## Testing Approach

### Integration Tests (offline)
1. Switch flow: routing helper → persisted persona → confirmation rendered with the new clip; restart simulation keeps persona; clip lookup cache-only (9.1, 9.2, 9.6, 10.1, 10.2, 10.6)
2. Switch-back: previous persona's cached lines replay with zero re-render and zero network (4.2, 10.3)
3. Fetch failure: unavailable wording in the OLD voice; persona state untouched (10.5)
4. Operator override: persona persists; voice stays the configured clip (boundary behavior, documented)

### Slow / Network Tests
None here — real-model/real-fetch coverage lives in Tasks 2.2/2.4/4.1.

## Acceptance Criteria

- [ ] After a successful switch, the confirmation plays in the new persona's voice; the state file records it; restart keeps speaking with that persona
- [ ] A failed persona fetch keeps the current voice and says so; nothing else in the turn changes
- [ ] Switch-backs replay the previous persona's cached lines instantly (no re-render, no network)
- [ ] A configured operator clip still overrides persona voices (documented); persona persistence still occurs
- [ ] No product-code changes beyond the one resolution function; brain/personas logic untouched
- [ ] All requirements covered: 3.1, 4.2, 9.1, 9.2, 10.1, 10.2, 10.5, 10.6

## Notes

- This is the only place `tts` consumes `personas` — one function, local import, no cycle (`personas` never imports `tts`).
- The mtime-keyed clip-hash cache in `voice_identity()` makes switch invalidation automatic: different persona → different path → different hash → only that voice's keys change. No invalidation code exists or is needed.
- Operator-override semantics are now part of the spec: `TTS_REF_CLIP` set means "always this voice"; persona switching still persists (roster/refusal logic unchanged) and takes effect if the override is later removed. Documented here; the platform docs (Task 3.2's README pointers) carry the user-facing note.
- Warm-cache interplay: scripted lines pre-render for the voice active at startup; lines for other personas render on demand and then cache — by design (pre-rendering every persona would triple the cache for lines nobody hears).
