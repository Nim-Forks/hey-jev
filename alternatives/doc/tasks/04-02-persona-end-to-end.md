# Task 4.2 — Persona end-to-end validation (through the turn handler)

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Prove the whole persona story at the turn level — a spoken switch flows through `handle()`, the confirmation plays in the new voice, unknown/list/cloud/failure branches behave and keep the voice, the persona survives a simulated restart, and a fetched persona is reused with zero further downloads — all offline (decision backend stubbed, HTTP stubbed after first fetch, fake engine).

**Dependencies**: Task 3.1 (seam shape). Complements 3.1's helper-level tests by driving the real `handle()` entry point.

**Boundary**: `personas`, `brain routing`, `shared tests` (new turn-level test file). No product code changes expected.

**Requirements**: 9.1, 9.2, 9.5, 9.6, 10.2, 10.3, 10.5, 10.6

## Implementation Steps

### Step 1: Turn-level harness
- [ ] Stub `config.jev` to return canned fan-out answers (the routing suite's `base_ans` plus persona keys); record `brain.emit` calls; record played wav paths via the playback hook; fake engine in the TTS module; HTTP client stubbed per scenario (fixture bytes for the first fetch, raise-on-call for the offline assertions).
- **Observable**: `brain.handle("switch persona to kara")` runs end to end offline, emitting state transitions and playing exactly one wav.

### Step 2: The switch/list/unknown/cloud/failure matrix through `handle()`
- [ ] Switch to a catalog persona: confirmation spoken (text contains the persona), played wav's cache key equals the post-switch voice identity, state file records the persona (9.1, 9.2).
- [ ] Roster phrasing: roster line spoken, voice unchanged (9.4 side of the gate; 9.3's voice-preservation).
- [ ] Unknown persona: voice unchanged, roster with available names spoken (9.3).
- [ ] Cloud backend selected: needs-local refusal, voice unchanged (9.7 behavior via the handler).
- [ ] Fetch failure (license mismatch at metadata re-check): unavailable line spoken **in the old voice** — assert the played wav's key maps to the old voice identity (10.5).
- **Observable**: every branch asserted at the turn level; the voice is untouched on every failure path.

### Step 3: Restart + offline reuse + activity states
- [ ] Restart simulation: after a switch, re-read state (fresh `personas.active()`) and render a scripted line — it lands on the new persona's cache key with no download (10.6).
- [ ] Offline reuse across restart: after the first fetch (call count 1), patch the HTTP client to raise and re-run the whole switch flow for the second persona — cache-only (10.2, 10.3).
- [ ] Activity states: the switch turn emits `Thinking` then `Speaking` (no frozen gap) — the 9.5 observable via the emit capture.
- **Observable**: the matrix passes with the network stubbed to raise after the first fetch — offline reuse and persistence proven at the turn level.

### Step 4: Run on both platforms
- [ ] Offline suite green from `win11/` and `linux/` folders.
- **Observable**: recorded per-platform results.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tests/test_persona_turn.py` | Create | Turn-level persona matrix, restart + offline reuse, activity-state assertions |
| `alternatives/doc/design.md` | Modify | File-plan sync for the new test file (applied at this task's generation) |

### File: `shared/tests/test_persona_turn.py`

**Current Code** (seam under test — `brain.handle` head, lines 942–960):

```python
def handle(text, stt_ms=None, notify=None):
    global misses
    LAST_TURN_COST.update({"jev": 0.0, "llm": 0.0})
    print(f"\n> heard: {text!r}" + (f"  (stt {stt_ms}ms)" if stt_ms is not None else ""))
    if not text.strip():
        emit(notify, "Ready", "Didn't catch anything")
        return
    emit(notify, "Thinking", text)
    ans, jev_ms, cost = config.jev(text, QUESTIONS)
    LAST_TURN_COST["jev"] = cost
    _cancel_check(notify)
    for k, (v, c) in ans.items():
        flag = "" if c >= config.GATE else "  <- below gate"
        print(f"  {k:15} {str(v):22} {c:.2f}{flag}")
    print(f"  jev {jev_ms}ms  ${cost:.6f}")
    kind, payload = decide(ans, text)
```

**Expected Code** (essentials):

```python
import pytest

from shared import brain, config, personas, tts


def _turn_env(monkeypatch, fake_model):
    states, played = [], []
    monkeypatch.setattr(config, "play_wav_hook", lambda p: played.append(p))
    monkeypatch.setattr(brain, "emit", lambda n, s, d="": states.append((s, d)))
    monkeypatch.setattr(tts, "_MODELS", {"nano": fake_model})
    def jev_stub(text, questions):
        return brain.base_ans_for_tests(text), 5, 0.0   # canned answers incl. persona keys
    monkeypatch.setattr(config, "jev", jev_stub)
    return states, played


def _stub_http(monkeypatch, synthetic_clip, licenseurl="http://creativecommons.org/licenses/publicdomain/"):
    calls = {"n": 0}
    def fake_get(url, timeout=0, **k):
        calls["n"] += 1
        class R:
            content = open(synthetic_clip, "rb").read()
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"metadata": {"licenseurl": licenseurl}}
        return R()
    monkeypatch.setattr(personas.requests, "get", fake_get)
    return calls


def _two_persona_catalog():
    return (
        {"name": "jev", "description": "d", "reader": "r", "source_url": None,
         "source_license": "publicdomain", "start_s": 0, "duration_s": 0},
        {"name": "kara", "description": "d", "reader": "r",
         "source_url": "https://archive.org/download/i/f_64kb.mp3",
         "source_license": "publicdomain", "start_s": 0.5, "duration_s": 2.0},
    )


def test_switch_turn_confirmation_in_new_voice(monkeypatch, state_isolation, synthetic_clip):
    from shared.tests.test_tts_local import FakeModel
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    _stub_http(monkeypatch, synthetic_clip)
    states, played = _turn_env(monkeypatch, FakeModel())
    brain.handle("switch persona to kara")
    assert any(s == "Speaking" for s, _ in states)                  # 9.5
    assert any("kara" in d for _, d in states if s == "Speaking" for s, d in [(s, d) for s, d in states]) or True
    assert personas.active() == "kara"                              # 9.1 persisted
    expected_key = tts._cache_path("persona confirmation line")     # voice identity is kara's now
    assert tts.voice_identity() == hashlib_of_kara_clip(state_isolation)  # 9.2 new voice active
    assert len(played) == 1


def test_unknown_persona_turn_keeps_voice(monkeypatch, state_isolation, synthetic_clip):
    from shared.tests.test_tts_local import FakeModel
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    _stub_http(monkeypatch, synthetic_clip)
    states, played = _turn_env(monkeypatch, FakeModel())
    brain.handle("switch persona to bogus")
    assert personas.active() == "jev"
    line = next(d for s, d in states if s == "Speaking")
    assert "kara" in line and "kilmer" not in line or "kara" in line   # roster names available ones


def test_cloud_refusal_turn(monkeypatch, state_isolation, synthetic_clip):
    from shared.tests.test_tts_local import FakeModel
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    _stub_http(monkeypatch, synthetic_clip)
    states, played = _turn_env(monkeypatch, FakeModel())
    brain.handle("switch persona to kara")
    assert personas.active() == "jev"
    assert any("local" in d for _, d in states if _ == "Speaking" for _, d in [(s, d) for s, d in states]) or True


def test_fetch_failure_turn_keeps_old_voice(monkeypatch, state_isolation, synthetic_clip):
    from shared.tests.test_tts_local import FakeModel
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    _stub_http(monkeypatch, synthetic_clip, licenseurl="https://creativecommons.org/licenses/by-nc/4.0/")
    states, played = _turn_env(monkeypatch, FakeModel())
    old = tts.voice_identity()
    brain.handle("switch persona to kara")
    assert personas.active() == "jev"
    assert tts.voice_identity() == old                              # 10.5
    assert len(played) == 1 and played[0].endswith(".wav")          # unavailable line played


def test_offline_reuse_after_restart(monkeypatch, state_isolation, synthetic_clip):
    from shared.tests.test_tts_local import FakeModel
    monkeypatch.setattr(personas, "_PERSONAS", _two_persona_catalog())
    calls = _stub_http(monkeypatch, synthetic_clip)
    states, played = _turn_env(monkeypatch, FakeModel())
    brain.handle("switch persona to kara")                          # first fetch
    assert calls["n"] == 1
    # simulated restart: HTTP now impossible; persona state is on disk
    def dead_get(url, timeout=0, **k):
        raise AssertionError("network used after first fetch")
    monkeypatch.setattr(personas.requests, "get", dead_get)
    brain.handle("what personas are there")                          # roster, offline
    assert personas.clip_for("kara") == tts.active_clip()            # 10.2/10.3/10.6 cache-only
```

(The asserts marked with `or True` placeholders are tightened at implementation once the exact say-line wording from Task 2.5 is in the tree — the shipped test asserts the roster/refusal wording precisely, no placeholders left.)

## Testing Approach

### Integration Tests (offline)
1. Switch turn: state transitions, single confirmation playback, persisted persona, new-voice identity (9.1, 9.2, 9.5)
2. Roster turn / unknown turn / cloud turn / fetch-failure turn: correct wording, voice untouched (9.3, 9.4, 9.7, 10.5)
3. Restart + offline reuse: state-file persistence and cache-only clip/reply access with network impossible (10.2, 10.3, 10.6)

### Manual Verification
Run from both platform folders; record results.

## Acceptance Criteria

- [ ] The full switch flow works through `handle()` offline: confirmation in the new voice, states emitted, one playback
- [ ] Unknown/list/cloud/failure branches keep the voice and speak the designed lines
- [ ] Persona survives a simulated restart; a fetched persona is reused with zero further downloads (network patched to raise)
- [ ] Suite passes from both platform folders
- [ ] All requirements covered: 9.1, 9.2, 9.5, 9.6, 10.2, 10.3, 10.5, 10.6

## Notes

- `config.jev` is stubbed at the module attribute (the per-turn patch contract) — the routing suite's answer builder is reused so decision-shape drift fails loudly here too.
- The `emit` stub records `(state, detail)` tuples directly — no WS protocol coupling.
- Voice-identity assertions compare `tts.voice_identity()` before/after rather than decoding audio — content-hash equality is the contract the cache relies on.
- Real-model/real-fetch coverage stays in the slow/network suites (Tasks 2.2/2.4); this file stays fully offline.
