# Research & Design Decisions — TTS backend alternatives (replace Fish Audio)

---
**Purpose**: Capture discovery findings, architectural investigations, and rationale that inform the technical design of an open-source TTS backend for hey-jev.

**Usage**:
- Log research activities and outcomes during the discovery phase.
- Document design decision trade-offs that are too detailed for `design.md`.
- Provide references and evidence for future audits or reuse.

---

## Summary
- **Feature**: `tts-alternatives` — replace the Fish Audio S2.1 Pro cloud TTS with an open-source backend, selectable behind a config switch
- **Discovery Scope**: Extension (new backend behind the existing `fetch_tts` seam; no protocol or cache changes)
- **Key Findings**:
  - The integration surface is tiny: every spoken line funnels through `brain.fetch_tts()` (shared/brain.py:856), which returns a cached wav path keyed by SHA1(voice|text). A backend swap is one function behind a switch; `warm_cache()`, the `cache/tts/` layout, the remote server's wav streaming and the timer/reminder pre-render all keep working unchanged.
  - Emotion tags (`[cheerful] [chuckling] [sighing] [clear throat] [laughing]`) are baked into `REPLIES` (shared/brain.py:179) and the LLM system prompt (shared/brain.py:466). Any replacement must accept or map these tags, or they are spoken literally. This is the main functional gap between Fish and generic OSS TTS.
  - **Chatterbox (Resemble AI, MIT)** is the only verified OSS family that combines inline paralinguistic tags (`[laugh]`, `[chuckle]`, `[cough]`), zero-shot voice cloning from a ~10s reference clip, and a CPU-viable variant (Nano, 110M, 3× realtime on 8 cores). It matches the app's CPU-only constraint and the tag convention with a small mapping layer.
  - **Fish Audio S2 Pro itself is now open-weight** (4B params, `fishaudio/s2-pro` on HuggingFace, same `[tag]` syntax natively) — but it needs GPU serving (SGLang/vLLM) and ships a custom non-OSI "Fish Audio Research License". Right shape for a self-hosted GPU box, wrong shape for the laptop assistant.
  - Fish costs nothing today (`s2.1-pro-free` free until end of November 2026, then $15/M chars ≈ cents/day with the reply cache), so the switch is optionality/privacy engineering, not a cost emergency.

## Research Log

### Current TTS integration contract
- **Context**: Any replacement must fit the existing one-turn flow without touching the brain's routing.
- **Sources Consulted**: `shared/brain.py` (chunks 7–8), `shared/config.py`, `shared/remote_server.py`, `win11/siri.py`, `linux/siri.py`.
- **Findings**:
  - `fetch_tts(text)` → `(path, ms, cached)`; cache key `SHA1(f"{VOICE_ID}|{text}")`, cache dir `config.CACHE_DIR` (platform-overridden). Fish call: `POST https://api.fish.audio/v1/tts`, headers `Authorization` + `model: s2.1-pro-free`, body `{text, reference_id: VOICE_ID, format: "wav"}`.
  - `warm_cache()` iterates every fixed `REPLIES` line (app names and level words expanded) and renders them in a background thread at startup; `{left}`/live-value lines are generated on demand.
  - `brain.say()` → `fetch_tts` → `config.play_wav_hook(path)`; the remote server monkey-patches `brain.say` per turn and streams the wav bytes over WS/HTTP instead.
  - Reminder prep (`prepare_reminder`) pre-renders LLM-written alert lines into the same cache so timer alerts play instantly.
  - `VOICE_ID` is a Fish-hosted voice (config.py:29). Platforms are CPU-only (Whisper small.en int8 already runs locally; playback via sounddevice).
- **Implications**: The backend switch must live as a `config.X` module attribute (per the project invariant: remote_server and tests patch config attrs per turn — never freeze with from-imports). Cache key stays valid if the backend id replaces `VOICE_ID` in the hash input, giving a clean invalidation when switching voices/backends.

### Fish Audio open-source status (verified 2026-09-30)
- **Context**: Check whether the vendor's own model can be self-hosted as an escape hatch.
- **Sources Consulted**: github.com/fishaudio/fish-speech (fetched today), huggingface.co/fishaudio/s2-pro, arXiv 2603.08823.
- **Findings**:
  - S2 Pro: 4B Dual-AR model (slow AR 4B + fast AR 400M over RVQ codec), 10M hours training, 80+ languages, RL (GRPO) aligned. Benchmarks: Seed-TTS WER 0.54% zh / 0.99% en; EmergentTTS win rate 81.88%.
  - Native fine-grained inline control with the same syntax hey-jev already uses — `[chuckling]`, `[sigh]`, `[whisper]`… 15k+ tags including free-form descriptions.
  - Voice cloning from 10–30s reference, no fine-tuning. Streaming via SGLang: RTF 0.195, TTFA ~100 ms on one H200.
  - License: **"Fish Audio Research License"** — custom, not OSI-approved. Serving needs SGLang/vLLM and a GPU; there is no CPU path for a 4B model.
