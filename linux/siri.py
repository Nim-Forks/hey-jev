"""Linux platform layer for hey-jev: ACTIONS, hooks, entry points.

The brain lives in shared/brain.py — this file wires the platform:
pactl volume/mute, playerctl media, gsettings dark mode, loginctl lock,
systemctl suspend, desktop-id app launches.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import subprocess
import threading
import time

from dotenv import load_dotenv

from shared import brain, config, tts

config.TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
config.CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
config.PERSONAS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "personas")
config.PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")
# parity with win11: re-read the platform .env (linux keeps its .env at the
# checkout root, which shared/config.py already finds; this is a no-op there
# unless a linux/.env exists).
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
config.TTS_BACKEND = os.getenv("TTS_BACKEND", config.TTS_BACKEND)


def sh(*cmd):
    result = subprocess.run(list(cmd), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(cmd)}")
    return result.stdout.strip()


def _sink():
    return "@DEFAULT_SINK@"


def volume():
    out = sh("pactl", "get-sink-volume", _sink())
    m = re.search(r"(\d+)%", out)
    if not m:
        raise RuntimeError(f"could not read volume: {out!r}")
    return int(m.group(1))


def set_volume(pct):
    sh("pactl", "set-sink-volume", _sink(), f"{int(max(0, min(100, pct)))}%")


def set_mute(m):
    sh("pactl", "set-sink-mute", _sink(), "1" if m else "0")


def is_muted():
    return sh("pactl", "get-sink-mute", _sink()).strip().lower() == "muted: yes"


APPS = {
    "spotify": {"name": "Spotify", "process": "spotify", "launch": ["sh", "-c", "gtk-launch spotify >/dev/null 2>&1 || xdg-open spotify:"]},
    "slack": {"name": "Slack", "process": "slack", "launch": ["sh", "-c", "gtk-launch slack >/dev/null 2>&1 || xdg-open slack:"]},
    "chrome": {"name": "Google Chrome", "process": "chrome", "launch": ["sh", "-c", "gtk-launch google-chrome >/dev/null 2>&1 || xdg-open https://www.google.com"]},
    "vscode": {"name": "Visual Studio Code", "process": "code", "launch": ["sh", "-c", "gtk-launch code >/dev/null 2>&1 || code"]},
    "explorer": {"name": "Files", "process": "nautilus", "launch": ["sh", "-c", "gtk-launch org.gnome.Nautilus >/dev/null 2>&1 || xdg-open ~"]},
    "edge": {"name": "Microsoft Edge", "process": "msedge", "launch": ["sh", "-c", "gtk-launch microsoft-edge >/dev/null 2>&1 || xdg-open https://www.bing.com"]},
    "notepad": {"name": "Text Editor", "process": "gedit", "launch": ["sh", "-c", "gtk-launch org.gnome.gedit >/dev/null 2>&1 || gedit"]},
    "terminal": {"name": "Terminal", "process": "x-terminal-emulator", "launch": ["x-terminal-emulator"]},
}
LEVELS = {"silent": 0, "quiet": 25, "medium": 50, "loud": 75, "max": 100}


def process_running(proc):
    r = subprocess.run(["pgrep", "-x", proc], capture_output=True)
    return r.returncode == 0


def open_app(key, wait=6.0):
    app = APPS[key]
    sh(*app["launch"])
    t = time.time()
    while time.time() - t < wait and not process_running(app["process"]):
        time.sleep(0.3)


def press_media(action):
    sh("playerctl", action)
    time.sleep(0.4)


def spotify_running():
    return process_running("spotify")


def set_dark_mode(on):
    sh("gsettings", "set", "org.gnome.desktop.interface", "color-scheme",
       "prefer-dark" if on else "prefer-light")


def dark_mode_on():
    out = sh("gsettings", "get", "org.gnome.desktop.interface", "color-scheme")
    return "dark" not in out


ACTIONS = {
    "app_open": lambda a: open_app(a),
    "app_quit": lambda a: subprocess.run(["pkill", "-x", APPS[a]["process"]]),
    "volume_up": lambda _: set_volume(min(100, volume() + 20)),
    "volume_down": lambda _: set_volume(max(0, volume() - 20)),
    "volume_mute": lambda _: set_mute(True),
    "volume_unmute": lambda _: set_mute(False),
    "volume_set": lambda lvl: set_volume(LEVELS.get(lvl, 50)),
    "spotify_volume_up": lambda _: set_volume(min(100, volume() + 20)),
    "spotify_volume_down": lambda _: set_volume(max(0, volume() - 20)),
    "spotify_volume_mute": lambda _: set_mute(True),
    "spotify_volume_unmute": lambda _: set_mute(False),
    "spotify_volume_set": lambda lvl: set_volume(LEVELS.get(lvl, 50)),
    "display_dark_on": lambda _: set_dark_mode(True),
    "display_dark_off": lambda _: set_dark_mode(False),
    "display_toggle": lambda _: set_dark_mode(not dark_mode_on()),
    "media_play": lambda _: press_media("play-pause"),
    "media_pause": lambda _: press_media("play-pause"),
    "media_next": lambda _: press_media("next"),
    "media_previous": lambda _: press_media("previous"),
    "system_lock": lambda _: sh("loginctl", "lock-session"),
    "system_sleep": lambda _: sh("systemctl", "suspend"),
}


def machine_context():
    try:
        import socket
        import glob
        up_s = float(open("/proc/uptime").read().split()[0])
        load1 = open("/proc/loadavg").read().split()[0]
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k.strip()] = int(v.strip().split()[0])
        ram = f"{mem['MemAvailable'] / 1048576:.1f}/{mem['MemTotal'] / 1048576:.1f}GB free"
        df = subprocess.run(["df", "-BG", "/"], capture_output=True, text=True).stdout
        disk_free = df.splitlines()[-1].split()[3]
        bat = None
        for b in glob.glob("/sys/class/power_supply/BAT*/capacity"):
            bat = open(b).read().strip() + "%"
            break
        apps = []
        for label, proc in (("Spotify", "spotify"), ("Chrome", "chrome"),
                            ("VS Code", "code"), ("Firefox", "firefox")):
            if process_running(proc):
                apps.append(label)
        out = (f"host={socket.gethostname()}; os=Debian Linux; "
               f"up={int(up_s // 3600)}h{int(up_s % 3600 // 60)}m; load={load1}; "
               f"ram={ram}; disk/={disk_free} free; battery={bat or 'n/a'}; "
               f"running={','.join(apps) or 'none'}")
    except Exception as e:
        return f"(machine status unavailable: {e})"
    return out


def chime():
    for f in ("/usr/share/sounds/freedesktop/stereo/complete.oga",
              "/usr/share/sounds/freedesktop/stereo/bell.oga"):
        if os.path.exists(f):
            subprocess.run(["paplay", f], capture_output=True)
            return
    print("\a", end="", flush=True)


def play_wav(path):
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    sd.play(data, sr)
    sd.wait()


# wire hooks into config
config.machine_context_hook = machine_context
config.play_wav_hook = play_wav
config.APPS = APPS
config.ACTIONS = ACTIONS


def pick_input():
    if sd.default.device[0] != -1:
        return None
    devices = sd.query_devices()
    ins = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    mics = [i for i in ins if "monitor" not in devices[i]["name"].lower()]
    named = [i for i in mics if "mic" in devices[i]["name"].lower() or "input" in devices[i]["name"].lower()]
    pick = (named or mics or ins)[0] if (named or mics or ins) else None
    if pick is not None:
        print(f"[mic] no default input device set — using "
              f"{pick}: {devices[pick]['name']!r} (override with --device)")
    return pick


class Recorder:
    BLOCK = 1600

    def __init__(self, device=None):
        import numpy as np
        import queue
        import sounddevice as sd
        import collections
        self.np = np
        self.frames, self.on = [], False
        self.wake, self.paused = False, False
        self.segments = queue.Queue()
        self.noise = 0.005
        self._reset_segment()
        self.stream = sd.InputStream(samplerate=config.SAMPLE_RATE, channels=1, dtype="float32",
                                     blocksize=self.BLOCK, callback=self._cb,
                                     device=device if device is not None else pick_input())
        self.stream.start()

    def _reset_segment(self):
        self.speech, self.silent = [], 0
        import collections
        self.preroll = collections.deque(maxlen=3)

    def _cb(self, indata, *_):
        np = self.np
        if self.on:
            self.frames.append(indata.copy())
        if not self.wake or self.paused:
            if self.speech:
                self._reset_segment()
            return
        block = indata[:, 0].copy()
        rms = float(np.sqrt(np.mean(block ** 2)))
        loud = rms > max(self.noise * 3, 0.01)
        if not self.speech:
            if loud:
                self.speech, self.silent = list(self.preroll) + [block], 0
            else:
                self.noise = 0.95 * self.noise + 0.05 * rms
                self.preroll.append(block)
            return
        self.speech.append(block)
        self.silent = 0 if loud else self.silent + 1
        if self.silent >= 8 or len(self.speech) >= 150:
            if len(self.speech) - self.silent >= 4:
                self.segments.put(np.concatenate(self.speech))
            self._reset_segment()

    def start(self):
        self.frames, self.on = [], True

    def stop(self):
        self.on = False
        np = self.np
        return np.concatenate(self.frames)[:, 0] if self.frames else np.zeros(0, dtype="float32")


def ready_text(wake):
    return "Say \u201cHey Jev\u201d and your command" if wake else "Ready when you are"


try:
    from pynput import keyboard
    PTT_KEY = keyboard.Key.alt_r
except Exception:
    keyboard = None
    PTT_KEY = None


def run_voice_assistant(notify=None, controls=None, mode="ptt", device=None):
    from faster_whisper import WhisperModel
    print("loading whisper...")
    brain.emit(notify, "Starting", "Loading Whisper…")
    model_name, language = _stt_spec()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    brain.load_timers()
    rec = Recorder(device=device)
    busy = threading.Lock()
    armed_until = [0.0]

    def transcribe(audio, prompt):
        t = time.time()
        segs, _ = model.transcribe(audio, language=language, beam_size=1, vad_filter=True, initial_prompt=prompt)
        return " ".join(s.text.strip() for s in segs).strip(), int((time.time() - t) * 1000)

    def run_turn(text, stt_ms):
        with busy:
            rec.paused = True
            try:
                brain.handle(text, stt_ms, notify)
            except Exception as exc:
                print(f"\n  turn failed: {exc}")
                brain.emit(notify, "Something went wrong", str(exc))
                time.sleep(2)
                brain.emit(notify, "Ready", ready_text(rec.wake))
            finally:
                time.sleep(0.3)
                rec.paused = False

    def ptt_turn(audio):
        brain.emit(notify, "Transcribing", "Working out what you said…")
        try:
            text, ms = transcribe(audio, config.COMMAND_PROMPT)
        except Exception as exc:
            brain.emit(notify, "Something went wrong", str(exc))
            return
        run_turn(text, ms)

    def wake_loop():
        while True:
            try:
                audio = rec.segments.get(timeout=1)
            except queue.Empty:
                if armed_until[0] and time.time() > armed_until[0]:
                    armed_until[0] = 0
                    brain.emit(notify, "Ready", ready_text(rec.wake))
                continue
            if not rec.wake or busy.locked():
                continue
            try:
                text, ms = transcribe(audio, config.WAKE_PROMPT)
            except Exception as exc:
                print(f"\n  transcribe failed: {exc}")
                continue
            m = config.WAKE.match(text)
            if m:
                rest = text[m.end():].strip(" .,!?")
                if rest:
                    armed_until[0] = 0
                    run_turn(rest, ms)
                else:
                    with busy:
                        rec.paused = True
                        brain.say(say_line("wake"), notify)
                        time.sleep(0.2)
                        rec.paused = False
                    armed_until[0] = time.time() + config.WAKE_WINDOW
                    brain.emit(notify, "Listening", "Go ahead…")
            elif armed_until[0] and time.time() < armed_until[0]:
                armed_until[0] = 0
                run_turn(text, ms)
            elif text:
                print(f"\n  (not for me: {text!r})")

    def set_mode(new):
        rec.wake = new == "wake"
        armed_until[0] = 0
        print(f"\n[mode: {'always listening' if rec.wake else 'hold right Alt'}]")
        if not busy.locked():
            brain.emit(notify, "Ready", ready_text(rec.wake))

    def start_recording():
        if not rec.wake and not rec.on and not busy.locked():
            rec.start()
            print("\n[listening]", end="", flush=True)
            brain.emit(notify, "Listening", "Release right Alt when you\u2019re done")

    def stop_recording():
        if rec.on:
            audio = rec.stop()
            if len(audio) > config.SAMPLE_RATE * 0.3:
                threading.Thread(target=ptt_turn, args=(audio,), daemon=True).start()

    def timer_done(t):
        with busy:
            rec.paused = True
            try:
                brain.emit(notify, "Time's up", t["label"] or "Timer finished")
                chime()
                brain.say(brain.timer_done_line(t), notify)
            finally:
                time.sleep(0.3)
                rec.paused = False
        brain.emit(notify, "Ready", ready_text(rec.wake))

    brain.start_timer_loop(timer_done)
    threading.Thread(target=brain.warm_cache, daemon=True).start()
    threading.Thread(target=wake_loop, daemon=True).start()
    set_mode(mode)
    print("ready. ctrl+c to quit.")
    if controls is not None:
        while True:
            command = controls.get()
            if isinstance(command, tuple) and command[0] == "mode":
                set_mode(command[1])
            elif command == "press":
                start_recording()
            elif command == "release":
                stop_recording()

    if rec.wake:
        threading.Event().wait()

    if keyboard is not None:
        def on_press(key):
            if key == PTT_KEY:
                start_recording()

        def on_release(key):
            if key == PTT_KEY:
                stop_recording()

        with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
            l.join()
    else:
        print("[ptt] no keyboard listener (headless) — use --wake or the web remote")
        threading.Event().wait()


def _stt_spec():
    if config.WHISPER_LANGUAGES - {"en"}:
        return "small", None
    return config.WHISPER_MODEL, "en"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="skip the mic, run one turn on this transcript")
    ap.add_argument("--ui", action="store_true", help="show the floating status window (X11)")
    ap.add_argument("--wake", action="store_true", help="always listening")
    ap.add_argument("--remote", action="store_true", help="serve the browser mic/PTT remote")
    ap.add_argument("--device", help="input device name/index for the mic")
    ap.add_argument("--list-devices", action="store_true", help="print audio devices and exit")
    args = ap.parse_args()
    if args.list_devices:
        import sounddevice as _sd
        print(_sd.query_devices())
        return
    device = None
    if args.device:
        try:
            device = int(args.device)
        except ValueError:
            device = args.device
    if args.ui:
        from assistant_ui import run_app
        run_app()
        return
    if args.remote:
        problems = tts.validate_startup()
        if problems:
            sys.exit("\n".join(problems))
        import remote
        remote.run_remote()
        return
    if config.TTS_BACKEND == "fish" and not config.FISH_KEY:
        sys.exit("need FISH_AUDIO_API_KEY in Credential Manager or .env "
                 "(or set TTS_BACKEND=chatterbox for the local voice)")
    if config.decision_backend() is None:
        sys.exit("need a decision backend in Credential Manager or .env: "
                 "TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
    problems = tts.validate_startup()
    if problems:
        sys.exit("\n".join(problems))
    if args.text:
        brain.handle(args.text)
        return
    run_voice_assistant(mode="wake" if args.wake else "ptt", device=device)


def say_line(key, **fmt):
    return brain.say_line(key, **fmt)

if __name__ == '__main__':
    main()

