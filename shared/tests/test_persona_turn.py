import pytest

from shared import brain, config, personas, tts


def base_ans(**over):
    a = {"category": ("chit_chat", 0.9), "compound": (False, 0.9), "target": ("none", 0.2),
         "weather_action": ("none", 0.9), "info_skill": ("none", 0.9),
         "memory_action": ("none", 0.9), "persona_action": ("none", 0.2),
         "persona_name": ("none", 0.2)}
    a.update(over)
    return a


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


def _two_catalog():
    return (
        {"name": "jev", "description": "d", "reader": "r", "source_url": None,
         "source_license": "publicdomain", "start_s": 0, "duration_s": 0},
        {"name": "kara", "description": "d", "reader": "r",
         "source_url": "https://archive.org/download/i/f_64kb.mp3",
         "source_license": "publicdomain", "start_s": 0.5, "duration_s": 2.0},
    )


@pytest.fixture
def turn(monkeypatch):
    from test_tts_local import FakeModel
    states, played = [], []

    def go(text, backend="chatterbox"):
        monkeypatch.setattr(config, "TTS_BACKEND", backend)        # local voice, fake engine
        monkeypatch.setattr(config, "play_wav_hook", lambda p: played.append(p))
        monkeypatch.setattr(brain, "emit", lambda n, s, d="": states.append((s, d)))
        monkeypatch.setattr(tts, "_MODELS", {"nano": FakeModel()})
        monkeypatch.setattr(config, "jev", lambda t, q: (base_ans(persona_action=("switch", 0.9),
                                                                  persona_name=(t.split()[-1] if t.split()[-1] in ("kara", "kilmer", "jev", "bogus") else "none",
                                                                  0.9 if t.split()[-1] in ("kara", "kilmer", "jev", "bogus") else 0.3)), 5, 0.0))
        brain.handle(text)
        return states, played
    return go


def test_switch_turn_confirmation_in_new_voice(monkeypatch, state_isolation, synthetic_clip, turn):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    calls = _stub_http(monkeypatch, synthetic_clip)
    states, played = turn("switch persona to kara")
    assert any(s == "Speaking" for s, _ in states)                       # 9.5: activity states
    spoken = [d for s, d in states if s == "Speaking"]
    assert any("kara" in d for d in spoken)
    assert personas.active() == "kara"                                   # 9.1 persisted
    identity = tts.voice_identity()                                      # kara's clip hash active
    import hashlib
    want = hashlib.sha256(open(tts.active_clip(), "rb").read()).hexdigest()[:16]
    assert identity == want                                              # 9.2: new voice drives the key
    assert calls["n"] == 2                                               # metadata + file, once
    assert len(played) == 1


def test_unknown_persona_turn_keeps_voice(monkeypatch, state_isolation, synthetic_clip, turn):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    _stub_http(monkeypatch, synthetic_clip)
    states, played = turn("switch persona to bogus")
    assert personas.active() == "jev"
    spoken = [d for s, d in states if s == "Speaking"]
    assert any("kara" in d for d in spoken)                              # 9.3: roster named


def test_roster_turn(monkeypatch, state_isolation, synthetic_clip, turn):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    _stub_http(monkeypatch, synthetic_clip)
    states, played = turn("what personas are there")
    spoken = [d for s, d in states if s == "Speaking"]
    assert any("jev" in d and "kara" in d for d in spoken)               # 9.4
    assert personas.active() == "jev"


def test_cloud_refusal_turn(monkeypatch, state_isolation, synthetic_clip, turn):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    _stub_http(monkeypatch, synthetic_clip)

    def fake_post(url, headers=None, json=None, timeout=None):   # fish render stub (refusal line)
        class R:
            content = open(synthetic_clip, "rb").read()
            status_code = 200
            def raise_for_status(self): pass
        return R()
    monkeypatch.setattr(tts.requests, "post", fake_post)
    states, played = turn("switch persona to kara", backend="fish")
    assert personas.active() == "jev"                                    # 9.7
    spoken = [d for s, d in states if s == "Speaking"]
    assert any("local" in d for d in spoken)


def test_fetch_failure_turn_keeps_old_voice(monkeypatch, state_isolation, synthetic_clip, turn):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    _stub_http(monkeypatch, synthetic_clip, licenseurl="https://creativecommons.org/licenses/by-nc/4.0/")
    states, played = turn("switch persona to kara")
    old = hashlib_identity(state_isolation)
    assert personas.active() == "jev"                                    # 10.5
    assert tts.voice_identity() == old
    assert len(played) == 1 and played[0].endswith(".wav")


def test_offline_reuse_after_restart(monkeypatch, state_isolation, synthetic_clip, turn):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    calls = _stub_http(monkeypatch, synthetic_clip)
    turn("switch persona to kara")
    assert calls["n"] == 2

    def dead_get(url, timeout=0, **k):
        raise AssertionError("network used after first fetch")
    monkeypatch.setattr(personas.requests, "get", dead_get)
    states, played = turn("what personas are there")                     # offline roster
    assert personas.clip_for("kara") == tts.active_clip()                # 10.2/10.3/10.6
    assert played and played[-1].endswith(".wav")                        # roster still spoken


def hashlib_identity(state_isolation):
    import hashlib
    return hashlib.sha256(open(tts.active_clip(), "rb").read()).hexdigest()[:16]
