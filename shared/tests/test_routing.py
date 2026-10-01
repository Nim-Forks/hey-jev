import pytest

from shared import brain, config, personas


def base_ans(**over):
    a = {"category": ("chit_chat", 0.9), "compound": (False, 0.9), "target": ("none", 0.2),
         "app": ("none", 0.2), "app_action": ("none", 0.2),
         "volume_action": ("none", 0.2), "display_action": ("none", 0.2),
         "media_action": ("none", 0.2), "system_action": ("none", 0.2),
         "timer_action": ("none", 0.2),
         "weather_action": ("none", 0.9), "info_skill": ("none", 0.9),
         "memory_action": ("none", 0.9), "persona_action": ("none", 0.2),
         "persona_name": ("none", 0.2)}
    a.update(over)
    return a


def test_regex_wins_over_noisy_jev():
    kind, payload = brain.decide(base_ans(), "hey jev, switch persona to Kilmer")
    assert (kind, payload) == ("persona", ("switch", "kilmer"))


def test_jev_fallback_switch_with_name():
    ans = base_ans(persona_action=("switch", 0.9), persona_name=("kara", 0.9))
    assert brain.decide(ans, "i'd like a different voice") == ("persona", ("switch", "kara"))


def test_jev_switch_without_confident_name_is_unknown():
    ans = base_ans(persona_action=("switch", 0.9), persona_name=("none", 0.3))
    assert brain.decide(ans, "give me another voice") == ("persona", ("switch", None))


def test_list_phrasing():
    assert brain.decide(base_ans(), "what personas are there?") == ("persona", ("list", None))


def test_persona_questions_excluded_from_split():
    assert "first_persona_action" not in brain.SPLIT_QUESTIONS
    assert "second_persona_name" not in brain.SPLIT_QUESTIONS


def _timer_ans(**over):
    a = base_ans(category=("pc_command", 0.24), compound=(False, 0.64),
                 target=("timer", 0.72), timer_action=("set", 0.46))
    a.update(over)
    return a


def test_garbled_verb_still_sets_timer():
    kind, payload = brain.decide(_timer_ans(), "alwrt me in one minute")
    assert kind == "actions" and payload[0][1] == "timer_set"


def test_clean_phrase_below_subgate_still_sets():
    ans = _timer_ans(target=("timer", 0.69), timer_action=("set", 0.61))
    assert brain.decide(ans, "alert me in one minute")[1][0][1] == "timer_set"


def test_verbless_garble_uses_structure():
    assert brain.decide(_timer_ans(), "alwrp me in 1 minute")[1][0][1] == "timer_set"


def test_timer_negative_not_hijacked():
    ans = _timer_ans(target=("timer", 0.7), timer_action=("set", 0.3))
    kind, payload = brain.decide(ans, "don't remind me to call sam")
    assert (kind, payload) != ("actions", [(0.9, "timer_set", None, "timer_set", {"level": None})])


def test_alarm_phrasing_left_to_jev():
    assert brain.timer_override("wake me at seven") is None
    ans = _timer_ans(target=("timer", 0.9), timer_action=("set", 0.9))
    kind, payload = brain.decide(ans, "wake me at seven")
    assert kind == "actions" and payload[0][1] == "timer_set"


def test_no_structural_hijack_of_weather():
    ans = base_ans(category=("information_request", 0.9), target=("none", 0.2),
                   weather_action=("fetch", 0.9))
    assert brain.decide(ans, "what's the weather in london?") == ("weather", None)


def _stub_sources(monkeypatch, synthetic_clip=None, licenseurl="http://creativecommons.org/licenses/publicdomain/"):
    def fake_get(url, timeout=0, **k):
        class R:
            content = open(synthetic_clip, "rb").read() if (synthetic_clip and "metadata" not in url) else b""
            status_code = 200
            def raise_for_status(self): pass
            def json(self): return {"metadata": {"licenseurl": licenseurl}}
        return R()
    monkeypatch.setattr(personas.requests, "get", fake_get)


@pytest.fixture
def local_backend(monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")


def _two_catalog():
    return (
        {"name": "jev", "description": "d", "reader": "r", "source_url": None,
         "source_license": "publicdomain", "start_s": 0, "duration_s": 0},
        {"name": "kara", "description": "d", "reader": "r",
         "source_url": "https://archive.org/download/i/f_64kb.mp3",
         "source_license": "publicdomain", "start_s": 0.5, "duration_s": 2.0},
    )


def test_unknown_switch_keeps_voice_and_lists(state_isolation, local_backend):
    line = brain.persona_reply(("switch", "bogus"))
    assert "kara" in line and "kilmer" in line
    assert personas.active() == "jev"          # voice untouched


def test_cloud_backend_refuses(state_isolation, monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    line = brain.persona_reply(("switch", "kara"))
    assert "local" in line
    assert personas.active() == "jev"


def test_switch_persists(state_isolation, monkeypatch, local_backend, synthetic_clip):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    _stub_sources(monkeypatch, synthetic_clip)
    line = brain.persona_reply(("switch", "kara"))
    assert "kara" in line
    assert personas.active() == "kara"          # voice swap rides tts.active_clip (3.1)


def test_roster_lists_active(state_isolation, monkeypatch, local_backend, synthetic_clip):
    monkeypatch.setattr(personas, "_PERSONAS", _two_catalog())
    _stub_sources(monkeypatch, synthetic_clip)
    brain.persona_reply(("switch", "kara"))
    line = brain.persona_reply(("list", None))
    assert "kara" in line and "Right now" in line
