# API keys & configuration on Linux

Identical variable names to the Windows port — reference:
[../win11/03-api-keys.md](../win11/03-api-keys.md). Differences only:

| Key | Linux notes |
| --- | --- |
| `REMOTE_FRONT` | `tunnel` (the machine's own cloudflared) or `none`; NPM on this box sits behind the tunnel wildcard |
| `REMOTE_HOST` | `127.0.0.1` — the tunnel reaches it locally; `0.0.0.0` if you want LAN access too |
| `REMOTE_TOKEN` | set it — the tunnel makes the server public |
| `REMOTE_TOKENS` | optional extra tokens, comma-separated — one per device; delete one + `systemctl restart` to revoke |
| `NTFY_URL` | same ntfy topic (or a separate one per machine) |
| `ALERT_MESSAGE` | same default-alert behavior |
| `SERVER_KEY_LIMIT` | same client-side quota |

Everything else (decision backends, `LLM_MODEL`, `LLM_MAX_TOKENS`,
`JEV_GATE`, Fish key) is identical — copy `win11/.env` and adjust the
`REMOTE_*` lines. `KEV_MODEL` picks the model id sent to a KEV-compatible
endpoint (defaults `jev-latest`; e.g. `d1:free` for Liquid).

## Keys panel

The tkinter window is X11-only; on a headless box use `.env` (or the web
remote's Settings page, which stores per-device keys in browser
localStorage — same paste-first/bulk-import UI as Windows).

## Keep it secret

`chmod 600 .env`; it's git-ignored. The tunnel makes the server public —
**keep `REMOTE_TOKEN` set** (the startup banner warns when it's empty).
