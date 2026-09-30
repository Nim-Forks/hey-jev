# Requirements Document

## Introduction
This feature adds a selectable open-source TTS backend to hey-jev so the assistant can speak without depending on the Fish Audio cloud API. Today every spoken line flows through one seam (`fetch_tts`), backed by a disk cache and a startup warm-up, using a cloud-hosted voice and Fish-style emotion tags. The feature introduces a backend switch that keeps that flow intact while adding a local, offline-capable engine. Discovery findings and the decision record live in `research.md` (this folder).

## Boundary Context
- **In scope**: choosing the TTS backend via configuration; rendering speech locally; mapping emotion tags across backends; defining the assistant voice by a reference clip; cache behavior across backend changes; startup validation and failure handling for the TTS path; switching the assistant's persona by command; automatic discovery, licensing screening, and caching of persona voice clips.
- **Out of scope**: changing the default backend away from the cloud TTS; decision and question-answering services (Jev / LLM); speech-to-text (Whisper); non-English speech synthesis with the local backend; self-hosting the cloud vendor's own open-weight model; changes to the remote server protocol or its wav streaming; persona switching while the cloud backend is active.
- **Adjacent expectations**: the remote (browser) client continues to receive rendered wav audio unchanged; timer and reminder alerts continue to pre-render and play through the same TTS layer; each platform keeps providing its own audio playback hook; cost reporting continues to attribute TTS-free turns as before.

## Requirements

### Requirement 1: Selectable TTS backend
**Objective:** As a user, I want to choose between the cloud TTS and a local open-source TTS in configuration, so that the assistant can run without the cloud voice service.

#### Acceptance Criteria
1. While the backend setting is `"fish"`, the TTS layer shall render speech through the Fish Audio cloud API with today's behavior, unchanged.
2. When the backend setting is `"chatterbox"`, the TTS layer shall render speech locally on the machine, with no request to any external TTS service.
3. When the backend setting names an unimplemented backend, the assistant shall fail at startup with a message naming the valid values, rather than failing mid-turn.
4. The assistant shall allow switching the active backend by configuration alone, with no code edits.

### Requirement 2: Emotion tags across backends
**Objective:** As a listener, I want the assistant's replies to keep their expressive tone on every backend, so that the voice personality survives a backend switch.

#### Acceptance Criteria
1. When a reply line contains a known emotion tag, the TTS layer shall convert it to the selected backend's closest equivalent expression before synthesis.
2. When a reply line contains a tag the selected backend does not support, the TTS layer shall remove it from the spoken text instead of speaking it aloud.
3. When a reply line contains no tags, the TTS layer shall synthesize the text unchanged.
4. While the LLM writes reminder alert lines, the TTS layer shall apply the same tag handling as for scripted replies.

### Requirement 3: Voice identity from a reference clip
**Objective:** As a user, I want the local backend to speak with one consistent cloned voice, so that the assistant sounds like the same assistant every day.

#### Acceptance Criteria
1. While the local backend is active, the TTS layer shall synthesize all speech from the configured reference clip.
2. Where no reference clip is configured and the local backend is active, the TTS layer shall use the bundled default clip shipped with the feature.
3. When the configured reference clip is missing or unreadable while the local backend is active, the assistant shall fail at startup with a message naming the missing file.
4. Where the cloud backend is active, the TTS layer shall continue to use the configured cloud voice id as today.

### Requirement 4: Cache and warm-up preserved
**Objective:** As a user, I want replies to stay instant after a backend switch, so that the assistant does not feel slower than today.

#### Acceptance Criteria
1. When a line has already been rendered for the active backend and voice, the TTS layer shall return the cached audio without re-synthesizing.
2. When the backend or the voice changes, the TTS layer shall treat previously cached audio as stale and re-render on demand.
3. While the assistant is starting, the TTS layer shall pre-render every fixed reply line for the active backend in the background, as today.
4. The assistant shall report per-line render duration in the console trace (cached lines as 0), so operators keep today's diagnostics.

### Requirement 5: Language scope of the local backend
**Objective:** As a multilingual user, I want clear expectations about non-English speech, so that a backend switch cannot silently degrade replies I understand.

#### Acceptance Criteria
1. Where the configured speech languages are English-only, the assistant shall allow selecting the local backend.
2. When the local backend is selected and any non-English language is configured, the assistant shall refuse the selection at startup with a message saying non-English replies need the cloud backend.
3. Non-English synthesis on the local backend is out of scope for this feature.