- **Implications**: Ideal if a GPU server is ever in the picture (exact tag compatibility means zero REPLIES rewrites), but it does not satisfy the CPU-only constraint of the win11/linux platform layers, and the license needs legal review before any redistribution.

### Chatterbox family (verified 2026-09-30)
- **Context**: Find an OSS backend that keeps cloned voice + tags on CPU.
- **Sources Consulted**: github.com/resemble-ai/chatterbox (fetched today), huggingface.co/ResembleAI/chatterbox-nano.
- **Findings**:
  - MIT license (code and model family), 26.6k stars, `pip install chatterbox-tts`, Python 3.11 tested.
  - **Turbo (350M, English)**: paralinguistic tags native — `[cough]`, `[laugh]`, `[chuckle]` and more; one-step distilled decoder; built for low-latency voice agents.
  - **Nano (110M, English)**: same architecture, same tags, **3× realtime on 8 CPU cores** — the only tag-capable model found that meets the CPU constraint.
  - **Multilingual V3 (500M, 23+ langs)**: improved speaker similarity, reduced hallucination; cloning via `audio_prompt_path` (10s ref clip); tag support not advertised on the multilingual line. Single Language Pack finetunes for zh/es/pt/hi.
  - Cloning: `model.generate(text, audio_prompt_path="ref.wav")` — the app would ship or point to a reference clip instead of a hosted `VOICE_ID`.
  - Every output is watermarked (PerTh) — imperceptible, acceptable here.
  - Original Chatterbox (500M EN) exposes `exaggeration` / `cfg_weight` controls for expressive speech.
- **Implications**: Drop-in fit: map Fish tags → Chatterbox tags in one function; `VOICE_ID` becomes a reference-clip path/name in the cache key. Constraint: Turbo/Nano are English-only — the `WHISPER_LANGUAGES` multilingual feature would need Multilingual V3 (tag-less) for non-English replies, or Fish stays the default when non-en languages are configured.

### Other OSS candidates (from prior knowledge — licenses to re-verify before design freeze)
- **Context**: Sweep the field so the comparison is complete.
- **Sources Consulted**: prior knowledge of the 2024–2025 OSS TTS landscape; not re-verified today.
- **Findings**:
  - **Kokoro (82M, Apache-2.0)** — very fast on CPU, excellent quality for its size, fixed voice pack, no cloning, no tags.
  - **Piper (MIT)** — fastest CPU option, many languages, no cloning, no expressiveness.
  - **F5-TTS (MIT)** — good zero-shot cloning; no tags; GPU preferred.
  - **XTTS-v2 (Coqui, AGPL-3.0)** — cloning + 17 langs, but the project is dead and CPU latency is poor; AGPL complicates bundling.
  - **OpenAudio S1-mini (fish, 0.5B)** — supports tags, but weights are CC-BY-NC-SA (non-commercial).
  - **StyleTTS2 (MIT), Zonos (Apache, 1.6B, emotion params), Orpheus (3B, `<laugh>` tags), VibeVoice (7B, MIT)** — all GPU-class.
- **Implications**: Nothing else pairs tags + cloning + CPU. Kokoro/Piper are the "speed-only" fallbacks; the rest need a GPU.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Keep Fish (status quo) | `s2.1-pro-free` cloud API | Zero work, best quality, free until Nov 2026 | Vendor lock, network dependency, key management, paid after Nov 2026 | Default until the switch earns its keep |
| **Chatterbox-Nano/Turbo (local)** | MIT; 110M/350M EN; paralinguistic tags; 10s-clip cloning; CPU 3× realtime | Only OSS with tags + cloning + CPU; MIT clean; offline; per-voice ref clip | English-only; tag set smaller than Fish's (mapping needed); new torch dependency (~2GB); RAM alongside Whisper | **Selected candidate** |
| Chatterbox Multilingual V3 (local) | MIT; 500M; 23 langs; cloning | Keeps non-English replies with one backend | No tag support on this line → emotion lost; heavier than Nano | Fallback for the `WHISPER_LANGUAGES` path |
| Fish S2 Pro self-hosted | 4B open weights, identical tag syntax, SGLang serving | Zero REPLIES changes; top quality; 80+ langs | GPU required; custom research license; heavy ops | GPU-box future option |
| Kokoro / Piper (local) | Small CPU models, fixed voices | Bulletproof CPU speed, light deps | No cloning, no emotion → REPLIES tags must be stripped; voice personality lost | Emergency CPU-only fallback |
| XTTS-v2 / F5-TTS (local) | Zero-shot cloning OSS | Cloning without GPU for F5 | No tags; XTTS AGPL + dead; F5 CPU marginal | Rejected for this feature |

