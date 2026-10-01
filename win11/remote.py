"""Thin remote wrapper: wires the platform layer into shared/remote_server.

Do NOT `import siri` here — the repo root's macOS siri.py would shadow the
platform layer. The platform hooks (chime, play_wav, machine_context) are
already wired into shared/config by the platform siri.py.
"""
from dotenv import load_dotenv

from shared import brain, config
from shared import remote_server as rs

# standalone-entry parity with siri.py: shared/config.py's dotenv walk misses
# this platform's .env, so re-read it for settings like TTS_BACKEND
import os
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
config.TTS_BACKEND = os.getenv("TTS_BACKEND", config.TTS_BACKEND)


def remote_timer_done(t, server):
    try:
        config.chime_hook()
        config.play_wav_hook(brain.fetch_tts(brain.timer_done_line(t))[0])
    except Exception as e:
        print(f"  timer alert failed: {e}")
    label = t.get("label") or "Timer finished"
    line = brain.timer_done_line(t)
    try:
        brain.notify_push("Hey Jev", t.get("label") or config.ALERT_MESSAGE or line)
    except Exception:
        pass
    for conn in list(server.web_clients):
        sess = server.sessions.get(conn, {})
        ntfy = sess.get("ntfy", "")
        client_msg = (sess.get("keys", {}) or {}).get("ALERT_MESSAGE")
        push_body = t.get("label") or client_msg or line
        speak_line = (label if t.get("label") else (client_msg or line))
        if ntfy:
            try:
                brain.notify_push("Hey Jev", push_body, url=ntfy)
            except Exception as e:
                print(f"  ntfy push failed: {e}")
        try:
            conn.send_text({"type": "timer-fired", "label": label, "line": speak_line})
        except Exception:
            server.web_clients.discard(conn)


def run_remote():
    brain.load_timers()
    brain.start_timer_loop(lambda t: remote_timer_done(t, rs._server))
    rs.serve()


if __name__ == "__main__":
    run_remote()
