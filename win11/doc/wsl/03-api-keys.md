# API keys on WSL Ubuntu

Identical to the Windows port: the Keychain is macOS-only, so use the
`.env` fallback — which **wins over everything** by design
(`secrets_store.py` checks the environment first).

## Create the .env

In the repo root (next to `siri.py`):

```bash
cat > .env <<'EOF'
TYPESAFE_API_KEY=...
FISH_AUDIO_API_KEY=...
OPENROUTER_API_KEY=...
EOF
chmod 600 .env
```

- OpenRouter optional (questions only; also the decisions fallback if
  Typesafe/KEV are absent).
- With no `security` binary, an empty key makes `get_secret()` raise — every
  used key must be non-empty.
- The port's `secrets_store.py` uses `keyring` (Secret Service/GNOME Keyring)
  with `.env` as fallback; on WSL, `.env` is the practical path.

## Keys reference

Full table (backends, LLM, remote, ntfy): [../win11/03-api-keys.md](../win11/03-api-keys.md)
— identical variable names.

## Keep it secret

`chmod 600 .env`, already git-ignored. Do not paste values into chats or
issues; rotate at the provider if leaked.
