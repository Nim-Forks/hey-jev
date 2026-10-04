# Combo instances — decision × voice matrix (geekom)

Six instances on the geekom, one per decision-backend × voice combination,
so capabilities and response times can be compared live. Built 2026-10-04 on
release `900e206`; stress-tested with the `deva` token (2.1 s spoken
"set a timer for five minutes" → 4 turns each: set, cancel, set, cancel).

## Ranking (measured)

| # | URL | decision + voice | warm turn | cost/decision | cost / 1000 turns | best used for |
|---|---|---|---|---|---|---|
| 1 | https://or-fish.nimes.in | OpenRouter + Fish | ~2–5 s | $0.000072 | $0.07 | daily driving — fastest, cloud-quality voice |
| 2 | https://jev-local.nimes.in | OpenRouter* + Chatterbox | 2–3 s cached / +5–20 s fresh | $0.000072 | $0.07 | personas + speed; true Typesafe after key |
| 3 | https://or-local.nimes.in | OpenRouter + Chatterbox | same as #2 | $0.000072 | $0.07 | duplicate of #2 — A/B after key |
| 4 | https://jev-fish.nimes.in | OpenRouter + Fish | ~3–5 s | $0.000072 | $0.07 | spare / parallel of #1 |
| 5 | https://kev-local.nimes.in | KEV + Chatterbox | ~15–20 s | $0.000037 | $0.04 | personas on a budget — half the cost, 21× slower |
| 6 | https://kev-fish.nimes.in | KEV + Fish | ~15 s | $0.000037 | $0.04 | KEV benchmarking only |

Voice cost: Fish = $0 (`s2.1-pro-free`, free until end of Nov 2026);
Chatterbox = $0 (local CPU). LLM answers (glm-5.3-flash) cost the same on all
six, only on question turns.

\* `jev-*` currently served by OpenRouter — no `TYPESAFE_API_KEY` exists yet.
Paste a key into `~/combo/jev-fish/.env` / `jev-local/.env` + restart for real
Typesafe numbers.

## Stress detail (2026-10-04, 4 turns each, sequential)

| | kev-fish | kev-local | jev-fish | jev-local | or-fish | or-local |
|---|---|---|---|---|---|---|
| decision actually served | kev | kev | openrouter | openrouter | openrouter | openrouter |
| STT (whisper small.en) | 1.2–1.3 s | 1.2–2.0 s | 1.2–1.4 s | 1.3–1.8 s | 1.2–1.4 s | 1.2–1.4 s |
| Jev decision | 12.9–14.7 s | 11.8–13.4 s | 0.31–0.66 s | 0.35–0.72 s | 0.31–0.9 s | 0.35–0.85 s |
| TTS cold | fish 1.0–2.4 s | chatterbox 30.4 s | fish 0.7–1.3 s | chatterbox 19.8 s | fish 3.8 s | chatterbox 19.6 s |
| TTS warm | ~1 s | 6.3 s / 0 cached | ~1 s | 4.8–6.3 s / 0 cached | 1.4 s / 0 cached | 7.1 s / 0 cached |
| turn wall | 15.5–36.1 s | 15.3–45.5 s | 2.8–5.0 s | 4.8–24.8 s | 2.2–12.9 s | 2.0–23.4 s |
| personas (voice switch) | ✗ | ✓ | ✗ | ✓ | ✗ | ✓ |

Findings:

- **KEV is the bottleneck**: 12–15 s per decision (21× OpenRouter's 0.3–0.9 s)
  at half the price. One kev-fish turn hit the 30 s decision timeout and
  dropped (give-up reply) — a real reliability risk under load.
- Chatterbox model load adds ~15–30 s to the first render per instance
  (per-process, stays resident ~1.5–2 GB).
- Warm end-to-end: openrouter+fish ≈ 1.5–3 s; chatterbox adds 5–7 s fresh,
  0 s cached.

## Layout

- Per instance: `~/combo/<name>/` — a **real copy** of `linux/remote.py` +
  `linux/siri.py` (Python 3.11+ resolves symlinked script dirs, so the entry
  files must be real) and symlinks `shared`, `web`, `assets` → prod checkout.
  Per-instance `.env` = prod's base with overrides.
- Ports / combos / gate: 8767 kev-fish (0.45), 8768 kev-local (0.45),
  8769 jev-fish (0.65), 8770 jev-local (0.65), 8771 or-fish (0.65),
  8772 or-local (0.65). All en-only (`WHISPER_LANGUAGES=en`), `deva` token
  active, same NTFY/keys as prod.
- Units: `hey-jev-<name>.service` (system), ExecStart = prod venv
  (`remote.py`), WorkingDirectory = `~/combo/<name>/linux`.
- Tunnel: `~/.cloudflared/config.yml` ingress entries per hostname →
  localhost port; DNS CNAMEs `<name>.nimes.in` →
  `7f8b0c6e-...cfargotunnel.com` (proxied), added via dashboard (the box cert
  can't route nimes.in).

## Ops

- Restart one: `sudo systemctl restart hey-jev-<name>`
- After code syncs, refresh entry copies:
  `for n in kev-fish kev-local jev-fish jev-local or-fish or-local; do
   cp ~/hey-jev-prod/linux/{remote,siri}.py ~/combo/$n/linux/; done`
  (plus `git -C ~/hey-jev-prod pull` + `deploy-service.sh hey-jev-prod`)
- Test `*-local` combos sequentially — three Chatterbox models resident would
  need ~6 GB on top of everything else (box has 11 GiB).
- Croatian stays on prod (`hey-jev.nimes.in`, `en,hr`, fish) — no combo
  instance speaks it while Chatterbox 0.1.7 is en-only.
