import pytest

from shared import config, tts


def test_clip_resolution_bundled(state_isolation):
    import os
    assert tts.active_clip() == config.DEFAULT_VOICE_CLIP
    assert os.path.isfile(tts.active_clip())


def test_clip_resolution_missing_configured_fails(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_REF_CLIP", "/no/such/clip.wav")
    with pytest.raises(tts.TTSRenderError, match="/no/such/clip.wav"):
        tts.active_clip()


def test_unknown_backend_raises(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "piper")
    with pytest.raises(tts.TTSRenderError, match="piper"):
        tts.render("hi")


def test_cache_key_changes_with_backend_and_voice(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    k_fish = tts._cache_path("hi")
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    k_local = tts._cache_path("hi")
    assert k_fish != k_local
    assert tts._cache_path("hi") == k_local  # stable for repeated calls


def test_startup_unknown_backend(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "piper")
    problems = tts.validate_startup()
    assert len(problems) == 1 and "piper" in problems[0] and "chatterbox" in problems[0]


def test_startup_chatterbox_valid(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_engine_importable", lambda: True)
    assert tts.validate_startup() == []


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
    assert any("de" in p and "cloud" in p for p in problems)


def test_startup_configured_clip_missing(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_engine_importable", lambda: True)
    monkeypatch.setattr(config, "TTS_REF_CLIP", "/no/such/clip.wav")
    assert any("/no/such/clip.wav" in p for p in tts.validate_startup())


def test_startup_cloud_backend_skips_clip_checks(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    monkeypatch.setattr(config, "TTS_REF_CLIP", "/no/such/clip.wav")
    assert tts.validate_startup() == []
