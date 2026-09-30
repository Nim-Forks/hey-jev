# Task 2.2 — Local render engine (Chatterbox) behind the same seam

**Spec**: tts-alternatives
**Branch**: `feature-alternatives`
**Status**: draft

---

## Task Overview

**Objective**: Fill the local-backend slot in the TTS module: lazily load the Chatterbox model (singleton keyed by the variant setting, CPU), render mapped text with the active voice clip, write the wav through the shared cache-key formula, and keep failures inside the render-error envelope — never a fallback, never speech text on the network.

**Dependencies**: Task 2.1 (dispatch slot, tag map, cache key, clip resolution), Task 1.4 (optional install; only needed to run the real-model test).

**Boundary**: `tts` component only (`shared/tts.py`); brain/platform unchanged.

**Requirements**: 1.2, 6.1, 6.2, 6.3, 7.1, 8.2

## Implementation Steps

### Step 1: Lazy model singleton
- [ ] Implement a loader keyed by the variant setting (module-level dict, one instance max), importing the engine **inside** the loader so the base install never pays the import cost.
- [ ] Load on CPU; Nano is the default variant. Verify the Nano entry point against the installed package first (inspect the `chatterbox` module for the Nano class or flag — the vendor README only demonstrates the Turbo loader `ChatterboxTurboTTS.from_pretrained(device=...)`); if Nano's loading API differs from the Turbo call shape, adapt and record the exact working call in this file's Notes. If Nano is unusable in the installed release, run Turbo and flag the deviation.
- [ ] Weights come from the engine's own local cache after the first load; first-ever load may download weights (engine installation — distinct from the speech-traffic boundary: spoken text and rendered audio never leave the machine).
- **Observable**: with the optional set installed, the first local render loads the model once (subsequent renders reuse it — assertable via the singleton key).

