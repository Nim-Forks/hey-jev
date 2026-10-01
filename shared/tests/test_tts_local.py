import pytest

from shared import config, tts


class FakeModel:
    sr = 24000
    CALLS = []  # (text, audio_prompt_path) per generate call

    def generate(self, text, audio_prompt_path):
        FakeModel.CALLS.append((text, audio_prompt_path))
        import numpy as np
        return np.zeros((1, 24000), dtype=np.float32)


@pytest.fixture
def fake_engine(monkeypatch):
    FakeModel.CALLS.clear()
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_MODELS", {"nano": FakeModel()})
    return tts


def test_render_writes_cache(fake_engine, state_isolation):
    path, ms, cached = fake_engine.render("hello [chuckling] world")
    assert FakeModel.CALLS and FakeModel.CALLS[0][0] == "hello [chuckle] world"  # mapped text
    assert cached is False and ms >= 0 and path.endswith(".wav")
    import soundfile as sf
    data, sr = sf.read(path)
    assert sr == 24000 and data.ndim == 1


def test_render_second_call_is_cached(fake_engine, state_isolation):
    fake_engine.render("hello")
    path, ms, cached = fake_engine.render("hello")
    assert cached is True and ms == 0


def test_no_http_on_render(fake_engine, state_isolation, monkeypatch):
    import requests

    def boom(*a, **k):
        raise AssertionError("render performed an HTTP call")
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setattr(requests, "get", boom)
    fake_engine.render("offline please")


def test_failure_envelope(fake_engine, state_isolation, monkeypatch):
    class Bad:
        sr = 24000

        def generate(self, *a, **k):
            raise RuntimeError("oom")

    monkeypatch.setattr(tts, "_MODELS", {"nano": Bad()})
    with pytest.raises(tts.TTSRenderError, match="oom"):
        fake_engine.render("hi")
    assert config.TTS_BACKEND == "chatterbox"  # backend selection untouched


def test_engine_missing_message(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_MODELS", {})
    import sys as _sys
    # block the package AND the submodule: a cached chatterbox.tts_turbo would
    # otherwise satisfy the from-import without touching the parent
    monkeypatch.setitem(_sys.modules, "chatterbox", None)
    monkeypatch.setitem(_sys.modules, "chatterbox.tts_turbo", None)
    with pytest.raises(tts.TTSRenderError, match="requirements-tts-local"):
        tts.render("hi")


@pytest.mark.slow
@pytest.mark.network
def test_real_model_render(state_isolation, monkeypatch):
    pytest.importorskip("chatterbox")
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    path, ms, cached = tts.render("Jev here, all systems nominal.")
    import soundfile as sf
    data, sr = sf.read(path)
    assert sr == 24000 and len(data) > sr


def test_rtf_math():
    from measure_rtf import rtf_ratio, verdict
    assert rtf_ratio(500, 1.0) == 0.5
    assert verdict([0.5, 1.5]) == {"mean": 1.0, "max": 1.5, "pass": False}
    assert verdict([0.9, 0.8])["pass"] is True
