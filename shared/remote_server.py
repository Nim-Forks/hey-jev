"""HTTP/WebSocket remote server for hey-jev: browsers (and the Termux client)
act as the mic + PTT; the platform's siri.py --remote wraps this module.
See doc/android/09-web-only-client.md for the protocol design.

Front-door agnostic: always binds plain HTTP on REMOTE_PORT; REMOTE_FRONT
only changes the startup hint. Platform layer calls serve().
"""
import base64
import hashlib
import json
import os
import struct
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

from shared import brain, config
from shared.secrets_store import KEY_NAMES


STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
FAVICON_PATH = os.path.normpath(os.path.join(STATIC_DIR, "..", "..", "assets", "icon.png"))
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
SERVER_KEY_LIMIT = int(os.getenv("SERVER_KEY_LIMIT", "10"))

_server = None  # module-level ref set by serve()


def http_send(handler, code, body, ctype):
    handler.send_response(code)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


class WsConn:
    def __init__(self, sock):
        self.sock = sock

    def _read_exact(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("ws closed")
            buf += chunk
        return buf

    def recv(self):
        b1, b2 = self._read_exact(2)
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._read_exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._read_exact(8))[0]
        mask = self._read_exact(4) if masked else None
        payload = self._read_exact(length) if length else b""
        if mask:
            payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
        return opcode, payload

    def send(self, opcode, payload):
        head = bytearray([0x80 | opcode])
        n = len(payload)
        if n < 126:
            head.append(n)
        elif n < 65536:
            head.append(126)
            head += struct.pack(">H", n)
        else:
            head.append(127)
            head += struct.pack(">Q", n)
        self.sock.sendall(bytes(head) + payload)

    def send_text(self, obj):
        self.send(1, json.dumps(obj).encode())

    def send_binary(self, data):
        self.send(2, data)