## Design Decisions

### Decision: `TTS_BACKEND` switch in shared/config, Chatterbox as the OSS implementation
- **Context**: One spoken-line seam (`fetch_tts`) serves local app, web remote, reminders and warm cache; backends must be selectable and per-turn patchable.
- **Alternatives Considered**:
  1. Hard-swap Fish for Chatterbox — simplest, loses the free cloud option and the ability to A/B.
  2. `TTS_BACKEND = "fish" | "chatterbox"` module attribute read as `config.TTS_BACKEND` — parallel implementations, per-turn patchable like every other config knob.
- **Selected Approach**: Add `config.TTS_BACKEND` (default `"fish"`); `fetch_tts` dispatches on it. Chatterbox path: map tags → call `ChatterboxTurboTTS.generate(text_mapped, audio_prompt_path=config.TTS_REF_CLIP)` on CPU → write wav into the existing cache dir. Cache key becomes `SHA1(f"{TTS_BACKEND}|{voice}|{text}")` with `voice = TTS_REF_CLIP` for chatterbox, so switching backends/voices invalidates cleanly.
- **Rationale**: Preserves the global-patch contract (config attrs only), keeps the free Fish path working until Nov 2026, and makes the warm-cache/pre-render flow identical for both backends.
- **Trade-offs**: One extra model-load code path (lazy load on first render, mirroring `_Whisper`); two torch-family dependency trees to keep healthy; English-only for Turbo/Nano.
- **Follow-up**:
  - Measure Nano cold render + warm cache on the actual win11/linux boxes (8-core assumption).
  - Verify Chatterbox Python/torch version compatibility with each platform venv (faster-whisper pins its own ctranslate2; they can coexist but the resolver needs testing).
  - Decide tag map: `[chuckling]→[chuckle]`, `[laughing]→[laugh]`, `[sighing]→[sigh]`, `[clear throat]→[cough]` (verify supported tag list against Turbo docs), `[cheerful]→strip` (no direct equivalent; rely on ref-clip warmth).
- **Reference clip sourced (2026-09-30)**: `voice-ref-clip.wav` (this folder) — 25 s, 24 kHz mono PCM, cut from a public-domain LibriVox recording of Shakespeare's sonnets read by Elizabeth Klett ([archive.org/item/sonnets_etk_librivox](https://archive.org/item/sonnets_etk_librivox), licenseurl `creativecommons.org/licenses/publicdomain`). Chosen because the persona is a female voice and the recording is a clean single-reader studio-quality read whose license permits cloning and redistribution. Swap by pointing `TTS_REF_CLIP` at another clip; the cache key changes with it, so no stale audio reuse.

### Persona switching extension (added after the first requirements pass)
- **Context**: The user asked for a "switch persona" command where the app itself finds a suitable clip for cloning, caches it, and uses that persona's voice.
- **Findings**:
  - Public-domain single-reader catalogs (LibriVox on archive.org, verified this session) give per-recording direct file URLs, per-item license metadata (`licenseurl`), and reader identity — enough for the app to fetch and screen clips automatically.
  - archive.org exposes both a search API (advancedsearch.php, JSON) and per-item file metadata (metadata endpoint) that were exercised end-to-end today for this sourcing.
  - Per-persona caching reuses the same pattern as the TTS reply cache: content-addressed files under a config-overridden directory.
  - Voice-command routing can ride the existing Jev fan-out (a persona question), or a typed/remote command; both flow through the existing command paths.
- **Implications**: Personas become catalog entries (name → PD source + description) plus a per-persona clip cache; requirements 9–10 capture the observable behavior. Catalog curation and the fetch/screen flow belong to design.

