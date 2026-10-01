"""TTS backends behind the brain.fetch_tts seam.

INVARIANT: reads every mutable setting as `config.X` at call time (the remote
server and tests patch config per turn). The cloud path is byte-identical to
the pre-feature implementation; the local path performs no network I/O for
speech and never falls back to the cloud backend on failure.
"""
import hashlib
import os
import re
import time

import requests

from shared import config


class TTSRenderError(RuntimeError):
    """Raised when a line cannot be rendered; callers report it, backends never swap."""


_TAG_RE = re.compile(r"\[([^\]\r\n]+)\]")
FISH_TO_CHATTERBOX = {
    "chuckling": "chuckle",
    "laughing": "laugh",
    "sighing": "sigh",
    "clear throat": "cough",
    # "cheerful" and anything unknown: stripped (no local equivalent)
}


def map_tags(text: str) -> str:
    """Cloud backend speaks Fish tags natively (pass-through). Local backend:
    known tags translated, unknown stripped — a tag is never spoken aloud."""
    if config.TTS_BACKEND != "chatterbox":
        return text

    def repl(m):
        tag = m.group(1).strip().lower()
        mapped = FISH_TO_CHATTERBOX.get(tag)
        return f"[{mapped}]" if mapped else ""

    return _TAG_RE.sub(repl, text)


def active_clip() -> str:
    """Absolute clip path defining the local voice: an operator-configured clip
    wins; otherwise the active persona's clip (the bundled persona resolves to
    the bundled default). Missing clips fail, naming persona or file."""
    from shared import personas  # local import: no cycle at module load
    clip = config.TTS_REF_CLIP or personas.clip_for(personas.active())
    if not clip or not os.path.isfile(clip):
        who = personas.active() if not config.TTS_REF_CLIP else config.TTS_REF_CLIP
        raise TTSRenderError(f"voice reference clip not available for {who!r}: {clip}")
    return clip


_CLIP_HASHES = {}  # (path, mtime) -> sha256[:16]; refreshed when a clip is overwritten


def voice_identity() -> str:
    """Stable voice token for the cache key: cloud voice id, or clip content hash."""
    if config.TTS_BACKEND != "chatterbox":
        return config.VOICE_ID
    path = active_clip()
    key = (path, os.path.getmtime(path))
    h = _CLIP_HASHES.get(key)
    if h is None:
        h = hashlib.sha256(open(path, "rb").read()).hexdigest()[:16]
        _CLIP_HASHES.clear()  # keep only the active voice's hash
        _CLIP_HASHES[key] = h
    return h


def _cache_path(mapped_text: str) -> str:
    key = hashlib.sha1(f"{config.TTS_BACKEND}|{voice_identity()}|{mapped_text}".encode()).hexdigest()
    return os.path.join(config.CACHE_DIR, key + ".wav")


def _render_fish(text: str):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = _cache_path(text)  # map_tags is identity for the cloud backend
    if os.path.exists(path):
        return path, 0, True
    t = time.time()
    r = requests.post("https://api.fish.audio/v1/tts",
                      headers={"Authorization": f"Bearer {config.FISH_KEY}", "model": "s2.1-pro-free"},
                      json={"text": text, "reference_id": config.VOICE_ID, "format": "wav"}, timeout=60)
    r.raise_for_status()
    open(path, "wb").write(r.content)
    return path, int((time.time() - t) * 1000), False


_MODELS = {}  # variant -> loaded model instance (singleton per variant)