### Step 2: Render with the active clip through the shared cache
- [ ] On render: cache-hit check first (shared cache-path helper); on miss, generate the mapped text with `audio_prompt_path` set to the active clip, write the wav (tensor → numpy → soundfile, 24 kHz, mono, PCM_16) into the cache path, return `(path, ms, False)`.
- [ ] Keep the generate call shape from the vendor example (text + audio prompt); pass no other controls in this task (defaults).
- **Observable**: a local-backend `--text` turn produces the wav in the reply cache and the trace prints `tts chatterbot`-style backend + cached/ms lines (Task 2.1's line already handles the trace).

### Step 3: Failure envelope and no-network guard
- [ ] Wrap load + generate in the render-error type with the original message preserved (model load failure, OOM, bad output); the backend setting must never change on failure.
- [ ] The generate path must not import or call any HTTP client; add a unit-level guard asserting the module never performs an HTTP call during render (see tests).
- **Observable**: a forced generate failure surfaces as a reported error with the session usable and the backend still `"chatterbox"`.

### Step 4: Real-model check (slow, optional to run here)
- [ ] Add a `@pytest.mark.slow @pytest.mark.network` test that renders one short line with the real model into the isolated cache and asserts a readable 24 kHz mono wav — skipped cleanly when the optional set is missing (same skip shape as Task 4.1 uses).
- **Observable**: the test passes on a machine with the optional install and weights cached; skipped with a clear message otherwise.

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `shared/tts.py` | Modify | Replace the chatterbox stub with loader + render |
| `shared/tests/test_tts_local.py` | Create | Fake-model unit tests + offline guard + slow real-model test |

### File: `shared/tts.py`

**Current Code** (the Task 2.1 stub):

```python
def _render_chatterbox(text: str):
    raise TTSRenderError("chatterbox backend not implemented (task 2.2)")
```

**Expected Code After Implementation** (stub replaced; loader added; imports extended):

```python
_MODELS = {}  # variant -> loaded model instance (singleton per variant)


def _ensure_model():
    """Load the local engine once per variant. Imports inside so the base
    install never pays the cost. CPU only."""
    variant = config.TTS_CHATTERBOX_VARIANT
    if variant not in _MODELS:
        try:
            from chatterbox.tts_turbo import ChatterboxTurboTTS
        except ImportError as e:
            raise TTSRenderError(
                "local TTS engine not installed; see shared/requirements-tts-local.txt") from e
        # NOTE: verify the Nano entry point against the installed package; the
        # vendor README demonstrates only the Turbo loader. Adapt if it differs.
        _MODELS[variant] = ChatterboxTurboTTS.from_pretrained(device="cpu")
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
        sf.write(path, wav.squeeze(0).detach().cpu().numpy(), model.sr,
                 subtype="PCM_16")
    except TTSRenderError:
        raise
    except Exception as e:
        raise TTSRenderError(f"local render failed: {e}") from e
    return path, int((time.time() - t) * 1000), False
```

### File: `shared/tests/test_tts_local.py`

**Current Code**: none.

**Expected Code** (essentials):

```python
import pytest

from shared import config, tts


class FakeModel:
    sr = 24000

    def generate(self, text, audio_prompt_path):
        assert "[" not in text or text.startswith("[chuckle]")  # mapped text arrives
        assert audio_prompt_path  # active clip is passed
        import numpy as np
        return np.zeros((1, 24000), dtype=np.float32)


@pytest.fixture
def fake_engine(monkeypatch):
    monkeypatch.setattr(config, "TTS_BACKEND", "chatterbox")
    monkeypatch.setattr(tts, "_MODELS", {"nano": FakeModel()})
    return tts


def test_render_writes_cache(fake_engine, state_isolation):
    path, ms, cached = tts.render("hello [chuckling] world")
    assert cached is False and ms >= 0 and path.endswith(".wav")
    import os
    import soundfile as sf
    data, sr = sf.read(path)
    assert sr == 24000 and data.ndim == 1


def test_render_second_call_is_cached(fake_engine, state_isolation):
    tts.render("hello")
    path, ms, cached = tts.render("hello")
    assert cached is True and ms == 0


def test_no_http_on_render(fake_engine, state_isolation, monkeypatch):
    import requests
    def boom(*a, **k):
        raise AssertionError("render performed an HTTP call")
    monkeypatch.setattr(requests, "post", boom)
    monkeypatch.setattr(requests, "get", boom)
    tts.render("offline please")


def test_failure_envelope(fake_engine, state_isolation, monkeypatch):
    class Bad:
        sr = 24000
        def generate(self, *a, **k):
            raise RuntimeError("oom")
    monkeypatch.setattr(tts, "_MODELS", {"nano": Bad()})
    with pytest.raises(tts.TTSRenderError, match="oom"):
        tts.render("hi")
    assert config.TTS_BACKEND == "chatterbox"  # backend selection untouched


@pytest.mark.slow
@pytest.mark.network
def test_real_model_render(state_isolation):
    pytest.importorskip("chatterbox")
    path, ms, cached = tts.render("Jev here, all systems nominal.")
    import soundfile as sf
    data, sr = sf.read(path)
    assert sr == 24000 and len(data) > sr
```

## Testing Approach

### Unit Tests (offline, fake model)
1. Render writes a readable 24 kHz mono wav into the isolated cache
2. Second identical render is a cache hit `(path, 0, True)`
3. No HTTP call occurs during render (requests patched to raise)
4. Generate failure → `TTSRenderError` with original message; backend setting unchanged
5. Mapped text and the active clip path are what the engine receives

### Slow / Network Tests
- Real Nano/Turbo render behind `@pytest.mark.slow @pytest.mark.network`, `importorskip` guard, runs only with the optional install.

### Integration Tests
Full-flow behavior (turn-level, warm cache, both backends) lands in Task 4.1.

## Acceptance Criteria

- [ ] Local render works through the same seam: mapped text + active clip → cached wav; cached lines return instantly
- [ ] Model loads lazily once per variant on CPU; base installs never import the engine
- [ ] The local path performs no HTTP I/O (unit-enforced); first-ever weight download is the only network event and carries no speech text
- [ ] All failures raise the render error with the original cause; backend selection never changes; the session survives
- [ ] Slow real-model test passes with the optional install; skipped cleanly without it
- [ ] All requirements covered: 1.2, 6.1, 6.2, 6.3, 7.1, 8.2

## Notes

- Nano entry point must be verified against the installed package before wiring `nano=True`-style options — the PyPI README (verified today) demonstrates only `ChatterboxTurboTTS.from_pretrained(device=...)`. If Nano needs a different call, keep the Turbo line working and record the exact Nano call here.
- Requirement 8.2 (slow first render still plays) is satisfied structurally: render happens synchronously inside the turn's Speaking state, then plays; no drop path exists. The E2E gate (Task 4.4) observes it.
- Per-turn patching: `TTS_CHATTERBOX_VARIANT` is read inside the loader at call time; tests swap `_MODELS` wholesale rather than reloading weights.
- Output format: 24 kHz PCM_16 mono matches the bundled clip and the persona cache; the engine's native sample rate (`model.sr`) governs the write — assert 24 kHz only if that is the engine's rate (verify at implementation; adjust the test constant if Turbo/Nano expose a different `sr`).
