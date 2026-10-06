# Combo instances — decision × voice matrix (geekom)

Sixteen combo instances on the geekom: six from the first wave (hosted
backends, built 2026-10-04 on release `900e206`) and ten from the second
(systemone wave, `f8da21e` — see the Second wave section below). Stress and
smoke numbers below were gathered with the fleet access token (2.1 s spoken
"set a timer for five minutes" → 4 turns each: set, cancel, set, cancel).

## Ranking (measured)

| # | URL | decision + voice | warm turn | cost/decision | cost / 1000 turns | best used for |
|---|---|---|---|---|---|---|
| 1 | https://liquid-fish.nimes.in | **Liquid d1:free + Fish** | **~4 s** (`jev 910ms` decision) | $0 (free tier) | $0 | **daily driving — fastest, calibrated, free** |
| 2 | https://liquid-local.nimes.in | Liquid d1:free + Chatterbox | ~4 s + chatterbox | $0 | $0 | personas on the best decider |
| 3 | https://laya-fish.nimes.in | laya (self-hosted) + Fish | ~8 s (decision 5.8 s) | $0 | $0 | best self-hosted decider (88.9 % agreement) |
| 4 | https://laya-local.nimes.in | laya + Chatterbox | ~8 s + chatterbox | $0 | $0 | offline-ish personas |
| 5 | https://opendecider-fish.nimes.in | opendecider + Fish | ~7 s (decision 5.5 s) | $0 | $0 | fastest self-hosted probe |
| 6 | https://opendecider-local.nimes.in | opendecider + Chatterbox | same | $0 | $0 | |
| 7 | https://or-fish.nimes.in | OpenRouter + Fish | ~2–5 s | $0.000072 | $0.07 | snappiest hosted decisions |
| 8 | https://or-local.nimes.in | OpenRouter + Chatterbox | same + chatterbox | $0.000072 | $0.07 | personas |
| 9 | https://jev-fish.nimes.in | OpenRouter* + Fish | ~3–5 s | $0.000072 | $0.07 | spare of #7 |
| 10 | https://jev-local.nimes.in | OpenRouter* + Chatterbox | same | $0.000072 | $0.07 | true Typesafe after key |
| 11 | https://kev-local.nimes.in | hosted KEV + Chatterbox | ~15–20 s | $0.000037 | $0.04 | legacy comparison |
| 12 | https://kev-fish.nimes.in | hosted KEV + Fish | ~15 s | $0.000037 | $0.04 | benchmark only |
| 13–14 | https://anarkali-fish / -local.nimes.in | anarkali ($0) | ⚠ clarifies | $0 | $0 | unblocked by `31d3bfd`; near-uniform confidences (~0.2) + timer bias — skip until retrained |
| 15 | https://clef-fish.nimes.in | Clef 27B via gate ($~0.00006) | 3.8–6.1 s | $~0.00006 | $0.06 | deterministic, image input, `confidence` semantics differ (see 08) |
| 16 | https://clef-local.nimes.in | Clef + Chatterbox | + chatterbox | $~0.00006 | $0.06 | personas on Clef decisions |

Voice cost: Fish = $0 (`s2.1-pro-free`, free until end of Nov 2026);
Chatterbox = $0 (local CPU). LLM answers (glm-5.3-flash) cost the same on all
instances, only on question turns.

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

## Wave 3 — Clef (2026-10-06)

`clef-fish` (8783) and `clef-local` (8784) — decision backend = **Cloudflare
Clef** (27B, Apache 2.0, Jev-API compatible) via **Workers AI**
(`@cf/cloudflare/clef`, ~$0.06/1k turns, deterministic, image-capable).
Workers AI wraps answers in `{"result": ...}` and needs the model id in the
URL, so the instances go through the **gate's new cloud mode**
(`KEV_URL=http://127.0.0.1:8900/clef`, `KEV_MODEL=clef`, key = the Workers AI
token stored in `deciders.env` as `CLEF_KEY`) — the gate rewrites the URL and
unwraps the envelope. Measured: 2-question 0.92 s; real fan-out `jev 605ms`;
full turns 3.8–6.1 s. Clef-flash (`cloudflare/clef-flash`, 9B, ~$0.02/1k) is
the drop-in faster variant — not deployed yet.

## Wave 2 — systemone combos (2026-10-04, pending re-test)

Ten more instances, one per new decision backend × voice, pointing their
decision side at the on-demand gate (`http://127.0.0.1:8900/<name>`, see
`08-systemone-backends.md`). All en-only, the shared access token, base `.env` from prod.

