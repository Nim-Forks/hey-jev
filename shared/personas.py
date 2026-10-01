"""Persona catalog + automatic voice-clip sourcing.

INVARIANT: reads mutable settings as `config.X` at call time. Clips are
fetched ONLY from curated catalog entries whose license is public domain /
CC0 — never from user-supplied URLs. The bundled persona never downloads.
"""
import io
import json
import os
import re

import numpy as np
import requests

from shared import config

TARGET_SR = 24000
_PERMISSIVE = ("publicdomain", "cc0")  # substring match, lowercase
_ITEM_RE = re.compile(r"archive\.org/download/([^/]+)/", re.I)
_MAX_SOURCE_BYTES = 20 * 1024 * 1024

_PERSONAS = (
    {"name": "jev", "description": "the default Jev voice", "reader": "Elizabeth Klett",
     "source_url": None, "source_license": "publicdomain", "start_s": 0.0, "duration_s": 0.0},
    {"name": "kara", "description": "a warm storytelling voice", "reader": "Kara Shallenberg",
     "source_url": "https://archive.org/download/poems_every_child_should_know_librivox/poems_every_child_31_burt_64kb.mp3",
     "source_license": "publicdomain", "start_s": 60.0, "duration_s": 25.0},
    {"name": "kilmer", "description": "a calm, deep narrator", "reader": "Phil Chenevert",
     "source_url": "https://archive.org/download/treesandotherpoems_pc_librivox/treesandotherpoems_1_kilmer_64kb.mp3",
     "source_license": "publicdomain", "start_s": 25.0, "duration_s": 25.0},
)


def _license_ok(license_str: str) -> bool:
    s = (license_str or "").lower()
    return any(p in s for p in _PERMISSIVE)


def _item_from_url(url: str):
    m = _ITEM_RE.search(url or "")
    return m.group(1) if m else None


def catalog():
    """The validated persona entries (construction-time license screen)."""
    for p in _PERSONAS:
        if p["source_url"] is not None and not _license_ok(p["source_license"]):
            raise RuntimeError(f"persona {p['name']}: license not permissive: {p['source_license']}")
    return _PERSONAS


def resolve(name: str):
    n = (name or "").strip().lower()
    for p in catalog():
        if p["name"] == n:
            return p["name"]
    return None


def list_personas() -> list:
    cur = active()
    return [{"name": p["name"], "description": p["description"], "active": p["name"] == cur}
            for p in catalog()]


def _state_path():
    return config.PERSONA_FILE


def active() -> str:
    try:
        return json.load(open(_state_path())).get("persona") or "jev"
    except Exception:
        return "jev"


def set_active(name: str):
    canon = resolve(name)
    if canon is None:
        raise KeyError(name)
    tmp = _state_path() + ".tmp"
    json.dump({"persona": canon}, open(tmp, "w"))
    os.replace(tmp, _state_path())


def _cached_path(name: str) -> str:
    return os.path.join(config.PERSONAS_CACHE_DIR, f"{name}.wav")


def _slice_resample(data, sr, start_s: float, dur_s: float):
    if data.ndim > 1:
        data = data.mean(axis=1)
    a = int(start_s * sr)
    seg = data[a: a + int(dur_s * sr)]
    if len(seg) < sr // 2:
        raise ValueError("clip slice too short")
    n_out = int(len(seg) * TARGET_SR / sr)
    return np.interp(np.linspace(0, len(seg) - 1, n_out), np.arange(len(seg)), seg).astype(np.float32)


def _licenseurl_from_item(item: str):
    r = requests.get(f"https://archive.org/metadata/{item}", timeout=30)
    r.raise_for_status()
    return (r.json().get("metadata") or {}).get("licenseurl", "")


def _download_and_store(p: dict, dest: str):
    import soundfile as sf
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    item = _item_from_url(p["source_url"])
    if not item or not _license_ok(_licenseurl_from_item(item)):
        raise ValueError("license check failed")
    r = requests.get(p["source_url"], timeout=60)
    r.raise_for_status()
    if len(r.content) > _MAX_SOURCE_BYTES:
        raise ValueError("source file too large")
    data, sr = sf.read(io.BytesIO(r.content), dtype="float32", always_2d=False)
    audio = _slice_resample(data, sr, p["start_s"], p["duration_s"])
    sf.write(dest, audio, TARGET_SR, subtype="PCM_16")


def clip_for(name: str):
    canon = resolve(name)
    if canon is None:
        return None
    p = next(x for x in catalog() if x["name"] == canon)
    if p["source_url"] is None:            # bundled persona: no fetch, ever
        return config.DEFAULT_VOICE_CLIP
    dest = _cached_path(canon)
    if os.path.isfile(dest):               # cache hit: no network
        return dest
    try:
        _download_and_store(p, dest)
    except Exception as e:
        print(f"  persona {canon}: clip unavailable: {e}")
        return None                        # caller keeps the current voice
    return dest
