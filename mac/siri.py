"""macOS platform layer for hey-jev: ACTIONS, hooks, entry points.

The brain lives in shared/brain.py — this file wires the platform:
osascript app/volume/media/dark-mode commands, afplay playback,
Keychain secrets, AppKit UI (assistant_ui.py).

**Untested** — no Mac available. The action layer was copied from the
original root siri.py (which was tested on macOS Sequoia/Tahoe).
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import argparse
import random
import threading
import time

from shared import brain, config

config.TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
config.CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")

# ------------------------------------------------------------------- macOS helpers

def osa(script):
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "AppleScript failed")
    return result.stdout.strip()


def sh(*cmd):
    result = subprocess.run(list(cmd), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(cmd)}")
    return result.stdout.strip()


APPS = {
    "spotify": {"name": "Spotify", "process": "Spotify", "launch": ["open", "-a", "Spotify"]},
    "slack": {"name": "Slack", "process": "Slack", "launch": ["open", "-a", "Slack"]},
    "chrome": {"name": "Google Chrome", "process": "Google Chrome", "launch": ["open", "-a", "Google Chrome"]},
    "vscode": {"name": "Visual Studio Code", "process": "Code", "launch": ["open", "-a", "Visual Studio Code"]},
    "explorer": {"name": "Finder", "process": "Finder", "launch": ["open", "-a", "Finder"]},
    "edge": {"name": "Microsoft Edge", "process": "Microsoft Edge", "launch": ["open", "-a", "Microsoft Edge"]},
    "notepad": {"name": "Notes", "process": "Notes", "launch": ["open", "-a", "Notes"]},
    "terminal": {"name": "Terminal", "process": "Terminal", "launch": ["open", "-a", "Terminal"]},
}
LEVELS = {"silent": 0, "quiet": 25, "medium": 50, "loud": 75, "max": 100}


def process_running(proc):
    r = osa(f'application "{proc}" is running')
    return r == "true"


def open_app(key, wait=5.0):
    app = APPS[key]
    sh("open", "-a", APPS[key]["name"])
    t = time.time()
    while time.time() - t < wait and not process_running(APPS[key]["name"]):
        time.sleep(0.2)


def spotify_volume():
    return int(osa('tell application "Spotify" to get sound volume'))


def spotify_play(tries=12):
    for _ in range(tries):
        osa('tell application "Spotify" to play')
        time.sleep(0.5)
        if osa('tell application "Spotify" to player state') == "playing":
            return
    raise RuntimeError("Spotify never started playing")


def press_media(key_name):
    if key_name == "media_play":
        osa('tell application "Spotify" to play')
    elif key_name == "media_pause":
        osa('tell application "Spotify" to pause')
    elif key_name == "media_next":
        osa('tell application "Spotify" to next track')
    elif key_name == "media_previous":
        osa('tell application "Spotify" to previous track')
    time.sleep(0.4)


def volume():
    return int(osa("output volume of (get volume settings)"))


def set_volume(pct):
    osa(f"set volume output volume {int(max(0, min(100, pct)))}")


def set_mute(m):
    osa(f"set volume output muted {'true' if m else 'false'}")


def is_muted():
    return osa("output muted of (get volume settings)") == "true"


def set_dark_mode(on):
    osa(f'tell application "System Events" to tell appearance preferences to set dark mode to {str(on).lower()}')


def dark_mode_on():
    return osa('tell application "System Events" to tell appearance preferences to get dark mode') == "true"


ACTIONS = {
    "app_open": lambda a: open_app(a),
    "app_quit": lambda a: osa(f'tell application "{APPS[a]["name"]}" to quit'),
    "volume_up": lambda _: osa(f"set volume output volume {min(100, volume() + 20)}"),
    "volume_down": lambda _: osa(f"set volume output volume {max(0, volume() - 20)}"),
    "volume_mute": lambda _: osa("set volume output muted true"),
    "volume_unmute": lambda _: osa("set volume output muted false"),
    "volume_set": lambda lvl: osa(f"set volume output volume {LEVELS.get(lvl, 50)}"),
    "spotify_volume_up": lambda _: osa(f'tell application "Spotify" to set sound volume to {min(100, spotify_volume() + 20)}'),
    "spotify_volume_down": lambda _: osa(f'tell application "Spotify" to set sound volume to {max(0, spotify_volume() - 20)}'),
    "spotify_volume_mute": lambda _: osa('tell application "Spotify" to set sound volume to 0'),
    "spotify_volume_unmute": lambda _: osa('tell application "Spotify" to set sound volume to 50'),
    "spotify_volume_set": lambda lvl: osa(f'tell application "Spotify" to set sound volume to {LEVELS.get(lvl, 50)}'),
    "display_dark_on": lambda _: set_dark_mode(True),
    "display_dark_off": lambda _: set_dark_mode(False),
    "display_toggle": lambda _: set_dark_mode(not dark_mode_on()),
    "media_play": lambda _: spotify_play(),
    "media_pause": lambda _: press_media("media_pause"),
    "media_next": lambda _: press_media("media_next"),
    "media_previous": lambda _: press_media("media_previous"),
    "system_lock": lambda _: osa('tell application "System Events" to keystroke "q" using {control down, command down}'),
    "system_sleep": lambda _: sh("pmset", "sleepnow"),
}


def machine_context():
    try:
        host = osa("do shell script 'hostname -s'")
        uptime = osa("do shell script 'uptime | sed \\'s/.*up//; s/,.*//\\''")
        ram = osa("do shell script 'sysctl -n hw.memsize | awk \\'{print $1/1073741824 \\\"GB\\\"}\\''")
        battery = osa("pmset -g batt | grep -o '[0-9]*%' | head -1") if "laptop" in osa(
            "do shell script 'sysctl -n hw.model'") else "n/a"
        out = f"host={host}; os=macOS; up={uptime.strip()}; ram={ram}; battery={battery or 'n/a'}"
    except Exception as e:
        return f"(machine status unavailable: {e})"
    return out


def chime():
    subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], capture_output=True)


def play_wav(path):
    subprocess.run(["afplay", path], capture_output=True)


# wire hooks into config
config.machine_context_hook = machine_context
config.play_wav_hook = play_wav
config.chime_hook = chime
config.APPS = {k: {"name": v["name"]} for k, v in APPS.items()}
config.ACTIONS = ACTIONS


# ------------------------------------------------------------------- STT (mic + push to talk)

def pick_input():
    return None  # macOS handles default input via CoreAudio


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
    model_name, language = stt_spec()
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
        print(f"\n[mode: {'always listening' if rec.wake else 'hold right Option'}]")
        if not busy.locked():
            brain.emit(notify, "Ready", ready_text(rec.wake))

    def start_recording():
        if not rec.wake and not rec.on and not busy.locked():
            rec.start()
            print("\n[listening]", end="", flush=True)
            brain.emit(notify, "Listening", "Release right Option when you\u2019re done")

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
        print("[ptt] no keyboard listener — use --wake or the web remote")
        threading.Event().wait()


def stt_spec():
    if config.WHISPER_LANGUAGES - {"en"}:
        return "small", None
    return config.WHISPER_MODEL, "en"


def say_line(key, **fmt):
    return brain.say_line(key, **fmt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="skip the mic, run one turn on this transcript")
    ap.add_argument("--ui", action="store_true", help="show the floating status window (tray icon)")
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
        import remote
        remote.run_remote()
        return
    if not config.FISH_KEY:
        sys.exit("need FISH_AUDIO_API_KEY in Keychain or .env")
    if config.decision_backend() is None:
        sys.exit("need a decision backend in Keychain or .env: "
                 "TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
    if args.text:
        brain.handle(args.text)
        return
    run_voice_assistant(mode="wake" if args.wake else "ptt", device=device)


def say_line(key, **fmt):
    return brain.say_line(key, **fmt)


if __name__ == "__main__":
    main()