class RemoteServer:
    def __init__(self, port, host, front, tokens):
        self.port, self.host, self.front = port, host, front
        self.tokens = frozenset(tokens)   # any of these authenticates; drop one in .env to revoke it
        self.sessions = {}
        self.turn_lock = threading.Lock()
        self.web_clients = set()

    def token_ok(self, token):
        return not self.tokens or (token in self.tokens)

    def broadcast_web(self, msg):
        for conn in list(self.web_clients):
            try:
                conn.send_text(msg)
            except Exception:
                self.web_clients.discard(conn)

    @staticmethod
    def _clean_keys(keys):
        allowed = set(KEY_NAMES) | {"KEV_URL", "KEV_API_KEY", "LLM_MODEL", "ALERT_MESSAGE"}
        return {k: v for k, v in (keys or {}).items() if k in allowed and v}

    def begin_turn(self, conn):
        sess = self.sessions.get(conn, {})
        override = sess.get("keys", {})
        self._saved = (config.TS_KEY, config.FISH_KEY, config.OR_KEY,
                       config.KEV_URL, config.KEV_KEY, config.USE_KEV, config.LLM_MODEL)
        if override:
            config.TS_KEY = override.get("TYPESAFE_API_KEY", config.TS_KEY)
            config.FISH_KEY = override.get("FISH_AUDIO_API_KEY", config.FISH_KEY)
            config.OR_KEY = override.get("OPENROUTER_API_KEY", config.OR_KEY)
            config.KEV_URL = override.get("KEV_URL", "").strip().rstrip("/")
            config.KEV_KEY = override.get("KEV_API_KEY", "").strip()
            config.USE_KEV = bool(config.KEV_URL and config.KEV_KEY)
            config.LLM_MODEL = override.get("LLM_MODEL", config.LLM_MODEL)

    def end_turn(self, _conn):
        (config.TS_KEY, config.FISH_KEY, config.OR_KEY,
         config.KEV_URL, config.KEV_KEY, config.USE_KEV, config.LLM_MODEL) = self._saved

    def memory_for(self, conn):
        return self.sessions.get(conn, {}).get("memory", [])

    def memory_sink(self, conn):
        if not hasattr(conn, "send_text"):
            return None
        conn_ref = conn
        def sink(op, arg):
            conn_ref.send_text({"type": "memory", "op": op, "text": arg})
        return sink

    def run_turn(self, conn, pcm, notify):
        import numpy as np
        audio = np.frombuffer(pcm, dtype="float32")
        with self.turn_lock:
            try:
                text, stt_ms = transcribe_text(audio, notify)
            except Exception as exc:
                print(f"\n  transcribe failed: {exc}")
                notify("Something went wrong", str(exc))
                return None
            if not text:
                notify("Ready", "Didn't catch anything")
                return None
            self._send_heard(conn, text)
            return self._execute_turn(conn, text, notify, stt_ms)

    def run_turn_text(self, conn, text, notify):
        with self.turn_lock:
            self._send_heard(conn, text)
            return self._execute_turn(conn, text, notify, None)

    @staticmethod
    def _send_heard(conn, text):
        if hasattr(conn, "send_text"):
            try:
                conn.send_text({"type": "heard", "text": text})
            except Exception:
                pass

    def _execute_turn(self, conn, text, notify, stt_ms):
        reply = {"wav": None}
        sess = self.sessions.get(conn, {})
        using_server_keys = not (sess.get("keys", {}) or {}).get("FISH_AUDIO_API_KEY")
        if using_server_keys:
            uses = int(sess.get("uses", 0))
            if uses >= SERVER_KEY_LIMIT:
                notify("Something went wrong",
                       f"Server key limit reached ({uses}/{SERVER_KEY_LIMIT}) — add your own keys in Settings")
                if hasattr(conn, "send_text"):
                    try:
                        conn.send_text({"type": "key-limit", "used": uses, "limit": SERVER_KEY_LIMIT})
                    except Exception:
                        pass
                return None
            sess["uses"] = uses + 1

        def remote_say(line, notify_cb):
            print(f"  say: {line}")
            notify_cb("Speaking", line)
            self._send_reply(conn, line)
            try:
                path, ms, cached = brain.fetch_tts(line)
                print(f"  tts {config.TTS_BACKEND} {'cached' if ms == 0 else str(ms) + 'ms'}")
                reply["wav"] = open(path, "rb").read()
            except Exception as exc:
                print(f"  tts failed: {exc}")
                notify_cb("Something went wrong", f"TTS failed: {exc}")

        self.begin_turn(conn)
        orig_say = brain.say
        brain.say = remote_say
        brain.MEMORY_SINK = self.memory_sink(conn)
        brain.MEMORY_CURRENT = self.memory_for(conn)
        brain.TURN_CANCEL["flag"] = False
        try:
            try:
                brain.handle(text, stt_ms, notify)
            except brain.TurnCancelled:
                print("\n  turn cancelled")
                notify("Ready", "Cancelled")
            except Exception as exc:
                print(f"\n  remote turn failed: {exc}")
                notify("Something went wrong", str(exc))
                try:
                    remote_say(brain.say_line("give_up"), notify)
                except Exception:
                    pass
        finally:
            brain.say = orig_say
            brain.MEMORY_SINK = None
            brain.MEMORY_CURRENT = []
            brain.TURN_CANCEL["flag"] = False
            self.end_turn(conn)
        if using_server_keys and hasattr(conn, "send_text"):
            try:
                conn.send_text({"type": "usage", "used": sess["uses"], "limit": SERVER_KEY_LIMIT})
            except Exception:
                pass
        return reply["wav"]

    def run_turn_replay(self, conn, line, notify):
        with self.turn_lock:
            notify("Speaking", line)
            self.begin_turn(conn)
            try:
                path, ms, cached = brain.fetch_tts(line)
                print(f"  replay {'cached' if ms == 0 else str(ms) + 'ms'}: {line!r}")
                return open(path, "rb").read()
            finally:
                self.end_turn(conn)

    @staticmethod
    def _send_reply(conn, line):
        if hasattr(conn, "send_text"):
            try:
                conn.send_text({"type": "reply", "line": line})
            except Exception:
                pass

    def serve_forever(self):
        handler = self._make_handler()
        httpd = ThreadingHTTPServer((self.host, self.port), handler)
        print(f"[remote] serving on http://{self.host}:{self.port} (front: {self.front})")
        httpd.serve_forever()

    def _make_handler(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype):
                http_send(self, code, body, ctype)

            def do_GET(self):
                if self.headers.get("Upgrade", "").lower() == "websocket":
                    accept = self._ws_key()
                    if not accept:
                        self._send(400, b"bad ws upgrade", "text/plain")
                        return
                    self.send_response(101, "Switching Protocols")
                    self.send_header("Upgrade", "websocket")
                    self.send_header("Connection", "Upgrade")
                    self.send_header("Sec-WebSocket-Accept", accept)
                    self.end_headers()
                    ws_loop(server, self.connection, self.client_address)
                    return
                if self.path in ("/", "/index.html"):
                    server._page(self, "index.html", "text/html; charset=utf-8")
                elif self.path == "/app.js":
                    server._page(self, "app.js", "text/javascript; charset=utf-8")
                elif self.path == "/worklet.js":
                    server._page(self, "worklet.js", "text/javascript; charset=utf-8")
                elif self.path == "/settings":
                    server._page(self, "settings.html", "text/html; charset=utf-8")
                elif self.path == "/health":
                    self._send(200, b"ok", "text/plain")
                elif self.path in ("/favicon.png", "/favicon.ico"):
                    try:
                        with open(FAVICON_PATH, "rb") as f:
                            self._send(200, f.read(), "image/png")
                    except OSError:
                        self._send(404, b"no icon", "text/plain")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length) if length else b""
                if self.path == "/turn":
                    server._turn_http(self, body)
                elif self.path == "/test-keys":
                    server._test_keys(self, body)
                else:
                    self._send(404, b"not found", "text/plain")

            def _ws_key(self):
                key = self.headers.get("Sec-WebSocket-Key")
                if not key:
                    return None
                return base64.b64encode(
                    hashlib.sha1((key + WS_GUID).encode()).digest()).decode()

        return Handler

    def _page(self, handler, name, ctype):
        try:
            with open(os.path.join(STATIC_DIR, name), "rb") as f:
                http_send(handler, 200, f.read(), ctype)
        except FileNotFoundError:
            http_send(handler, 404, f"missing web/{name}".encode(), "text/plain")

    def _test_keys(self, handler, body):
        try:
            payload = json.loads(body or b"{}")
        except Exception:
            http_send(handler, 400, b'{"ok":false,"detail":"bad json"}', "application/json")
            return
        keys = self._clean_keys(payload.get("keys"))
        token = payload.get("token")
        if not keys and not self.token_ok(token):
            http_send(handler, 200, b'{"ok":false,"detail":"bad token"}', "application/json")
            return
        sentinel = _Sentinel()
        self.sessions[sentinel] = {"keys": keys, "memory": []}
        self.begin_turn(sentinel)
        try:
            ok, detail = _ping_decision()
        finally:
            self.end_turn(sentinel)
            self.sessions.pop(sentinel, None)
        http_send(handler, 200, json.dumps({"ok": ok, "detail": detail}).encode(),
                  "application/json")

    def _turn_http(self, handler, body):
        auth = handler.headers.get("Authorization", "")
        if not self.token_ok(auth[7:].strip() if auth.startswith("Bearer ") else None):
            http_send(handler, 401, b"need Authorization: Bearer <token>", "text/plain")
            return
        keys = {}
        keys_hdr = handler.headers.get("X-Keys")
        if keys_hdr:
            try:
                keys = self._clean_keys(json.loads(base64.b64decode(keys_hdr)))
            except Exception:
                http_send(handler, 400, b"bad X-Keys", "text/plain")
                return
        conn = _Sentinel()
        uses_hdr = handler.headers.get("X-Uses")
        try:
            uses = max(0, int(uses_hdr))
        except (TypeError, ValueError):
            uses = 0
        self.sessions[conn] = {"keys": keys, "memory": [], "uses": min(uses, SERVER_KEY_LIMIT)}
        notify_events = []
        def notify(state, detail=""):
            notify_events.append({"state": state, "detail": detail})
        try:
            wav = self.run_turn(conn, body, notify)
        finally:
            self.sessions.pop(conn, None)
        if wav is None:
            wav = b""
        cost = brain.LAST_TURN_COST
        handler.send_response(200)
        handler.send_header("Content-Type", "audio/wav")
        handler.send_header("Content-Length", str(len(wav)))
        handler.send_header("X-Events", json.dumps(notify_events))
        handler.send_header("X-Cost", f"{cost.get('jev', 0) + cost.get('llm', 0):.6f}")
        handler.end_headers()
        handler.wfile.write(wav)


