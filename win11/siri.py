"""Windows platform layer for hey-jev: ACTIONS, hooks, entry points.

The brain lives in shared/brain.py — this file wires the platform:
WASAPI volume (inline C#), registry dark mode, rundll32 lock/sleep,
pynput media keys, sounddevice playback, winsound chime.
"""
import argparse
import os
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

from shared import brain, config, tts

config.TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
config.CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
config.PERSONAS_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "personas")
config.PERSONA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persona.json")
config.PERSONAS_CATALOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "personas-catalog.json")
# shared/config.py's dotenv walk starts at shared/ and misses this platform's
# .env; re-read it so settings like TTS_BACKEND (read at config import) apply.
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"), override=True)
config.TTS_BACKEND = os.getenv("TTS_BACKEND", config.TTS_BACKEND)


def ps(script):
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                            capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"command failed: {script}")
    return result.stdout.strip()


def sh(*cmd):
    result = subprocess.run(list(cmd), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(cmd)}")


PS_AUDIO = r"""
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {
    int RegisterControlChangeNotify(IntPtr n);
    int UnregisterControlChangeNotify(IntPtr n);
    int GetChannelCount(out uint c);
    int SetMasterVolumeLevel(float l, Guid g);
    int SetMasterVolumeLevelScalar(float l, Guid g);
    int GetMasterVolumeLevel(out float l);
    int GetMasterVolumeLevelScalar(out float l);
    int SetChannelVolumeLevel(uint c, float l, Guid g);
    int SetChannelVolumeLevelScalar(uint c, float l, Guid g);
    int GetChannelVolumeLevel(uint c, out float l);
    int GetChannelVolumeLevelScalar(uint c, out float l);
    int SetMute(bool m, Guid g);
    int GetMute(out bool m);
}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {
    int Activate(ref Guid iid, uint cls, IntPtr p, out IAudioEndpointVolume o);
}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {
    int EnumAudioEndpoints(int d, int m, IntPtr o);
    int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice e);
}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")]
class MMDeviceEnumerator {}
public static class Vol {
    public static float Get() {
        var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        IMMDevice dev; e.GetDefaultAudioEndpoint(0, 1, out dev);
        Guid iid = typeof(IAudioEndpointVolume).GUID; IAudioEndpointVolume a;
        dev.Activate(ref iid, 1, IntPtr.Zero, out a);
        float v; a.GetMasterVolumeLevelScalar(out v); return v * 100f;
    }
    public static void Set(float pct) {
        var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        IMMDevice dev; e.GetDefaultAudioEndpoint(0, 1, out dev);
        Guid iid = typeof(IAudioEndpointVolume).GUID; IAudioEndpointVolume a;
        dev.Activate(ref iid, 1, IntPtr.Zero, out a);
        a.SetMasterVolumeLevelScalar(Math.Max(0f, Math.Min(100f, pct)) / 100f, Guid.Empty);
    }
    public static void Mute(bool m) {
        var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        IMMDevice dev; e.GetDefaultAudioEndpoint(0, 1, out dev);
        Guid iid = typeof(IAudioEndpointVolume).GUID; IAudioEndpointVolume a;
        dev.Activate(ref iid, 1, IntPtr.Zero, out a);
        a.SetMute(m, Guid.Empty);
    }
    public static bool IsMuted() {
        var e = (IMMDeviceEnumerator)new MMDeviceEnumerator();
        IMMDevice dev; e.GetDefaultAudioEndpoint(0, 1, out dev);
        Guid iid = typeof(IAudioEndpointVolume).GUID; IAudioEndpointVolume a;
        dev.Activate(ref iid, 1, IntPtr.Zero, out a);
        bool m; a.GetMute(out m); return m;
    }
}
'@
"""

def _ps_audio(op):
    return PS_AUDIO + f"\n[Vol]::{op}\n"


def volume():
    out = ps(_ps_audio("Get()"))
    try:
        return int(round(float(out)))
    except ValueError:
        raise RuntimeError(f"could not read volume: {out!r}")


def set_volume(pct):
    ps(_ps_audio(f"Set({float(pct)})"))


def set_mute(m):
    ps(_ps_audio(f"Mute({str(bool(m)).lower()})"))


def is_muted():
    return ps(_ps_audio("IsMuted()")).lower() == "true"


APPS = {
    "spotify": {"name": "Spotify", "process": "Spotify", "launch": ["explorer.exe", "spotify:"]},
    "slack": {"name": "Slack", "process": "slack", "launch": ["cmd", "/c", "start", "", "slack:"]},
    "chrome": {"name": "Google Chrome", "process": "chrome", "launch": ["cmd", "/c", "start", "", "chrome"]},
    "vscode": {"name": "Visual Studio Code", "process": "Code", "launch": ["cmd", "/c", "start", "", "vscode"]},
    "explorer": {"name": "File Explorer", "process": "explorer", "launch": ["explorer.exe"]},
    "edge": {"name": "Microsoft Edge", "process": "msedge", "launch": ["cmd", "/c", "start", "", "microsoft-edge:"]},
    "notepad": {"name": "Notepad", "process": "notepad", "launch": ["notepad.exe"]},
    "terminal": {"name": "Terminal", "process": "WindowsTerminal", "launch": ["cmd", "/c", "start", "", "wt:"]},
}
LEVELS = {"silent": 0, "quiet": 25, "medium": 50, "loud": 75, "max": 100}

