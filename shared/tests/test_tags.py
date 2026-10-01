import pytest

from shared import config, tts


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")


def test_known_tags_map(local):
    assert tts.map_tags("[chuckling] hi") == "[chuckle] hi"
    assert tts.map_tags("[laughing] [sighing] [clear throat]") == "[laugh] [sigh] [cough]"


def test_unknown_tags_stripped(local):
    assert tts.map_tags("[cheerful] hi [shrug]") == " hi "
    assert "[" not in tts.map_tags("[whatever] ok")


def test_tag_free_untouched(local):
    assert tts.map_tags("plain text") == "plain text"


def test_cloud_passthrough(monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "fish")
    assert tts.map_tags("[chuckling] hi [cheerful]") == "[chuckling] hi [cheerful]"


def test_tag_case_and_spaces(local):
    assert tts.map_tags("[Clear Throat]") == "[cough]"
    assert "[" not in tts.map_tags("[ Happy ]")