### Local backend live verification (2026-09-30, win11 dev box, Python 3.13, torch 2.6.0+cpu)
- **Context**: First real end-to-end run of the chatterbox backend after bulk implementation.
- **Findings**:
  - `chatterbox-tts 0.1.7` exposes **Turbo (350M) only** — `ChatterboxTurboTTS.from_pretrained(device)` has no nano flag and the package ships no Nano class. `TTS_CHATTERBOX_VARIANT` remains a hook for a future release; both variants currently load Turbo.
  - Two vendor CPU bugs required load-time workarounds in `tts._ensure_model` (verified necessary): the S3 conditioning path feeds a **float64 numpy wav** into a float32 mel bank (root cause: default `norm_loudness=True` runs pyloudnorm, which returns float64 and leaks into every conditioning consumer) — fixed by casting audio to float32 at the `log_mel_spectrogram` choke point and forcing float32 out of `norm_loudness`.
  - **Real render works**: six reply-length lines rendered through the product seam; wavs verified 24 kHz mono.
  - **RTF evidence (requirement 8.1)**: mean **3.82**, max **4.30** — **FAIL against the < 1.0 target** on this box (AMD Zen4 mobile; torch thread tuning 8/4 changed nothing beyond noise). Cause: Turbo 350M's AR token loop (~10–13 tok/s) is too heavy for the envelope; Nano (110M, the intended CPU model) is not loadable in 0.1.7.
  - Practical impact while RTF > 1: warm-cache scripted replies stay instant (background pre-render, ~8–10 min for the full set on first run); a **new** LLM-written line waits ~8–12 s before playback. Cached lines unaffected.
- **Implications**: The local backend is functionally complete but misses the realtime envelope with 0.1.7/Turbo. When Nano ships loadable: flip the default variant and re-run the harness (vendor claims ~3× realtime on 8 cores). Until then the Fish default stays the latency-safe choice for live answers; the switch remains correct for offline/privacy use and warm-cache-dominant usage. Re-verify on the linux box (thread counts and BLAS differ).

### Decision: keep Fish as default until the free window ends (30 Nov 2026)
- **Context**: `s2.1-pro-free` is $0 until end of November 2026; post-paid cost with the reply cache is cents/day.
- **Alternatives Considered**: flip default now vs. keep Fish default and merge the switch early.
- **Selected Approach**: merge the switch on `feature-alternatives` with Fish still default; flip the default when the free window ends or when offline/privacy demands it.
- **Rationale**: zero regression risk for daily users now; the branch stays a cheap insurance policy and a live benchmark harness.
- **Trade-offs**: two backends carried in requirements.txt (or Chatterbox as an extras group `pip install .[tts-local]` to keep base installs light — decide at design time).
- **Follow-up**: revisit default after a week of side-by-side latency/quality logs.

### Decision: non-English replies are out of scope for the first cut
- **Context**: Turbo/Nano are English-only; `WHISPER_LANGUAGES` already gates a multilingual STT feature.
- **Alternatives Considered**: route non-en turns to Multilingual V3 (tag-less) vs. keep Fish for non-en.
- **Selected Approach**: document that when `WHISPER_LANGUAGES` has non-en entries, TTS stays Fish (or Multilingual V3 as a degraded mode with tags stripped).
- **Rationale**: keeps the first cut small; the tag strip is mechanical if V3 is chosen later.
- **Follow-up**: verify Multilingual V3 quality for the shipped ref clip's voice.

## Risks & Mitigations
- Tag leak (unmapped Fish tag spoken aloud) — enforce a single `map_tags()` with a whitelist + unit test over every `REPLIES` template expansion and a sample of LLM outputs; unknown tags stripped defensively.
- CPU contention with Whisper during a turn — render is usually cached/warmed; for live LLM answers render after or serialize with the existing `busy`/`turn_lock` locks; measure on 8-core boxes.
- Torch/ctranslate2 dependency conflicts in platform venvs — pin and test `requirements.txt` resolution on both platforms before merge; consider an optional extras group.
- Ref-clip voice drift from the Fish voice — accept a different (local) voice identity; ship a curated clip and document the change; cache key change forces clean re-render.
- License/compliance drift — Chatterbox MIT verified today; re-verify at pin time; Fish S2 Pro custom license explicitly not adopted for bundling.
- Drift between win11/linux copies — both platforms import the same brain/config; keep backend code in `shared/`, platform layers only wire `play_wav_hook` (already true).

## References
- [fishaudio/fish-speech](https://github.com/fishaudio/fish-speech) — S2 Pro open weights, tag syntax, license notice (fetched 2026-09-30)
- [Fish Audio S2 Technical Report](https://arxiv.org/abs/2603.08823) — architecture, benchmarks, streaming numbers
- [resemble-ai/chatterbox](https://github.com/resemble-ai/chatterbox) — Turbo/Nano/Multilingual V3, MIT, tag examples, usage (fetched 2026-09-30)
- [ResembleAI/chatterbox-nano (HuggingFace)](https://huggingface.co/ResembleAI/chatterbox-nano) — Nano weights
- [fishaudio/s2-pro (HuggingFace)](https://huggingface.co/fishaudio/s2-pro) — S2 Pro weights
- Repo internals: `shared/brain.py` (fetch_tts, REPLIES, warm_cache, prepare_reminder), `shared/config.py` (VOICE_ID, backend priority pattern), `shared/remote_server.py` (say patch, wav streaming), `shared/doc/02-risks-invariants.md` (config-attr invariant)