def _ensure_model():
    """Load the local engine once per variant. Imports inside so the base
    install never pays the cost. CPU only."""
    variant = config.TTS_CHATTERBOX_VARIANT
    if variant not in _MODELS:
        os.environ.setdefault("TQDM_DISABLE", "1")  # no per-render progress bars in server logs
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
        except ImportError as e:
            raise TTSRenderError(
                "local TTS engine not installed; see shared/requirements-tts-local.txt") from e
        # NOTE: verified Nano entry point — 0.1.7 exposes no nano flag or class;
        # from_pretrained(device) loads Turbo (350M). The variant setting stays
        # for future releases; both variants currently map to this loader.
        m = ChatterboxTurboTTS.from_pretrained(device="cpu")
        tok = getattr(getattr(m, "s3gen", None), "tokenizer", None)
        if tok is not None:
            # CPU dtype fix (chatterbox 0.1.7 + torch 2.6+cpu): the S3
            # conditioning path feeds a float64 numpy wav into log_mel while
            # the mel bank is float32 -> "expected scalar type Double but
            # found Float". log_mel_spectrogram is the choke point for every
            # caller, so cast its audio to float32 there.
            import numpy as np

            orig_mel = tok.log_mel_spectrogram

            def _mel_f32(audio, padding=0):
                import torch
                if isinstance(audio, torch.Tensor):
                    audio = audio.float()
                elif isinstance(audio, np.ndarray):
                    audio = torch.from_numpy(audio.astype(np.float32, copy=False))
                return orig_mel(audio, padding)

            tok.log_mel_spectrogram = _mel_f32
        # pyloudnorm's loudness normalization returns float64, which then leaks
        # into every conditioning consumer; force float32 at the source.
        nl = getattr(m, "norm_loudness", None)
        if nl is not None:
            def _norm_f32(wav, sr):
                return np.asarray(nl(wav, sr), dtype=np.float32)
            m.norm_loudness = _norm_f32
        _MODELS[variant] = m
    return _MODELS[variant]


def _render_chatterbox(text: str):
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    path = _cache_path(text)
    if os.path.exists(path):
        return path, 0, True
    import numpy as np
    import soundfile as sf
    t = time.time()
    try:
        model = _ensure_model()
        wav = model.generate(text, audio_prompt_path=active_clip())
        audio = wav.detach().cpu().numpy() if hasattr(wav, "detach") else np.asarray(wav)
        sf.write(path, audio.reshape(-1) if audio.ndim > 1 else audio, model.sr, subtype="PCM_16")
    except TTSRenderError:
        raise
    except Exception as e:
        raise TTSRenderError(f"local render failed: {e}") from e
    return path, int((time.time() - t) * 1000), False


def render(text: str):
    """brain.fetch_tts seam: -> (wav_path, render_ms, cached)."""
    backend = config.TTS_BACKEND
    mapped = map_tags(text)
    if backend == "fish":
        return _render_fish(mapped)
    if backend == "chatterbox":
        return _render_chatterbox(mapped)
    raise TTSRenderError(
        f"unknown TTS backend {backend!r}; valid: {', '.join(config.TTS_BACKENDS)}")


def _engine_importable() -> bool:
    try:
        import chatterbox  # noqa: F401  (probe only; the real load stays lazy)
        return True
    except ImportError:
        return False


def validate_startup() -> list:
    """Blocking TTS problems for the current settings; empty list = ready.
    Platform entry points print each problem and exit before the mic opens."""
    problems = []
    backend = config.TTS_BACKEND
    if backend not in config.TTS_BACKENDS:
        problems.append(f"unknown TTS_BACKEND {backend!r}; "
                        f"valid: {', '.join(config.TTS_BACKENDS)} (set TTS_BACKEND in .env)")
        return problems
    if backend != "chatterbox":
        return problems
    if not _engine_importable():
        problems.append("TTS_BACKEND=chatterbox but the local engine is not installed; "
                        "run: pip install -r shared/requirements-tts-local.txt (Python >= 3.13)")
    non_en = config.WHISPER_LANGUAGES - {"en"}
    if non_en:
        problems.append(f"TTS_BACKEND=chatterbox supports English replies only; configured "
                        f"languages {sorted(non_en)} need the cloud backend "
                        "(unset WHISPER_LANGUAGES or set TTS_BACKEND=fish)")
    if config.TTS_REF_CLIP:
        if not os.path.isfile(config.TTS_REF_CLIP):
            problems.append(f"TTS_REF_CLIP not found: {config.TTS_REF_CLIP}")
    elif not os.path.isfile(config.DEFAULT_VOICE_CLIP):
        problems.append(f"bundled voice clip missing: {config.DEFAULT_VOICE_CLIP} "
                        "(reinstall or set TTS_REF_CLIP)")
    return problems
