"""Thin remote wrapper: wires the platform layer into shared/remote_server."""
import os
import sys

import siri  # noqa: F401  — wires platform hooks
from shared import brain, config
from shared import remote_server as rs


def remote_timer_done(t):
    try:
        siri.chime()
        siri.play_wav_path(brain.fetch_tts(brain.timer_done_line(t))[0])
    except Exception as e:
        print(f"  timer alert failed: {e}")
    label = t.get("label") or "Timer finished"
    line = brain.timer_done_line(t)
    try:
        brain.notify_push("Hey Jev", t.get("label") or config.ALERT_MESSAGE or line)
    except Exception:
        pass
    for conn in list(rs._server.web_clients):
        sess = rs._server.sessions.get(conn, {})
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
            rs._server.web_clients.discard(conn)


def run_remote():
    brain.load_timers()
    brain.start_timer_loop(remote_timer_done)
    rs.serve()


if __name__ == "__main__":
    run_remote()