| instance | URL | port | decision | voice | gate | note |
|---|---|---|---|---|---|---|
| hey-jev-anarkali-fish | https://anarkali-fish.nimes.in | 8773 | anarkali (gate) | Fish | 0.45 | unblocked by `31d3bfd`; routes but conf ~0.2 (clarifies) — needs anarkali retraining |
| hey-jev-anarkali-local | https://anarkali-local.nimes.in | 8774 | anarkali (gate) | Chatterbox | 0.45 | same |
| hey-jev-von-fish | https://von-fish.nimes.in | 8775 | von (gate) | Fish | 0.45 | von: 70.4 % agreement, 2 wrong @ conf 0.9 in stress |
| hey-jev-von-local | https://von-local.nimes.in | 8776 | von (gate) | Chatterbox | 0.45 | |
| hey-jev-opendecider-fish | https://opendecider-fish.nimes.in | 8777 | opendecider (gate) | Fish | 0.45 | fastest decider (0.45 s probe) |
| hey-jev-opendecider-local | https://opendecider-local.nimes.in | 8778 | opendecider (gate) | Chatterbox | 0.45 | |
| hey-jev-laya-fish | https://laya-fish.nimes.in | 8779 | laya (gate) | Fish | 0.45 | best agreement 88.9 % in stress |
| hey-jev-laya-local | https://laya-local.nimes.in | 8780 | laya (gate) | Chatterbox | 0.45 | |
| hey-jev-liquid-fish | https://liquid-fish.nimes.in | 8781 | **Liquid d1:free — live** | Fish | 0.45 | key activated 2026-10-04; `jev 910ms` on the real 15-question fan-out, turns 4.0–4.3 s |
| hey-jev-liquid-local | https://liquid-local.nimes.in | 8782 | Liquid d1:free | Chatterbox | 0.45 | same |
| hey-jev-clef-fish | https://clef-fish.nimes.in | 8783 | Clef → the gate's cloud mode → Workers AI | Fish | 0.45 | 2026-10-06: `jev 605ms`, turns 3.8–6.1 s, deterministic |
| hey-jev-clef-local | https://clef-local.nimes.in | 8784 | same | Chatterbox | 0.45 | personas |

Cold-gate caveat: the very first decision after a cold gate may exceed the
30 s decision timeout for von/opendecider (model reload); laya measured 4 s
cold, anarkali ~1 s. Re-test pending — table to be extended with timings.

Smoke check (2026-10-04, public URLs, set→cancel): laya-fish ✅ (decision
`jev 5553ms` via gate — the `backend: kev` label is cosmetic), liquid-fish ✅
(OpenRouter fallback until the `liquid_` key lands), anarkali-fish: the 422
blocker is fixed (`31d3bfd` — every choice option now carries a description;
live turns complete, `jev 1130ms` via gate) but anarkali's confidences stay
near-uniform (~0.2) with a timer bias, so turns clarify — anarkali needs its
own retraining, not a wire fix.

## Layout

- Per instance: `~/combo/<name>/` — a **real copy** of `linux/remote.py` +
  `linux/siri.py` (Python 3.11+ resolves symlinked script dirs, so the entry
  files must be real) and symlinks `shared`, `web`, `assets` → prod checkout.
  Per-instance `.env` = prod's base with overrides.
- Ports / combos / gate: 8767 kev-fish (0.45), 8768 kev-local (0.45),
  8769 jev-fish (0.65), 8770 jev-local (0.65), 8771 or-fish (0.65),
  8772 or-local (0.65). All en-only (`WHISPER_LANGUAGES=en`), shared access token
  active, same NTFY/keys as prod.
- Units: `hey-jev-<name>.service` (system), ExecStart = prod venv
  (`remote.py`), WorkingDirectory = `~/combo/<name>/linux`.
- Tunnel: `~/.cloudflared/config.yml` ingress entries per hostname →
  localhost port; DNS CNAMEs `<name>.nimes.in` →
  `7f8b0c6e-...cfargotunnel.com` (proxied), added via dashboard (the box cert
  can't route nimes.in).

## Ops

- **Deploy new code to all 16 combos** (pull, refresh entry copies, restart,
  health-check): `bash ~/hey-jev-prod/linux/deploy-combos.sh` — add
  `--with-beta` to also sync + restart beta.
- Restart one: `sudo systemctl restart hey-jev-<name>`
- Test `*-local` combos sequentially — three Chatterbox models resident would
  need ~6 GB on top of everything else (box has 11 GiB).
- International language (en + hr) stays on prod (`hey-jev.nimes.in`, fish) — no combo
  instance speaks it while Chatterbox 0.1.7 is en-only.