### Requirement 6: Graceful TTS failures
**Objective:** As a user, I want the assistant to survive speech-rendering problems, so that one bad render never ends the session.

#### Acceptance Criteria
1. If a local render fails, the assistant shall report the failure in the status surface and console, and remain usable for the next turn.
2. If a local render fails, the assistant shall not fall back to the cloud backend silently; switching backends stays an explicit configuration change.
3. While the local model is loading on first use, the assistant shall show its normal activity states instead of appearing frozen.

### Requirement 7: TTS traffic boundary
**Objective:** As a privacy-conscious user, I want the local backend to keep spoken text off the network, so that what the assistant says never reaches a voice vendor.

#### Acceptance Criteria
1. While the local backend is active, the TTS layer shall send no speech text or rendered audio to any external service.
2. The TTS backend setting shall not change where decision or question-answering traffic is sent; those services keep their own configuration.

### Requirement 8: Performance envelope on CPU-only machines
**Objective:** As a user without a GPU, I want the local backend to keep up with playback, so that long waits never replace replies.

#### Acceptance Criteria
1. While running on the supported CPU-only machines, the local backend shall synthesize a typical reply-length line faster than realtime (render time shorter than the audio duration) once the model is loaded.
2. When a line is rendered for the first time and takes longer than its playback duration, the assistant shall play the audio when ready rather than dropping the reply.

### Requirement 9: Persona switching command
**Objective:** As a user, I want to switch the assistant's persona to something else with a single command, so that the voice I hear matches a character I prefer.

#### Acceptance Criteria
1. When the user issues a switch-persona command naming a known persona, the assistant shall adopt that persona's voice for all later speech.
2. When the switch completes, the assistant shall confirm the switch spoken in the new persona's voice.
3. When the user names a persona the assistant does not know, the assistant shall keep the current persona and reply naming the available personas.
4. When the user asks what personas exist or which one is active, the assistant shall announce the active persona and the available ones.
5. While a persona switch is in progress, the assistant shall show its normal activity states instead of appearing frozen.
6. When the assistant restarts, it shall keep using the persona that was active before the restart.
7. When the cloud backend is active, the assistant shall keep the current voice and reply that persona switching needs the local backend.

### Requirement 10: Automatic persona clip discovery and caching
**Objective:** As a user, I want the app to find a suitable voice clip for a persona by itself, so that I never have to hunt for audio files.

#### Acceptance Criteria
1. When a persona is selected, the assistant shall obtain a suitable reference clip for that persona without any user-supplied audio.
2. When the clip for the requested persona is already cached on the machine, the assistant shall use the cached clip and skip any download.
3. When a clip is fetched for a persona, the assistant shall store it in a per-persona cache, so switching back to that persona works without another download.
4. The assistant shall fetch persona clips only from sources whose license permits voice cloning and redistribution (public domain or equivalent).
5. If no suitable clip can be found, the assistant shall keep the current persona's voice and say so.
6. The assistant shall use each persona's cached clip consistently across backend switches within the same session and restarts.

## Constraints & Assumptions
- The cloud backend remains the default until its free pricing window ends (end of November 2026); this feature only adds the option.
- The local backend must operate on the CPU-only machines the platforms already target (no GPU requirement).
- The rendered output stays wav, so the existing cache layout, playback hooks, and remote streaming keep working.

## Glossary
- **Cloud backend / fish** — the current Fish Audio S2.1 Pro cloud TTS reached over the network with an API key.
- **Local backend / chatterbox** — the open-source TTS engine that runs on the machine, selected by the new setting.
- **Emotion tags** — bracketed markers in reply text, e.g. `[chuckling]`, `[sighing]`, that shape how a line sounds.
- **Reference clip** — a short (~10 s) audio sample that defines the assistant's cloned voice for the local backend; the feature bundles a default (public-domain LibriVox recording of Shakespeare's sonnets read by Elizabeth Klett, 25 s, in this folder).
- **Warm cache** — pre-rendering every fixed reply line at startup so later plays are instant.
- **Persona** — a named voice character (e.g. the bundled default) with its own reference clip; switching persona changes the voice the local backend speaks with.
- **Persona clip cache** — the on-disk store of fetched per-persona reference clips, so a persona works offline after its first selection.