class _Sentinel:
    pass


def ws_loop(server, sock, addr):
    conn = WsConn(sock)
    server.sessions[conn] = {"keys": {}, "memory": [], "uses": 0, "ntfy": ""}
    server.web_clients.add(conn)
    audio_buf = bytearray()
    try:
        while True:
            opcode, payload = conn.recv()
            if opcode == 8:
                break
            if opcode == 1:
                msg = json.loads(payload)
                mtype = msg.get("type")
                if mtype == "auth":
                    keys = server._clean_keys(msg.get("keys"))
                    token = msg.get("token")
                    memory = [str(x)[:200] for x in (msg.get("memory") or [])][:50]
                    try:
                        uses = max(0, int(msg.get("uses", 0)))
                    except (TypeError, ValueError):
                        uses = 0
                    ok = server.token_ok(token) or bool(keys)
                    ntfy = str(msg.get("ntfy") or "").strip()
                    server.sessions[conn] = {"keys": keys if ok else {}, "memory": memory,
                                             "uses": min(uses, SERVER_KEY_LIMIT), "ntfy": ntfy}
                    conn.send_text({"type": "auth-ok" if ok else "auth-error",
                                    "detail": "" if ok else "bad token"})
                elif mtype == "ntfy-sync":
                    sess = server.sessions.get(conn)
                    if sess is not None:
                        sess["ntfy"] = str(msg.get("url") or "").strip()
                elif mtype == "memory-sync":
                    sess = server.sessions.get(conn)
                    if sess is not None and isinstance(msg.get("items"), list):
                        sess["memory"] = [str(x)[:200] for x in msg["items"]][:50]
                elif mtype == "audio-start":
                    audio_buf.clear()
                    server_notify(conn, "Listening", "Recording…")
                elif mtype == "audio-end":
                    if audio_buf:
                        server_notify(conn, "Transcribing", "Working out what you said…")
                        threading.Thread(target=_ws_turn, args=(server, conn, bytes(audio_buf)),
                                         daemon=True).start()
                elif mtype == "text":
                    text = (msg.get("text") or "").strip()
                    if text:
                        server_notify(conn, "Thinking", text)
                        threading.Thread(target=_ws_turn_text, args=(server, conn, text),
                                         daemon=True).start()
                elif mtype == "replay":
                    line = (msg.get("text") or "").strip()
                    if line:
                        threading.Thread(target=_ws_turn_replay, args=(server, conn, line),
                                         daemon=True).start()
                elif mtype == "timers":
                    try:
                        conn.send_text({"type": "timers",
                                        "timers": [[n, round(l, 1)] for n, l in brain.timer_snapshot()]})
                    except Exception:
                        pass
                elif mtype == "cancel":
                    brain.request_cancel()
                elif mtype == "tiles":
                    threading.Thread(target=_ws_tiles, args=(conn,), daemon=True).start()
                elif mtype == "weather-at":
                    threading.Thread(target=_ws_weather_at,
                                     args=(conn, msg.get("lat"), msg.get("lng")), daemon=True).start()
            elif opcode == 2:
                audio_buf.extend(payload)
    except (ConnectionError, OSError, json.JSONDecodeError):
        pass
    finally:
        server.web_clients.discard(conn)
        server.sessions.pop(conn, None)


