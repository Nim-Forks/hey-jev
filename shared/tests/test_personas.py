import json

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
        personas.catalog()


def test_resolve_unknown_and_bundled():
    assert personas.resolve("nope") is None
    assert personas.resolve("JEV") == "jev"
    assert personas.clip_for("jev") == config.DEFAULT_VOICE_CLIP


def test_clip_for_fetches_once_then_cache_only(monkeypatch, state_isolation, synthetic_clip):
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
    assert p1 == p2 and calls["n"] == 2  # metadata + file: once. Second call: cache only
    d, s = sf.read(p1)
    assert s == personas.TARGET_SR and d.ndim == 1


def test_license_mismatch_is_unavailable(monkeypatch, state_isolation):
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


def test_real_catalog_is_screened():
    # the shipped entries must pass the screen (kara + kilmer curated in task 2.4)
    names = [p["name"] for p in personas.catalog()]
    assert names == ["jev", "kara", "kilmer"]
    assert personas.resolve("kara") == "kara" and personas.resolve("kilmer") == "kilmer"


# ------------------------------------------------------------------ integration
# persona voice flows through the TTS seam (task 3.1) — offline via fake engine

@pytest.fixture
def fake_engine(monkeypatch):
    from shared import tts as tts_mod
    from test_tts_local import FakeModel
    FakeModel.CALLS.clear()
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts_mod, "_MODELS", {"nano": FakeModel()})
    return tts_mod


def _stub_sources(monkeypatch, synthetic_clip, licenseurl="http://creativecommons.org/licenses/publicdomain/"):
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


def test_switch_renders_new_voice_and_persists(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    from shared import brain
    calls = _stub_sources(monkeypatch, synthetic_clip)
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    path_jev, _, _ = fake_engine.render("hello there")
    line = brain.persona_reply(("switch", "kara"))
    assert "kara" in line and personas.active() == "kara"
    path_kara, _, cached = fake_engine.render("persona confirmation")
    assert path_kara != path_jev and cached is False
    before = calls["n"]
    assert fake_engine.active_clip() == personas.clip_for("kara")
    assert calls["n"] == before                      # clip resolution: cache-only


def test_switch_back_instant_from_cache(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    from shared import brain
    calls = _stub_sources(monkeypatch, synthetic_clip)
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    fake_engine.render("greeting line")
    brain.persona_reply(("switch", "kara"))
    brain.persona_reply(("switch", "jev"))
    n = calls["n"]
    path, ms, cached = fake_engine.render("greeting line")
    assert cached is True and ms == 0 and calls["n"] == n


def test_fetch_failure_keeps_old_voice(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    from shared import brain
    _stub_sources(monkeypatch, synthetic_clip, licenseurl="https://creativecommons.org/licenses/by-nc/4.0/")
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    old = fake_engine.voice_identity()
    line = brain.persona_reply(("switch", "kara"))
    assert "couldn't fetch" in line and personas.active() == "jev"
    assert fake_engine.voice_identity() == old


def test_operator_override_beats_persona(monkeypatch, state_isolation, synthetic_clip, fake_engine):
    from shared import brain
    _stub_sources(monkeypatch, synthetic_clip)
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    monkeypatch.setattr(config, "TTS_REF_CLIP", config.DEFAULT_VOICE_CLIP)
    brain.persona_reply(("switch", "kara"))
    assert personas.active() == "kara"
    assert fake_engine.active_clip() == config.DEFAULT_VOICE_CLIP
