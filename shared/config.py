"""Platform-neutral configuration + decision backends for hey-jev.

INVARIANT: every value that remote_server or tests may override per turn
(TS_KEY, FISH_KEY, OR_KEY, KEV_URL, KEV_KEY, USE_KEV, LLM_MODEL) lives as a
module attribute here and must be read as `config.X` — never bound with
`from shared.config import X` (from-imports freeze the value and the patch
stops working). Platform layers set the hooks (machine_context_hook,
play_wav_hook, stt_spec_hook) and path overrides (TIMERS_FILE, CACHE_DIR)
right after importing this module.
"""
import os
import re

import requests
from dotenv import load_dotenv

from shared.secrets_store import get_secret

load_dotenv()

TS_KEY = get_secret("TYPESAFE_API_KEY")
FISH_KEY = get_secret("FISH_AUDIO_API_KEY")
OR_KEY = get_secret("OPENROUTER_API_KEY")
# KEV: a self-hosted Jev-compatible decision backend. If both vars are set,
# decisions go to KEV instead of the Typesafe cloud (same wire contract).
KEV_URL = os.getenv("KEV_URL", "").strip().rstrip("/")
KEV_KEY = os.getenv("KEV_API_KEY", "").strip()
USE_KEV = bool(KEV_URL and KEV_KEY)
VOICE_ID = "9a9cf47702da476aa4629e2506d4a857"
SAMPLE_RATE = 16000
# Confidence gate. KEV deployments answer correctly but run hot — the gate
# drops to 0.45 when KEV is active. Override with JEV_GATE.
GATE = float(os.getenv("JEV_GATE", "0.45" if USE_KEV else "0.65"))
COMMAND_PROMPT = "Open Spotify. Set a timer for five minutes. Play. Pause. Next track. Turn Spotify down. Turn the volume down. Mute. Dark mode on. Lock the screen."
WAKE_PROMPT = "Hey Jev, open Spotify. Hey Jev, pause the music. Hey Jev, turn the volume down."
WAKE = re.compile(r"^\W*(?:hey|hi|hay|okay|ok|a)\W+(?:jev|jevs|jeff|jeffs|jef|jeb|jab|chev|jeve|jav)\b\W*", re.I)
WAKE_WINDOW = 6.0
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13")
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-haiku-4.5")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "300"))
NTFY_URL = os.getenv("NTFY_URL", "").strip()
ALERT_MESSAGE = os.getenv("ALERT_MESSAGE", "").strip()
SERVER_KEY_LIMIT = int(os.getenv("SERVER_KEY_LIMIT", "10"))
# paths (platform layer overrides both to its own folder)
TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
# persona storage (platform layer overrides both to its own folder)
PERSONAS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "personas")
PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")

# TTS backend switch. "fish" = cloud API (current behavior, default).
# "chatterbox" = local open-source engine (optional install, English-only).
TTS_BACKENDS = ("fish", "chatterbox")
TTS_BACKEND = os.getenv("TTS_BACKEND", "fish").strip().lower()
TTS_REF_CLIP = os.getenv("TTS_REF_CLIP", "").strip() or None  # None -> persona/bundled clip
TTS_CHATTERBOX_VARIANT = os.getenv("TTS_CHATTERBOX_VARIANT", "nano").strip().lower()
# Bundled default voice (public domain; swap by overwriting the file or setting TTS_REF_CLIP).
DEFAULT_VOICE_CLIP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                  "assets", "voice-default.wav")

# STT spec, shared-resolved (doc/02-risks-invariants.md #8). Previously referenced
# by remote_server + platforms but defined only in the legacy mac layer.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small.en")


def _parse_languages(raw):
    return {p.strip() for p in raw.replace(";", ",").split(",") if p.strip()}


WHISPER_LANGUAGES = _parse_languages(os.getenv("WHISPER_LANGUAGES", "en"))

# hooks the platform layer must wire (see doc/01-migration-plan.md)
machine_context_hook = None   # () -> str
play_wav_hook = None          # (path) -> None
stt_spec_hook = None          # () -> (model_name, language)


def reload_keys():
    global TS_KEY, FISH_KEY, OR_KEY, KEV_URL, KEV_KEY, USE_KEV
    TS_KEY = get_secret("TYPESAFE_API_KEY")
    FISH_KEY = get_secret("FISH_AUDIO_API_KEY")
    OR_KEY = get_secret("OPENROUTER_API_KEY")
    KEV_URL = os.getenv("KEV_URL", "").strip().rstrip("/")
    KEV_KEY = os.getenv("KEV_API_KEY", "").strip()
    USE_KEV = bool(KEV_URL and KEV_KEY)


# Decision backend priority: KEV > Typesafe > OpenRouter-Jev.
def decision_backend():
    """(url, key, model, name) for the active decision backend, or None."""
    if USE_KEV:
        return f"{KEV_URL}/v1/systemone", KEV_KEY, "jev-latest", "kev"
    if TS_KEY:
        return "https://api.typesafe.ai/v1/systemone", TS_KEY, "jev-latest", "typesafe"
    if OR_KEY:
        return "https://openrouter.ai/api/alpha/decisions", OR_KEY, JEV_MODEL, "openrouter"
    return None


def jev(text, questions):
    """One decision call. Returns (answers{name: (value, conf)}, ms, cost).
    `questions` must be provided by the caller (brain passes QUESTIONS /
    SPLIT_QUESTIONS; tests pass minimal sets)."""
    import time
    t = time.time()
    backend = decision_backend()
    if backend is None:
        raise RuntimeError("no decision backend: set TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
    url, key, model, name = backend
    r = requests.post(url, json={"model": model, "state": text, "questions": questions},
                      headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    ans = {}
    for k, a in j["answers"].items():
        if a["type"] == "noul":  # probability, confidence is distance from 0.5
            ans[k] = (a["noul"] >= 0.5, max(a["noul"], 1 - a["noul"]))
        elif a["type"] == "score":  # index into the rubric, legend maps it back to the label
            ans[k] = (a["legend"][str(int(round(a["score"])))], a.get("confidence", 0))
        else:
            ans[k] = (a["choice"], a.get("confidence", 0))
    usage = j.get("usage", {})
    cost = usage.get("cost") or usage.get("input_tokens", 0) * 0.042 / 1e6
    print(f"  backend: {name} ({model})")
    return ans, int((time.time() - t) * 1000), cost