from pynput import keyboard
MEDIA_KEYS = {
    "media_play": keyboard.Key.media_play_pause,
    "media_pause": keyboard.Key.media_play_pause,
    "media_next": keyboard.Key.media_next,
    "media_previous": keyboard.Key.media_previous,
}
PTT_KEY = keyboard.Key.alt_r


def process_running(proc):
    out = ps(f"(Get-Process -Name '{proc}' -ErrorAction SilentlyContinue | Measure-Object).Count")
    try:
        return int(out) > 0
    except ValueError:
        return False


def open_app(key, wait=6.0):
    app = APPS[key]
    sh(*app["launch"])
    t = time.time()
    while time.time() - t < wait and not process_running(app["process"]):
        time.sleep(0.3)


def press_media(key_name):
    k = MEDIA_KEYS[key_name]
    kb = keyboard.Controller()
    kb.press(k)
    kb.release(k)
    time.sleep(0.4)


def set_dark_mode(on):
    base = r"HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    val = "0" if on else "1"
    ps(f"Set-ItemProperty -Path '{base}' -Name AppsUseLightTheme -Value {val}; "
       f"Set-ItemProperty -Path '{base}' -Name SystemUsesLightTheme -Value {val}")
    ps("""
$sig = '[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);'
$t = Add-Type -MemberDefinition $sig -Name Win32SMT -Namespace W -PassThru
$r = [UIntPtr]::Zero
$t::SendMessageTimeout([IntPtr]0xffff, 0x001A, [UIntPtr]::Zero, 'ImmersiveColorSet', 2, 500, [ref]$r) | Out-Null
""")


def dark_mode_on():
    out = ps("(Get-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize').SystemUsesLightTheme")
    return out.strip() == "0"


ACTIONS = {
    "app_open": lambda a: open_app(a),
    "app_quit": lambda a: ps(f"Stop-Process -Name '{APPS[a]['process']}' -Force -ErrorAction SilentlyContinue; Start-Sleep -Milliseconds 300"),
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
    "media_play": lambda _: press_media("media_play"),
    "media_pause": lambda _: press_media("media_pause"),
    "media_next": lambda _: press_media("media_next"),
    "media_previous": lambda _: press_media("media_previous"),
    "system_lock": lambda _: sh("rundll32.exe", "user32.dll,LockWorkStation"),
    "system_sleep": lambda _: sh("rundll32.exe", "powrprof.dll,SetSuspendState 0,1,0"),
}


def machine_context():
    try:
        return ps(r'''
$os = Get-CimInstance Win32_OperatingSystem
$up = (Get-Date) - $os.LastBootUpTime
$cpu = (Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
$bat = Get-CimInstance Win32_Battery | Select-Object -First 1
$apps = (Get-Process Spotify,slack,chrome,Code,msedge,WindowsTerminal -ErrorAction SilentlyContinue | Group-Object Name | ForEach-Object Name) -join ','
"host=$env:COMPUTERNAME; os=$($os.Caption); up=$([int]$up.TotalHours)h$($up.Minutes)m; cpu=$(if ($null -ne $cpu) { [string]$cpu } else { '?' })%; ram=$([math]::Round($os.FreePhysicalMemory/1MB,1))/$([math]::Round($os.TotalVisibleMemorySize/1MB,1))GB free; diskC=$([math]::Round((Get-PSDrive C).Free/1GB))GB free; battery=$(if ($bat) { [string][math]::Round($bat.EstimatedChargeRemaining*100) + '%' } else { 'n/a (desktop) or none' }); running=$apps"
''')
    except Exception as e:
        return f"(machine status unavailable: {e})"


def chime():
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
    except Exception:
        pass


# wire hooks into config
config.machine_context_hook = machine_context
config.chime_hook = chime
config.APPS = APPS
config.ACTIONS = ACTIONS


def play_wav(path):
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    sd.play(data, sr)
    sd.wait()

config.play_wav_hook = play_wav

def pick_input():
    if sd.default.device[0] != -1:
        return None
    devices = sd.query_devices()
    mics = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    named = [i for i in mics if "microphone" in devices[i]["name"].lower()]
    pick = (named or mics)[0] if (named or mics) else None
    if pick is not None:
        print(f"[mic] no default input device set on Windows — using "
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


def run_voice_assistant(notify=None, controls=None, mode="ptt", device=None):
    from faster_whisper import WhisperModel
    print("loading whisper...")
    brain.emit(notify, "Starting", "Loading Whisper…")
    model = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
    brain.load_timers()
    rec = Recorder(device=device)
    busy = threading.Lock()
    armed_until = [0.0]

    def transcribe(audio, prompt):
        t = time.time()
        segs, _ = model.transcribe(audio, language="en", beam_size=1, vad_filter=True, initial_prompt=prompt)
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

    def on_press(key):
        if key == PTT_KEY:
            start_recording()

    def on_release(key):
        if key == PTT_KEY:
            stop_recording()

    with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
        l.join()


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

