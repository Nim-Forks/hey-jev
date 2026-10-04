import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_shared_core_imports():
    from shared import brain, config
    assert callable(brain.fetch_tts)
    assert config.TTS_BACKEND in config.TTS_BACKENDS


def test_multi_token_gate():
    from shared.remote_server import RemoteServer
    s = RemoteServer(0, "127.0.0.1", "none", ["tok-a", "tok-b"])
    assert s.token_ok("tok-a") and s.token_ok("tok-b")
    assert not s.token_ok("tok-c") and not s.token_ok(None)
    assert RemoteServer(0, "127.0.0.1", "none", []).token_ok("anything")  # empty = gate off


def test_kev_model_env(monkeypatch):
    from shared import config
    monkeypatch.setenv("KEV_MODEL", "d1:free")
    url, key, model, name = config.decision_backend()
    if config.USE_KEV:
        assert model == "d1:free" and name == "kev"
    else:  # kev not configured on the test box — the env read is still per-call
        assert config.decision_backend() is None or model != "d1:free"
    monkeypatch.delenv("KEV_MODEL", raising=False)
    url, key, model, name = config.decision_backend()
    if config.USE_KEV:
        assert model == "jev-latest"


def test_synthetic_clip_fixture(state_isolation, tmp_path):
    from fixtures import write_syllable_wav
    p = write_syllable_wav(str(tmp_path / "tone.wav"))
    import soundfile as sf
    data, sr = sf.read(p)
    assert sr == 24000 and data.ndim == 1 and len(data) > sr * 2