def _ws_turn(server, conn, pcm):
    def notify(state, detail=""):
        try:
            conn.send_text({"type": "state", "state": state, "detail": detail})
        except Exception:
            pass
    _turn_common(server, lambda: server.run_turn(conn, pcm, notify), conn)


def _ws_turn_text(server, conn, text):
    def notify(state, detail=""):
        try:
            conn.send_text({"type": "state", "state": state, "detail": detail})
        except Exception:
            pass
    _turn_common(server, lambda: server.run_turn_text(conn, text, notify), conn)


def _ws_turn_replay(server, conn, line):
    def notify(state, detail=""):
        try:
            conn.send_text({"type": "state", "state": state, "detail": detail})
        except Exception:
            pass
    try:
        wav = server.run_turn_replay(conn, line, notify)
        if wav:
            conn.send_binary(wav)
    except Exception as exc:
        try:
            conn.send_text({"type": "state", "state": "Something went wrong", "detail": str(exc)})
        except Exception:
            pass
    try:
        conn.send_text({"type": "state", "state": "Ready", "detail": "Ready when you are"})
    except Exception:
        pass


def _turn_common(server, run, conn):
    try:
        wav = run()
        if wav:
            if hasattr(conn, "send_text"):
                try:
                    c = brain.LAST_TURN_COST
                    conn.send_text({"type": "cost", "jev": c.get("jev", 0),
                                    "llm": c.get("llm", 0),
                                    "total": c.get("jev", 0) + c.get("llm", 0)})
                except Exception:
                    pass
            conn.send_binary(wav)
        else:
            conn.send_text({"type": "state", "state": "Something went wrong",
                            "detail": "no reply audio (check Fish key / TTS cache)"})
    except Exception as exc:
        try:
            conn.send_text({"type": "state", "state": "Something went wrong", "detail": str(exc)})
        except Exception:
            pass
    try:
        conn.send_text({"type": "state", "state": "Ready", "detail": "Ready when you are"})
    except Exception:
        pass


def server_notify(conn, state, detail=""):
    try:
        conn.send_text({"type": "state", "state": state, "detail": detail})
    except Exception:
        pass


