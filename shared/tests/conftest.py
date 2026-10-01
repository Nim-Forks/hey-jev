import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from shared import brain, config  # noqa: E402  (repo root on sys.path)


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long-running tests (local model loads)")
    config.addinivalue_line("markers", "network: tests that touch the network")


@pytest.fixture
def synthetic_clip(tmp_path):
    from fixtures import write_syllable_wav
    return write_syllable_wav(str(tmp_path / "synthetic.wav"))


@pytest.fixture(autouse=True)
def state_isolation(tmp_path, monkeypatch):
    """Point every feature-owned state location at the per-test tmp dir."""
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "PERSONAS_CACHE_DIR", str(tmp_path / "personas"))
    monkeypatch.setattr(config, "PERSONA_FILE", str(tmp_path / "persona.json"))
    monkeypatch.setattr(config, "TTS_REF_CLIP", None)  # bundled default unless a test sets one
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    os.makedirs(config.PERSONAS_CACHE_DIR, exist_ok=True)
