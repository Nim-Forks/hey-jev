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


def _activate_local(monkeypatch):
    from test_tts_local import FakeModel
    FakeModel.CALLS.clear()
    played = []
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(config, "play_wav_hook", lambda p: played.append(p))
    monkeypatch.setattr(tts, "_MODELS", {"nano": FakeModel()})

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
    assert len(posts) == 1
    url, headers, body, timeout = posts[0][1], posts[0][2], posts[0][3], posts[0][4]
    assert url == FISH_URL
    assert headers["Authorization"] == f"Bearer {config.FISH_KEY}"
    assert headers["model"] == "s2.1-pro-free"
    assert body == {"text": "hello [chuckling] there", "reference_id": config.VOICE_ID, "format": "wav"}
    assert timeout == 60 and cached is False and ms >= 0
    path2, ms2, cached2 = tts.render("hello [chuckling] there")
    assert (path2, ms2, cached2) == (path, 0, True)
    assert len([c for c in capture if c[0] == "post"]) == 1


def test_say_path_local(monkeypatch, state_isolation):
    played = _activate_local(monkeypatch)
    ms = brain.speak("hello there")
    assert len(played) == 1 and played[0].endswith(".wav")
    assert ms >= 0


def test_say_path_cloud(monkeypatch, state_isolation):
    capture = []
    _activate_fish(monkeypatch, capture)
    brain.speak("hello there")
    assert len([c for c in capture if c[0] == "play"]) == 1


def test_warm_cache_fish_idempotent(monkeypatch, state_isolation):
    monkeypatch.setattr(config, "APPS", {"spotify": {"name": "Spotify"}}, raising=False)
    capture = []
    _activate_fish(monkeypatch, capture)
    lines = list(brain.all_scripted_lines())
    assert lines and all("{" not in ln for ln in lines)
    brain.warm_cache()
    n_first = len([c for c in capture if c[0] == "post"])
    assert n_first >= len(lines)
    brain.warm_cache()
    assert len([c for c in capture if c[0] == "post"]) == n_first  # second pass: all cached


def test_warm_cache_local_offline(monkeypatch, state_isolation):
    monkeypatch.setattr(config, "APPS", {"spotify": {"name": "Spotify"}}, raising=False)
    played = _activate_local(monkeypatch)
    brain.warm_cache()
    brain.warm_cache()          # second pass: all cached; HTTP patched to raise throughout
    assert len(played) == 0     # warm cache renders, never plays


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