def _ping_decision():
    try:
        ans, ms, cost = config.jev("ping", {
            "category": {"type": "choice", "instructions": "What is this?",
                         "criteria": {"ping": "a test", "other": "anything else"}}})
        return True, f"decision backend answered in {ms}ms (${cost:.6f})"
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        return False, f"HTTP {code} from the decision backend — key wrong or expired"
    except Exception as e:
        return False, f"cannot reach the decision backend: {e}"


class _Whisper:
    _model = None
    _name = None
    _lock = threading.Lock()

    @classmethod
    def get(cls, notify, model_name=None):
        from faster_whisper import WhisperModel
        with cls._lock:
            if cls._model is None or (model_name and cls._name != model_name):
                print("loading whisper...")
                notify("Starting", "Loading Whisper…")
                cls._model = WhisperModel(model_name or config.WHISPER_MODEL, device="cpu",
                                          compute_type="int8")
                cls._name = model_name or config.WHISPER_MODEL
            return cls._model


def transcribe_text(audio_f32, notify):
    model_name, language = stt_spec()
    model = _Whisper.get(notify, model_name)
    t = time.time()
    segs, _ = model.transcribe(audio_f32, language=language, beam_size=1,
                               vad_filter=True, initial_prompt=config.COMMAND_PROMPT)
    text = " ".join(s.text.strip() for s in segs).strip()
    ms = int((time.time() - t) * 1000)
    print(f"\n> remote heard: {text!r}  (stt {ms}ms)")
    return text, ms


def stt_spec():
    """Platform hook: returns (model_name, language). Defaults to en-only."""
    if hasattr(config, "stt_spec_hook") and config.stt_spec_hook:
        return config.stt_spec_hook()
    return config.WHISPER_MODEL, "en"


def _ws_tiles(conn):
    try:
        conn.send_text({"type": "tiles", "tiles": brain.tiles_data()})
    except Exception:
        pass


def _ws_weather_at(conn, lat, lng):
    try:
        lat, lng = round(float(lat), 2), round(float(lng), 2)
        j = requests.get(f"https://wttr.in/~{lat},{lng}?format=j1",
                         headers={"User-Agent": "curl/8.0"}, timeout=10).json()
        cc = j["current_condition"][0]
        today = j["weather"][0]
        area = j.get("nearest_area", [{}])[0]
        weather = {"temp": cc["temp_C"], "desc": cc["weatherDesc"][0]["value"].strip().lower(),
                   "hi": today["maxtempC"], "lo": today["mintempC"],
                   "area": (area.get("areaName", [{"value": ""}])[0]["value"] or "your area")}
        conn.send_text({"type": "tile-weather", "weather": weather})
    except Exception as exc:
        try:
            conn.send_text({"type": "state", "state": "Ready",
                            "detail": f"location weather failed: {exc}"})
        except Exception:
            pass


class QuietHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        import sys
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
            return
        super().handle_error(request, client_address)


def serve():
    """Reads REMOTE_* env vars, builds the server and serves forever."""
    global _server
    port = int(os.getenv("REMOTE_PORT", "8765"))
    host = os.getenv("REMOTE_HOST", "0.0.0.0") or "0.0.0.0"
    front = os.getenv("REMOTE_FRONT", "none").strip().lower() or "none"
    tokens = [t.strip() for t in (os.getenv("REMOTE_TOKEN", "") + "," + os.getenv("REMOTE_TOKENS", "")).split(",") if t.strip()]
    scheme = {"npm": "https", "coolify": "https", "tunnel": "https"}.get(front, "http")
    server = RemoteServer(port, host, front, tokens)
    _server = server

    def remote_timer_done(t):
        try:
            siri_chime(t)
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

    brain.load_timers()
    brain.start_timer_loop(remote_timer_done)
    print(f"[remote] http://{host}:{port}  (front: {front})")
    if front in ("npm", "coolify", "tunnel"):
        print(f"[remote] open {scheme}://<your-front-host>/  (proxied to this port)")
    else:
        print(f"[remote] open http://<this-pc-ip>:{port}/  on a phone browser")
    if not server.tokens:
        print("[remote] REMOTE_TOKEN is empty — anyone on the network can use this")
    else:
        print(f"[remote] {len(server.tokens)} access token(s) active")
    QuietHTTPServer.allow_reuse_address = True
    httpd = QuietHTTPServer((host, port), server._make_handler())
    print(f"[remote] serving on http://{host}:{port} (front: {front})")
    httpd.serve_forever()


def siri_chime(t):
    """Platform timer chime — the platform layer sets config.chime_hook."""
    if hasattr(config, "chime_hook") and config.chime_hook:
        config.chime_hook()
