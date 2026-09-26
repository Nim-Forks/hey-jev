"""Linux port of the Hey Jev voice assistant (Debian/PipeWire): web remote + optional local PTT.

Same brain as the Windows port (../win11/siri.py): Jev/KEV/OpenRouter
decisions, Fish TTS, faster-whisper STT, timers/alarms persisted, memory
skills, free-API skills, LLM fallback with Jev-gated context. The action
layer is Linux-native: pactl volume, playerctl media, gsettings dark mode,
loginctl lock, systemctl suspend, desktop launches. Remote web server
included (--remote) — the primary interface on headless boxes.
"""
import os, re, sys, json, time, queue, random, argparse, subprocess, tempfile, threading, hashlib, collections
import urllib.parse
import numpy as np, requests, sounddevice as sd, soundfile as sf
from dotenv import load_dotenv
try:
    from pynput import keyboard  # X11 only; headless boxes use the web remote
except Exception:
    keyboard = None
from secrets_store import get_secret

load_dotenv()
TS_KEY = get_secret("TYPESAFE_API_KEY")
FISH_KEY = get_secret("FISH_AUDIO_API_KEY")
OR_KEY = get_secret("OPENROUTER_API_KEY")
# KEV: a self-hosted Jev-compatible decision backend. If both vars are set,
# decisions go to KEV instead of the Typesafe cloud (same wire contract).
KEV_URL = os.getenv("KEV_URL", "").strip().rstrip("/")
KEV_KEY = os.getenv("KEV_API_KEY", "").strip()
USE_KEV = bool(KEV_URL and KEV_KEY)
VOICE_ID = "9a9cf47702da476aa4629e2506d4a857"
PTT_KEY = keyboard.Key.alt_r if keyboard is not None else None
SAMPLE_RATE = 16000
# Confidence gate. KEV deployments answer correctly but run hot (small model,
# high temperature) — correct answers often land 0.45-0.62 — so the default
# gate drops to 0.45 when KEV is active. Override with JEV_GATE.
GATE = float(os.getenv("JEV_GATE", "0.45" if USE_KEV else "0.65"))
WHISPER_MODEL = "small.en"
# Extra STT languages (comma list in WHISPER_LANGUAGES, e.g. "en,hr,de").
# Non-English entries switch to the multilingual 'small' model when it is
# cached (installed by install.sh); Whisper auto-detects the spoken language.
WHISPER_LANGUAGES = frozenset(
    x.strip().lower() for x in os.getenv("WHISPER_LANGUAGES", "en").split(",") if x.strip())
MULTILINGUAL_MODEL = "small"
COMMAND_PROMPT = "Open Spotify. Set a timer for five minutes. Play. Pause. Next track. Turn Spotify down. Turn the volume down. Mute. Dark mode on. Lock the screen."
WAKE_PROMPT = "Hey Jev, open Spotify. Hey Jev, pause the music. Hey Jev, turn the volume down."
# Whisper often hears "Jev" as Jeff or Jeb, so accept the close ones
WAKE = re.compile(r"^\W*(?:hey|hi|hay|okay|ok|a)\W+(?:jev|jevs|jeff|jeffs|jef|jeb|jab|chev|jeve|jav)\b\W*", re.I)
WAKE_WINDOW = 6.0


def reload_keys():
    global TS_KEY, FISH_KEY, OR_KEY, KEV_URL, KEV_KEY, USE_KEV
    TS_KEY = get_secret("TYPESAFE_API_KEY")
    FISH_KEY = get_secret("FISH_AUDIO_API_KEY")
    OR_KEY = get_secret("OPENROUTER_API_KEY")
    KEV_URL = os.getenv("KEV_URL", "").strip().rstrip("/")
    KEV_KEY = os.getenv("KEV_API_KEY", "").strip()
    USE_KEV = bool(KEV_URL and KEV_KEY)

# --------------------------------------------------------------------------- Jev
QUESTIONS = {
    "category": {"type": "choice", "instructions": "What kind of request is this?",
                 "criteria": {"pc_command": "asks the computer to do something",
                              "information_request": "asks a general knowledge or factual question",
                              "chit_chat": "just talking, greeting, or thanking",
                              "unclear": "garbled, empty, or makes no sense"}},
    "compound": {"type": "noul", "instructions": "Does the request contain more than one distinct action?"},
    "target": {"type": "choice", "instructions": "What is the primary thing being controlled?",
               "criteria": {"app": "an application", "volume": "sound level", "display": "screen appearance or dark mode",
                            "media": "music playback", "system": "locking or sleeping the computer",
                            "timer": "setting, checking, or cancelling a timer or reminder"}},
    "app": {"type": "choice", "instructions": "Which app, if any, is named?",
            "criteria": {"spotify": None, "slack": None, "chrome": None, "vscode": None, "explorer": None,
                         "edge": None, "notepad": None, "terminal": None, "none": None}},
    "app_action": {"type": "choice", "instructions": "What should happen to the app?",
                   "criteria": {"open": "open, launch, or start the app itself", "quit": "quit, close, or kill the app",
                                "none": "the request is about playback, volume, or something inside the app, not opening or quitting it"}},
    "volume_action": {"type": "choice", "instructions": "What should happen to the volume, if anything?",
                      "criteria": {"up": None, "down": None, "mute": None, "unmute": None,
                                   "set": "set to a specific level", "none": None}},
    "volume_scope": {"type": "choice", "instructions": "Which volume should change?",
                     "criteria": {"spotify": "Spotify's own in-app volume when Spotify is explicitly named (unsupported on Windows, maps to system)",
                                  "system": "the PC's overall output volume, including unqualified volume requests"}},
    "volume_level": {"type": "score", "instructions": "If a volume level is asked for, how loud?",
                     "criteria": ["silent", "quiet", "medium", "loud", "max"]},
    "display_action": {"type": "choice", "instructions": "What should happen to dark mode?",
                       "criteria": {"dark_on": None, "dark_off": None, "toggle": None, "none": None}},
    "media_action": {"type": "choice", "instructions": "What should happen to music playback?",
                     "criteria": {"play": None, "pause": None, "next": None, "previous": None, "none": None}},
    "timer_action": {"type": "choice", "instructions": "What should happen with a timer or reminder?",
                     "criteria": {"set": "start a timer or set a reminder", "check": "ask how much time is left",
                                  "cancel": "stop or cancel a timer", "none": None}},
    "system_action": {"type": "choice", "instructions": "What should happen to the computer?",
                      "criteria": {"lock": None, "sleep": None, "none": None}},
    "needs_time": {"type": "noul", "instructions": "Does answering this require knowing the current date or time?"},
    "needs_machine": {"type": "noul", "instructions": "Does answering this require information about this computer's status, like RAM, disk space, battery, uptime, CPU load, or which apps are running?"},
    "weather_action": {"type": "choice", "instructions": "Is the user asking about the weather?",
                       "criteria": {"fetch": "asks about the weather: current conditions, a forecast, or questions like will it rain, snow, be sunny, be hot, or be cold somewhere",
                                    "none": "not about the weather at all"}},
    "info_skill": {"type": "choice", "instructions": "Does the request need live external data, and which kind?",
                   "criteria": {"sunrise": "sunrise, sunset, dawn, dusk or daylight times for a place",
                                "currency": "currency exchange or converting money between currencies",
                                "wikipedia": "asks who or what a person, place or thing is (factual encyclopedia lookup)",
                                "joke": "asks for a joke or something funny",
                                "news": "asks for news or today's headlines",
                                "none": "needs no live external data"}},
    "memory_action": {"type": "choice", "instructions": "Is the user asking the assistant to remember, recall or forget personal facts?",
                      "criteria": {"save": "asks to remember or store something for later ('remember that…')",
                                   "recall": "asks what was remembered or asks for a previously stored fact",
                                   "forget": "asks to forget something",
                                   "none": "not about stored memories"}},
}


def split_questions():
    """The same branch questions twice, one set scoped to the first action asked for, one to the second."""
    out = {}
    for slot, word in (("first", "FIRST"), ("second", "SECOND")):
        for k, q in QUESTIONS.items():
            if k in ("category", "compound", "needs_time", "needs_machine", "weather_action",
                     "info_skill", "memory_action"):
                continue
            out[f"{slot}_{k}"] = {**q, "instructions": f"Considering ONLY the {word} action the user asks for: {q['instructions']}"}
    return out


SPLIT_QUESTIONS = split_questions()

# Decision backend priority: KEV > Typesafe > OpenRouter-Jev.
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13")


def decision_backend():
    """(url, key, model, name) for the active decision backend, or None."""
    if USE_KEV:
        return f"{KEV_URL}/v1/systemone", KEV_KEY, "jev-latest", "kev"
    if TS_KEY:
        return "https://api.typesafe.ai/v1/systemone", TS_KEY, "jev-latest", "typesafe"
    if OR_KEY:
        return "https://openrouter.ai/api/alpha/decisions", OR_KEY, JEV_MODEL, "openrouter"
    return None


def jev(text, questions=None):
    t = time.time()
    backend = decision_backend()
    if backend is None:
        raise RuntimeError("no decision backend: set TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
    url, key, model, name = backend
    r = requests.post(url, json={"model": model, "state": text, "questions": questions or QUESTIONS},
                      headers={"Authorization": f"Bearer {key}"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    ans = {}
    for k, a in j["answers"].items():
        if a["type"] == "noul":  # probability, confidence is distance from 0.5
            ans[k] = (a["noul"] >= 0.5, max(a["noul"], 1 - a["noul"]))
        elif a["type"] == "score":  # index into the rubric, legend maps it back to the label
            ans[k] = (a["legend"][str(int(round(a["score"])))], a.get("confidence", 0))
        else:
            ans[k] = (a["choice"], a.get("confidence", 0))
    usage = j.get("usage", {})
    cost = usage.get("cost") or usage.get("input_tokens", 0) * 0.042 / 1e6
    print(f"  backend: {name} ({model})")
    return ans, int((time.time() - t) * 1000), cost


# --------------------------------------------------------------------------- Linux actions
# Desktop ids for app_open; process names for app_quit / open checks.
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


def sh(*cmd):
    result = subprocess.run(list(cmd), capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"command failed: {' '.join(cmd)}")
    return result.stdout.strip()


def _sink():
    return "@DEFAULT_SINK@"


def volume():
    """Master output volume 0-100 via pactl (PipeWire/PulseAudio)."""
    out = sh("pactl", "get-sink-volume", _sink())
    m = re.search(r"([\d]+)%", out)
    if not m:
        raise RuntimeError(f"could not read volume: {out!r}")
    return int(m.group(1))


def set_volume(pct):
    sh("pactl", "set-sink-volume", _sink(), f"{int(max(0, min(100, pct)))}%")


def set_mute(m):
    sh("pactl", "set-sink-mute", _sink(), "1" if m else "0")


def is_muted():
    return sh("pactl", "get-sink-mute", _sink()).strip().lower() == "muted: yes"


def process_running(proc):
    r = subprocess.run(["pgrep", "-x", proc], capture_output=True)
    return r.returncode == 0


def open_app(key, wait=6.0):
    """Launch via the APPS launch command, wait until the process shows up."""
    app = APPS[key]
    sh(*app["launch"])
    t = time.time()
    while time.time() - t < wait and not process_running(app["process"]):
        time.sleep(0.3)


def press_media(action):
    """playerctl drives the active MPRIS player (Spotify desktop included)."""
    sh("playerctl", action)
    time.sleep(0.4)


def spotify_running():
    return process_running("spotify")


def set_dark_mode(on):
    """GNOME color scheme; other desktops degrade to an unsupported error."""
    sh("gsettings", "set", "org.gnome.desktop.interface", "color-scheme",
       "prefer-dark" if on else "prefer-light")


def dark_mode_on():
    out = sh("gsettings", "get", "org.gnome.desktop.interface", "color-scheme")
    return "dark" not in out  # prefer-light/default -> not dark


ACTIONS = {
    "app_open": lambda a: open_app(a),
    "app_quit": lambda a: subprocess.run(["pkill", "-x", APPS[a]["process"]]),
    "volume_up": lambda _: set_volume(min(100, volume() + 20)),
    "volume_down": lambda _: set_volume(max(0, volume() - 20)),
    "volume_mute": lambda _: set_mute(True),
    "volume_unmute": lambda _: set_mute(False),
    "volume_set": lambda lvl: set_volume(LEVELS.get(lvl, 50)),
    # Spotify has no separate in-app volume via MPRIS; map to system volume
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

# --------------------------------------------------------------------------- Scripted replies with Fish tags
REPLIES = {
    "app_open": ["[cheerful] {app}'s up.", "{app}, opening now.", "[chuckling] There you go, {app}."],
    "app_quit": ["{app}'s gone.", "[sighing] Closing {app}. Good riddance.", "Done, {app} is closed."],
    "volume_up": ["Louder it is.", "[cheerful] Turning it up.", "Up we go."],
    "volume_down": ["Bringing it down.", "[sighing] A little quieter.", "Turning it down."],
    "volume_mute": ["[sighing] Muting. Finally some quiet.", "Muted.", "Shh. Muted."],
    "volume_unmute": ["Sound's back.", "[cheerful] Unmuted.", "And we're back."],
    "volume_set": ["Set to {level}.", "Volume's {level} now."],
    "spotify_volume_up": ["Turning Spotify up.", "[cheerful] Spotify's louder."],
    "spotify_volume_down": ["Turning Spotify down.", "Spotify's a little quieter."],
    "spotify_volume_mute": ["Spotify's muted.", "[sighing] Muting Spotify."],
    "spotify_volume_unmute": ["Spotify's sound is back.", "[cheerful] Spotify's unmuted."],
    "spotify_volume_set": ["Spotify's set to {level}.", "Set Spotify to {level}."],
    "display_dark_on": ["[chuckling] Lights off.", "Dark mode on.", "Going dark."],
    "display_dark_off": ["[cheerful] Let there be light.", "Dark mode off.", "Back to light."],
    "display_toggle": ["Flipped it.", "There, switched."],
    "media_play": ["[cheerful] Playing.", "Music's on.", "Here we go."],
    "media_pause": ["Paused.", "[sighing] Pausing. Take your time.", "Holding it there."],
    "media_next": ["Skipping.", "[chuckling] Not a fan? Next one.", "Next track."],
    "media_previous": ["Going back one.", "Previous track.", "[chuckling] Again? Sure."],
    "system_lock": ["Locking up. See you soon.", "Locked.", "Screen's locked."],
    "system_sleep": ["Good night.", "Sleeping now.", "[sighing] Finally, a nap."],
    "info": ["[chuckling] That's a question, not a command. I'll get a brain for that soon.",
             "[sighing] I can't answer that one yet."],
    "chit_chat": ["[chuckling] Hi. Give me something to do.", "[cheerful] Hey. I'm listening."],
    "compound_done": ["[chuckling] Done, both of them.", "[cheerful] All done.", "Both sorted."],
    "wake": ["Yes?", "[cheerful] Mm-hm?", "I'm listening."],
    "clarify": ["[clear throat] Sorry, say that again?", "Hm, one more time?"],
    "give_up": ["[sighing] I'm not sure what you mean. Try saying it differently?"],
    "timer_set": ["[cheerful] Timer's set.", "On it. I'll let you know.", "Done, counting down."],
    "reminder_set": ["Got it, I'll remind you.", "[cheerful] Sure, I'll give you a shout."],
    "timer_check": ["{left} left.", "You've got {left} to go."],
    "timer_cancel": ["Timer cancelled.", "[sighing] Fine, no timer then."],
    "timers_cancel": ["All timers cancelled.", "Cleared them all."],
    "timer_none": ["[chuckling] There's no timer running."],
    "timer_unclear": ["[clear throat] How long for?"],
    "timer_done": ["[cheerful] Time's up!", "[chuckling] Ding ding, time's up."],
    "reminder_done": ["[cheerful] Hey, just a reminder: {label}.", "Reminder: {label}."],
    "unsupported": ["[chuckling] I know what you want, I just can't do that one yet."],
    "weather_fail": ["[sighing] Sorry, the weather service isn't answering me right now."],
    "skill_fail": ["[sighing] That service isn't answering me right now.", "[sighing] Couldn't fetch that just now."],
    "alarm_set": ["Alarm set for {time}.", "Done, alarm at {time}.", "[cheerful] Alarm's on for {time}."],
    "alarm_cancel": ["Alarms cancelled.", "No more alarms."],
    "alarm_done": ["[cheerful] Alarm! Time to get up.", "Alarm! Ring ring!"],
    "memory_saved": ["Got it, I'll remember that.", "[cheerful] Saved. I'll remember.", "Noted, that's in my memory."],
    "memory_forgot": ["Forgotten.", "Done, wiped from memory.", "Okay, it's gone."],
    "memory_unclear": ["[clear throat] What should I remember, exactly?"],
    "memory_unsupported": ["[sighing] Memory works only from the web remote right now."],
}


TARGETS = ("app", "volume", "display", "media", "system", "timer")
SPEAK_FIRST = {"volume_mute", "system_lock", "system_sleep"}


def say_line(key, **fmt):
    return random.choice(REPLIES[key]).format(**fmt)


# --------------------------------------------------------------------------- Timers and reminders
NUMBER_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
                "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20,
                "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "ninety": 90, "couple": 2, "few": 3}
UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60,
         "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
DURATION = re.compile(r"(\d+(?:\.\d+)?)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b(\s+and\s+a\s+half)?")


def _digits(text):
    """'twenty five minutes' -> '25 minutes', 'half an hour' -> '30 minutes'."""
    t = re.sub(r"\bhalf an? hour\b", "30 minutes", text.lower())
    t = re.sub(r"\ba couple of\b", "couple", t)
    t = re.sub(r"\b(an?|few|couple)\s+(hours?|minutes?|seconds?)\b", lambda m: f"{NUMBER_WORDS[m[1]]} {m[2]}", t)
    words = t.replace("-", " ").split()
    out, i = [], 0
    while i < len(words):
        w = words[i].strip(",.!?")
        if w in NUMBER_WORDS and w not in ("a", "an", "few", "couple"):
            n = NUMBER_WORDS[w]
            nxt = words[i + 1].strip(",.!?") if i + 1 < len(words) else ""
            if n >= 20 and nxt in NUMBER_WORDS and NUMBER_WORDS[nxt] < 10 and nxt not in ("a", "an"):
                n, i = n + NUMBER_WORDS[nxt], i + 1
            out.append(str(n))
        else:
            out.append(words[i])
        i += 1
    return " ".join(out)


def parse_duration(text):
    """Total seconds mentioned in the sentence, or None."""
    total = 0
    for num, unit, half in DURATION.findall(_digits(text)):
        secs = UNITS[unit]
        total += float(num) * secs + (secs / 2 if half else 0)
    return int(total) or None


def parse_reminder(text):
    """What to remind about: the part after 'to', minus any duration."""
    m = re.search(r"\bto\s+(.+)$", _digits(text))
    if not m:
        return None
    what = DURATION.sub("", m[1])
    what = re.sub(r"\bplease\b", "", what).strip(" .,!?")
    what = re.sub(r"\s*\b(in|for|after)$", "", what).strip(" .,!?")
    return what or None


def say_duration(secs):
    secs = max(0, int(round(secs)))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    parts = [f"{n} {u}{'' if n == 1 else 's'}" for n, u in ((h, "hour"), (m, "minute"), (s, "second")) if n]
    if h or m >= 10:
        parts = parts[:2] if h else parts[:1]
    return " and ".join(parts) or "no time"


TIMERS, TIMERS_LOCK = [], threading.RLock()  # RLock: save_timers() is called while the lock is held


def add_timer(secs, label=None):
    t = {"end": time.time() + secs, "secs": secs, "label": label, "line": None, "kind": "timer"}
    with TIMERS_LOCK:
        TIMERS.append(t)
        TIMERS.sort(key=lambda x: x["end"])
    save_timers()
    return t


def prepare_reminder(t, said):
    """While the timer runs, have the LLM write the alert and a short name, and render the audio, so it plays instantly."""
    try:
        r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                          headers={"Authorization": f"Bearer {OR_KEY}"},
                          json={"model": LLM_MODEL, "max_tokens": LLM_MAX_TOKENS, "usage": {"include": True},
                                "reasoning": {"effort": "low"},
                                "response_format": {"type": "json_object"},
                                "messages": [{"role": "system", "content":
                                    "The user set a reminder with a voice assistant. Reply with JSON only: "
                                    '{"label": "2 to 4 word name for the task, e.g. Call Sam", '
                                    '"alert": "one short friendly sentence the assistant says out loud when the time is up, '
                                    'speaking to the user, e.g. Hey, it\'s time to give Sam a call."}. '
                                    "The alert may start with one tag from [cheerful] [chuckling] [sighing], or none. No markdown."},
                                    {"role": "user", "content": said}]}, timeout=30)
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        t["label"] = data.get("label") or t["label"]
        fetch_tts(data["alert"])  # cache the audio now
        t["line"] = data["alert"]
        print(f"\n  reminder ready: {t['label']!r} -> {t['line']!r}")
    except Exception as e:
        print(f"\n  reminder prep failed, using the plain line: {e}")


def timer_snapshot():
    """(name, seconds left) for each running timer, soonest first."""
    now = time.time()
    with TIMERS_LOCK:
        return [((t["label"] or "").capitalize()
                 or (f"Alarm {t.get('h', 0):02d}:{t.get('m', 0):02d}"
                     if t.get("kind") == "alarm" else short_duration(t["secs"]) + " timer"),
                max(0, t["end"] - now))
                for t in TIMERS]


def short_duration(secs):
    h, rem = divmod(int(secs), 3600)
    m, s = divmod(rem, 60)
    return " ".join(f"{n} {u}" for n, u in ((h, "hr"), (m, "min"), (s, "sec")) if n) or "0 sec"


def run_timer(action, text):
    """Returns (reply_key, fmt). Handles both timers and daily alarms."""
    tl = text.lower()
    if action == "timer_set":
        if re.search(r"\b(?:alarm|wake me)\b", tl):
            hm = re.search(r"\b(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)?", tl)
            if hm:
                h, m = int(hm["h"]), int(hm["m"] or 0)
                if hm["ap"] and "p" in hm["ap"] and h < 12:
                    h += 12
                if hm["ap"] and "a" in hm["ap"] and h == 12:
                    h = 0
                if 0 <= h < 24 and 0 <= m < 60:
                    add_alarm(h, m)
                    time_str = f"{h:02d}:{m:02d}"
                    print(f"  alarm: daily at {time_str}")
                    return ("alarm_set", {"time": time_str})
            return ("timer_unclear", {})
        secs = parse_duration(text)
        if not secs:
            return ("timer_unclear", {})
        label = parse_reminder(text)
        t = add_timer(secs, label)
        if label and OR_KEY:
            threading.Thread(target=prepare_reminder, args=(t, text), daemon=True).start()
        print(f"  timer: {secs}s" + (f" -> {label!r}" if label else ""))
        return ("reminder_set" if label else "timer_set", {})
    with TIMERS_LOCK:
        if not TIMERS:
            return ("timer_none", {})
        if action == "timer_check":
            return ("timer_check", {"left": say_duration(TIMERS[0]["end"] - time.time())})
        if re.search(r"\ball\b", tl):
            TIMERS.clear()
            save_timers()
            return ("timers_cancel", {})
        if re.search(r"\balarm", tl):
            removed = [t for t in TIMERS if t.get("kind") == "alarm"]
            if not removed:
                return ("timer_none", {})
            for t in removed:
                TIMERS.remove(t)
            save_timers()
            return ("alarm_cancel", {})
        TIMERS.remove(max(TIMERS, key=lambda t: t["end"] - t["secs"]))  # the one set most recently
        save_timers()
        return ("timer_cancel", {})


def start_timer_loop(on_done):
    """Fires on_done(timer) when a timer runs out; persists every change,
    pushes fired alerts to the phone (if ntfy is configured) and reschedules
    daily alarms."""
    def loop():
        while True:
            time.sleep(0.25)
            with TIMERS_LOCK:
                due = [t for t in TIMERS if t["end"] <= time.time()]
                for t in due:
                    TIMERS.remove(t)
            if due:
                save_timers()
            for t in due:
                try:
                    notify_push("Hey Jev", t.get("label") or ALERT_MESSAGE or "Timer finished")
                except Exception:
                    pass
                try:
                    on_done(t)
                except Exception as e:
                    print(f"  timer alert failed: {e}")
                if t.get("kind") == "alarm":
                    add_alarm(t["h"], t["m"], t.get("label"))
    threading.Thread(target=loop, daemon=True).start()


def timer_done_line(t):
    if t["line"]:
        return t["line"]
    if t.get("label"):
        return say_line("reminder_done", label=t["label"])
    if ALERT_MESSAGE:
        return ALERT_MESSAGE
    return say_line("alarm_done" if t.get("kind") == "alarm" else "timer_done")


# --------------------------------------------------------------------------- LLM fallback (questions only)
LLM_MODEL = os.getenv("LLM_MODEL", "anthropic/claude-haiku-4.5")
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "300"))

MACHINE_CTX = {"t": 0.0, "s": ""}


def machine_context():
    """Compact read-only snapshot of this Linux box, injected into LLM
    questions when Jev says the answer needs it. Cached for 60s."""
    if MACHINE_CTX["s"] and time.time() - MACHINE_CTX["t"] < 60:
        return MACHINE_CTX["s"]
    try:
        import socket
        up_s = float(open("/proc/uptime").read().split()[0])
        load1 = open("/proc/loadavg").read().split()[0]
        mem = {}
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            mem[k.strip()] = int(v.strip().split()[0])
        ram = f"{mem['MemAvailable'] / 1048576:.1f}/{mem['MemTotal'] / 1048576:.1f}GB free"
        df = subprocess.run(["df", "-BG", "/"], capture_output=True, text=True).stdout
        disk_free = df.splitlines()[-1].split()[3]
        import glob
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
    MACHINE_CTX["t"], MACHINE_CTX["s"] = time.time(), out
    return out


def ask_llm(text, need_time=False, need_machine=False, memory=None):
    t = time.time()
    ctx = []
    if need_time:
        ctx.append(f"The current local date and time is {time.strftime('%A %d %B %Y, %H:%M local time')}.")
    if need_machine:
        ctx.append(f"Machine status: {machine_context()}")
    if memory:
        ctx.append("Things you remember about the user: " + "; ".join(memory) + ".")
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      headers={"Authorization": f"Bearer {OR_KEY}"},
                      json={"model": LLM_MODEL, "max_tokens": LLM_MAX_TOKENS, "usage": {"include": True},
                            "reasoning": {"effort": "low"},
                            "messages": [{"role": "system", "content": "You are a voice assistant living on the user's PC. "
                                          + " ".join(ctx)
                                          + (" You have live access to that data — answer from it when relevant; never claim you lack access." if ctx else "")
                                          + " "
                                          + "Answer in one short spoken sentence, no markdown. "
                                          "You may start with exactly one tag from: [chuckling] [laughing] [sighing] [cheerful], or none."},
                                         {"role": "user", "content": text}]}, timeout=30)
    r.raise_for_status()
    j = r.json()
    msg = j["choices"][0]["message"]
    line = (msg.get("content") or "").strip()
    if not line:  # reasoning models sometimes return only chain-of-thought
        tail = (msg.get("reasoning") or "").strip().splitlines()[-1:] or ["(no answer)"]
        line = tail[0].strip()
    return line, int((time.time() - t) * 1000), j.get("usage", {}).get("cost")


# --------------------------------------------------------------------------- Weather (wttr.in, free, no key)
WEATHER_PLACE = re.compile(
    r"\bweather\b(?:\s+(?:is|it|the|like|in|at|for|of|about|today|tonight|now|there|outside))*"
    r"\s*(?P<place>[a-zA-Z][\w\s\-'’]*?)?[\s?.!,]*$")
CONDITION = re.compile(
    r"\b(?:rain|snow|hail|sleet|drizzle|pour|storm|thunder(?:storm)?|sunny|cloudy|overcast|"
    r"fog(?:gy)?|mist(?:y)?|windy|hot|cold|temperature|forecast|precipitation)\b", re.I)
IN_PLACE = re.compile(r"\b(?:in|at|for|around)\s+(?P<place>[a-zA-Z][\w\s\-'’]*?)[\s?.!,]*$", re.I)


def extract_place(text):
    m = WEATHER_PLACE.search(text.strip())
    if not m:
        m = None
        if CONDITION.search(text):
            m = IN_PLACE.search(text.strip())
    if not m:
        return None
    place = (m.group("place") or "").strip(" .,!?'’-")
    place = re.sub(r"\b(today|tonight|tomorrow|now|currently|there|outside|right now|here)\b",
                   "", place, flags=re.I).strip(" ,.!?")
    return place or None


def _hour_label(wttr_time):
    t = int(wttr_time) // 100
    return "midnight" if t == 0 else f"{t:02d}:00"


def weather_line(text):
    """One spoken sentence from wttr.in. No place named → IP-based location.
    'will it rain/snow' gets a direct yes/no verdict from hourly chances."""
    place = extract_place(text)
    t = text.lower()
    kind = "snow" if ("snow" in t or "sleet" in t) else "rain"
    try:
        r = requests.get(f"https://wttr.in/{place or ''}?format=j1",
                         headers={"User-Agent": "curl/8.0"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        cc = data["current_condition"][0]
        today = data["weather"][0]
        name = place.title() if place else "your area"
        desc = cc["weatherDesc"][0]["value"].strip().lower()
        base = f"Right now {cc['temp_C']} degrees, {desc}"
        if ("rain" in t or "snow" in t or "drizzle" in t or "sleet" in t
                or "precip" in t or "pour" in t):
            key = f"chanceof{kind}"
            chances = [(int(h.get(key, 0)), h.get("time", "0")) for h in today["hourly"]]
            peak, peak_time = max(chances)
            peak_hour = _hour_label(peak_time) if peak >= 25 else None
            if peak >= 70:
                verdict = f"{kind} is very likely today"
            elif peak >= 50:
                verdict = f"{kind} is likely today"
            elif peak >= 25:
                verdict = f"there is a real chance of {kind} today"
            elif peak >= 5:
                verdict = f"{kind} is unlikely today"
            else:
                verdict = f"it doesn't look like {kind} today"
            line = (f"{name}: {verdict}, up to {peak} percent"
                    + (f" around {peak_hour}" if peak_hour else "")
                    + f". {base}")
            if float(cc.get("precipMM", 0) or 0) > 0:
                line += f", {float(cc['precipMM']):.1f} millimeters fell in the last hour"
        else:
            line = (f"{name}: {cc['temp_C']} degrees, feels like {cc['FeelsLikeC']}, "
                    f"{desc}, humidity {cc['humidity']} percent. "
                    f"Today {today['mintempC']} to {today['maxtempC']} degrees")
        print(f"  weather: {place or '(auto)'} -> {cc['temp_C']}C {desc}")
        return f"[cheerful] {line}."
    except Exception as e:
        print(f"  weather failed: {e}")
        return say_line("weather_fail")


# --------------------------------------------------------------------------- Free-API skills
SUN_KW = re.compile(r"\b(?:sunrise|sunset|dawn|dusk|daylight|golden hour)\b", re.I)
CURRENCY_WORDS = {"dollar": "USD", "dollars": "USD", "usd": "USD", "euro": "EUR", "euros": "EUR",
                  "eur": "EUR", "pound": "GBP", "pounds": "GBP", "sterling": "GBP", "gbp": "GBP",
                  "quid": "GBP", "yen": "JPY", "jpy": "JPY", "franc": "CHF", "francs": "CHF",
                  "chf": "CHF", "krona": "SEK", "kronor": "SEK", "sek": "SEK", "zloty": "PLN",
                  "pln": "PLN", "rupee": "INR", "rupees": "INR", "inr": "INR", "yuan": "CNY",
                  "cny": "CNY", "dirham": "AED", "aed": "AED", "won": "KRW", "krw": "KRW"}
CURRENCY_A = re.compile(r"(?P<amt>\d+(?:[.,]\d+)?)\s*(?P<f>[a-zA-Z]+)\s+(?:to|in|into)\s+(?:the\s+)?(?P<t>[a-zA-Z]+)")
CURRENCY_B = re.compile(r"how\s+(?:many|much)\s+(?P<t>[a-zA-Z]+)\s+(?:is|are|does|would)\s+(?P<amt>\d+(?:[.,]\d+)?)\s*(?P<f>[a-zA-Z]+)")


def _geocode(place):
    """wttr.in as a free geocoder: nearest_area with lat/lng + name."""
    r = requests.get(f"https://wttr.in/{place or ''}?format=j1",
                     headers={"User-Agent": "curl/8.0"}, timeout=15)
    r.raise_for_status()
    j = r.json()
    area = j.get("nearest_area", [{}])[0]
    name = (area.get("areaName", [{"value": ""}])[0]["value"]) or (place or "your area").title()
    return area.get("latitude"), area.get("longitude"), name


def _to24(x):
    """12h astronomy time -> 24h 'HH:MM'."""
    for f in ("%I:%M %p", "%I:%M:%S %p"):
        try:
            return time.strftime("%H:%M", time.strptime(x.strip(), f))
        except ValueError:
            pass
    return x


def sunrise_line(text):
    place = None
    if SUN_KW.search(text):
        m = IN_PLACE.search(text.strip())
        place = (m.group("place") or "").strip(" .,!?'’-") if m else None
    j = requests.get(f"https://wttr.in/{place or ''}?format=j1",
                     headers={"User-Agent": "curl/8.0"}, timeout=15)
    j.raise_for_status()
    j = j.json()
    astro = j["weather"][0]["astronomy"][0]
    area = j.get("nearest_area", [{}])[0]
    name = (area.get("areaName", [{"value": ""}])[0]["value"]) or (place or "your area").title()
    return (f"[cheerful] In {name} today: sunrise {_to24(astro['sunrise'])}, "
            f"sunset {_to24(astro['sunset'])}.")


def _currency_code(word):
    return CURRENCY_WORDS.get(word.lower(), word.upper() if len(word) == 3 else None)


def currency_line(text):
    t = text.replace(",", "")
    m = CURRENCY_B.search(t) or CURRENCY_A.search(t)
    amt_s, f_w, t_w = (m["amt"], m["f"], m["t"]) if m else ("1", None, None)
    if not m:
        m2 = re.search(r"\b(?P<f>[a-zA-Z]+)\s+(?:to|in)\s+(?:the\s+)?(?P<t>[a-zA-Z]+)", t)
        if not m2:
            return say_line("skill_fail")
        amt_s, f_w, t_w = "1", m2["f"], m2["t"]
    f, t = _currency_code(f_w), _currency_code(t_w)
    if not f or not t:
        return "[sighing] I only know the major currencies, three letters each."
    if f == t:
        return f"That's the same currency, {f}."
    r = requests.get(f"https://api.frankfurter.app/latest?amount={amt_s}&from={f}&to={t}", timeout=15)
    r.raise_for_status()
    val = r.json()["rates"][t]
    return f"[cheerful] {float(amt_s):g} {f} is about {float(val):.2f} {t}."


def wiki_topic(text):
    t = text.strip().rstrip("?.! ")
    t = re.sub(r"^(?:hey\s+\w+,?\s*)", "", t, flags=re.I)
    t = re.sub(r"^(?:tell\s+me\s+about|about)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:who|what|where)(?:'s|\s+is|\s+are|\s+was|\s+were)?\s*", "", t, flags=re.I)
    if re.match(r"^(?:wrote|built|created|made|directed|invented|painted|founded|composed)\b",
                t, re.I):
        return None  # "wrote/built X" needs the author/creator -> let the LLM answer
    t = re.sub(r"^(?:(?:is|was|are|were|the)\s+)+", "", t, flags=re.I)
    if re.search(r"\b(?:my|mine|our)\b", t, flags=re.I):
        return None  # personal facts — the encyclopedia can't know these
    return t or None


def wiki_line(text):
    topic = wiki_topic(text)
    if not topic:
        return None  # signal: fall back to the LLM
    try:
        slug = urllib.parse.quote(topic.replace(" ", "_"))
        r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}",
                         headers={"User-Agent": "hey-jev/1.0"}, timeout=15)
        if r.status_code == 404:
            s = requests.get("https://en.wikipedia.org/w/api.php",
                             params={"action": "query", "list": "search", "srsearch": topic,
                                     "format": "json", "srlimit": 1}, timeout=15)
            hits = s.json().get("query", {}).get("search", [])
            if not hits:
                return None
            r = requests.get(f"https://en.wikipedia.org/api/rest_v1/page/summary/"
                             f"{urllib.parse.quote(hits[0]['title'].replace(' ', '_'))}",
                             headers={"User-Agent": "hey-jev/1.0"}, timeout=15)
        r.raise_for_status()
        extract = r.json().get("extract", "").strip()
    except (ValueError, requests.RequestException) as e:  # non-JSON / network hiccup -> LLM
        print(f"  wiki unavailable ({e}), falling back to LLM")
        return None
    if not extract:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", extract)
    return "[cheerful] " + " ".join(sentences[:2])


def joke_line():
    r = requests.get("https://icanhazdadjoke.com/", headers={"Accept": "application/json"}, timeout=15)
    r.raise_for_status()
    return "[cheerful] " + r.json()["joke"]


def news_line(text):
    feed = ("https://feeds.bbci.co.uk/news/technology/rss.xml"
            if "tech" in text.lower() else
            "https://feeds.bbci.co.uk/news/world/rss.xml")
    r = requests.get(feed, timeout=15, headers={"User-Agent": "curl/8.0"})
    r.raise_for_status()
    import xml.etree.ElementTree as ET
    titles = [item.findtext("title", "").strip()
              for item in ET.fromstring(r.content).findall(".//item")][:3]
    if not titles:
        return say_line("skill_fail")
    return "[cheerful] Headlines: " + " ... ".join(titles)


def skill_line(skill, text):
    try:
        if skill == "sunrise":
            return sunrise_line(text)
        if skill == "currency":
            return currency_line(text)
        if skill == "wikipedia":
            return wiki_line(text)  # None -> caller falls back to the LLM
        if skill == "joke":
            return joke_line()
        if skill == "news":
            return news_line(text)
    except Exception as e:
        print(f"  skill {skill} failed: {e}")
    return say_line("skill_fail")


# --------------------------------------------------------------------------- Memory (client-side, localStorage)
MEMORY_SINK = None     # set by the remote server during a turn
MEMORY_CURRENT = []    # the connected client's memory during a turn


def memory_fact(text):
    t = text.strip().rstrip("?.! ")
    t = re.sub(r"^(?:hey\s+\w+,?\s*)", "", t, flags=re.I)
    t = re.sub(r"^(?:please\s+)?remember(?:\s+(?:that|this|it))?\s*(?:that\s+)?", "", t, flags=re.I)
    t = re.sub(r"^(?:that)\s+", "", t, flags=re.I)
    return t.strip() or None


MEM_SAVE_RE = re.compile(r"^\s*(?:please\s+)?remember\s+that\b", re.I)
MEM_RECALL_RE = re.compile(
    r"\bwhat\s+(?:do\s+you\s+remember|do\s+you\s+know\s+about\s+me)\b"
    r"|\bdo\s+you\s+remember\b|\bwhat\s+have\s+(?:you\s+)?remembered\b", re.I)
MEM_FORGET_RE = re.compile(r"\bforget\b", re.I)


def memory_override(text):
    """Deterministic memory phrasing — KEV is unreliable at telling
    save/recall/forget apart, so plain language rules decide the op."""
    t = (text or "").strip()
    if MEM_SAVE_RE.match(t):
        return "save"
    if MEM_RECALL_RE.search(t):
        return "recall"
    if MEM_FORGET_RE.search(t) and not re.search(r"\bdon'?t\s+forget\b", t, re.I):
        return "forget"
    return None


def memory_forget(text):
    t = text.strip().rstrip("?.! ")
    if re.search(r"\b(?:everything|all of it|all)\b", t, flags=re.I):
        return "*"
    t = re.sub(r"^(?:hey\s+\w+,?\s*)", "", t, flags=re.I)
    t = re.sub(r"^(?:please\s+)?forget(?:\s+(?:that|about|it))?\s+(?:about\s+)?", "", t, flags=re.I)
    return t.strip() or "*"


def ask_llm_with_memory(text):
    return ask_llm(text, memory=MEMORY_CURRENT)


# --------------------------------------------------------------------------- Timers on disk + alarms + push
TIMERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "timers.json")
NTFY_URL = os.getenv("NTFY_URL", "").strip()
ALERT_MESSAGE = os.getenv("ALERT_MESSAGE", "").strip()


def notify_push(title, body, url=None):
    """Optional phone push via ntfy.sh — set NTFY_URL in .env (server owner)
    or a per-client topic (web remote) to enable."""
    target = url or NTFY_URL
    if not target:
        return
    try:
        requests.post(target, data=body.encode(),
                      headers={"Title": title, "Tags": "bell"}, timeout=10)
    except Exception as e:
        print(f"  ntfy failed: {e}")


def save_timers():
    try:
        with TIMERS_LOCK:
            data = [{"end": t["end"], "secs": t["secs"], "label": t.get("label"),
                     "line": t.get("line"), "kind": t.get("kind"), "h": t.get("h"), "m": t.get("m")}
                    for t in TIMERS]
        tmp = TIMERS_FILE + ".tmp"
        open(tmp, "w").write(json.dumps(data))
        os.replace(tmp, TIMERS_FILE)
    except Exception as e:
        print(f"  timer save failed: {e}")


def load_timers():
    """Reload persisted timers/alarms; fire missed reminders as a push."""
    try:
        with open(TIMERS_FILE) as f:
            data = json.load(f)
    except Exception:
        return
    now = time.time()
    stale = []
    with TIMERS_LOCK:
        TIMERS.clear()
    for d in data:
        if d.get("kind") == "alarm":
            add_alarm(d.get("h", 7), d.get("m", 0), d.get("label"))
        elif d["end"] > now + 1:
            with TIMERS_LOCK:
                TIMERS.append({"end": d["end"], "secs": d["secs"], "label": d.get("label"),
                               "line": d.get("line"), "kind": "timer"})
            with TIMERS_LOCK:
                TIMERS.sort(key=lambda x: x["end"])
        else:
            stale.append(d)
    save_timers()
    for d in stale:
        if d.get("label"):
            notify_push("Missed reminder", d["label"])
            print(f"  missed while offline: {d.get('label')!r}")


def next_alarm_end(h, m, now=None):
    now = now or time.time()
    lt = time.localtime(now)
    candidate = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, m, 0, 0, 0, -1))
    if candidate <= now + 1:
        candidate += 86400
    return candidate


def add_alarm(h, m, label=None):
    t = {"end": next_alarm_end(h, m), "secs": 0,
         "label": label or f"Alarm {h:02d}:{m:02d}", "line": None,
         "kind": "alarm", "h": h, "m": m}
    with TIMERS_LOCK:
        TIMERS.append(t)
        TIMERS.sort(key=lambda x: x["end"])
    save_timers()
    return t


# --------------------------------------------------------------------------- Web tiles
TILE_CACHE = {"t": 0.0, "data": None}


def tiles_data():
    """Clock + local weather + sun times for the web page's tile row."""
    if TILE_CACHE["data"] and time.time() - TILE_CACHE["t"] < 600:
        return TILE_CACHE["data"]
    data = {"clock": time.strftime("%H:%M"), "date": time.strftime("%a %d %b")}
    try:
        j = requests.get("https://wttr.in/?format=j1",
                         headers={"User-Agent": "curl/8.0"}, timeout=10).json()
        cc = j["current_condition"][0]
        today = j["weather"][0]
        area = j.get("nearest_area", [{}])[0]
        data["weather"] = {"temp": cc["temp_C"], "desc": cc["weatherDesc"][0]["value"].strip().lower(),
                           "hi": today["maxtempC"], "lo": today["mintempC"],
                           "area": area.get("areaName", [{"value": ""}])[0]["value"] or "here"}
        astro = today.get("astronomy", [{}])[0]
        data["sun"] = {"sunrise": _to24(astro.get("sunrise", "")),
                       "sunset": _to24(astro.get("sunset", ""))}
    except Exception as e:
        data["error"] = str(e)
    TILE_CACHE["t"], TILE_CACHE["data"] = time.time(), data
    return data


# --------------------------------------------------------------------------- Fish TTS
CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")


def fetch_tts(text):
    """Return a wav path for this line, generating it once and caching on disk. Returns (path, ms, cached)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, hashlib.sha1(f"{VOICE_ID}|{text}".encode()).hexdigest() + ".wav")
    if os.path.exists(path):
        return path, 0, True
    t = time.time()
    r = requests.post("https://api.fish.audio/v1/tts", headers={"Authorization": f"Bearer {FISH_KEY}", "model": "s2.1-pro-free"},
                      json={"text": text, "reference_id": VOICE_ID, "format": "wav"}, timeout=60)
    r.raise_for_status()
    open(path, "wb").write(r.content)
    return path, int((time.time() - t) * 1000), False


def play_wav(path):
    data, sr = sf.read(path, dtype="float32")
    if data.ndim > 1:
        data = data[:, 0]
    sd.play(data, sr)
    sd.wait()


def play_wav_path(path):
    """Public alias for local playback from other entry points (remote timer alerts)."""
    play_wav(path)


def speak(text):
    path, ms, cached = fetch_tts(text)
    play_wav(path)
    return ms


def all_scripted_lines():
    """Every fixed reply with placeholders expanded, so the whole set can be pre-rendered."""
    for key, lines in REPLIES.items():
        for line in lines:
            if "{app}" in line:
                yield from (line.format(app=v["name"]) for v in APPS.values())
            elif "{level}" in line:
                yield from (line.format(level=l) for l in LEVELS)
            elif "{" not in line:  # lines with a live value like {left} are generated when needed
                yield line


def warm_cache():
    """Pre-render all scripted lines in the background so replies play instantly ($0 on the free string)."""
    made = 0
    for line in all_scripted_lines():
        try:
            _, _, cached = fetch_tts(line)
            made += 0 if cached else 1
        except Exception as e:
            print(f"  cache miss for {line!r}: {e}")
    if made:
        print(f"  cached {made} new reply lines")


def chime():
    """Timer-done sound: freedesktop bell via paplay, terminal bell fallback."""
    for f in ("/usr/share/sounds/freedesktop/stereo/complete.oga",
              "/usr/share/sounds/freedesktop/stereo/bell.oga"):
        if os.path.exists(f):
            subprocess.run(["paplay", f], capture_output=True)
            return
    print("\a", end="", flush=True)


# --------------------------------------------------------------------------- Decision
def sub_action(ans, target):
    """(conf, action_key, arg, reply_key, fmt) for a target, or None if Jev didn't pick anything confident."""
    if target == "app":
        (app, ac), (action, aac) = ans["app"], ans["app_action"]
        if app == "none" or action == "none" or min(ac, aac) < GATE:
            return None
        return (min(ac, aac), f"app_{action}", app, f"app_{action}", {"app": APPS[app]["name"]})
    key = {"volume": "volume_action", "display": "display_action", "media": "media_action",
           "system": "system_action", "timer": "timer_action"}[target]
    action, conf = ans[key]
    if action == "none" or conf < GATE:
        return None
    lvl = ans["volume_level"][0] if target == "volume" else None
    prefix = target
    if target == "volume":
        scope, scope_conf = ans["volume_scope"]
        named_spotify = ans["app"][0] == "spotify"
        if scope == "spotify" and (scope_conf >= 0.5 or named_spotify):
            prefix = "spotify_volume"  # maps to system volume on Windows, same reply keys
    return (conf, f"{prefix}_{action}", lvl, f"{prefix}_{action}", {"level": lvl})


def decide(ans, text=None):
    """Read the Jev fan-out. Returns ("actions", [...]), ("reply", key), ("llm", None) or ("clarify", None)."""
    cat, cconf = ans["category"]
    if ans["target"][0] == "timer" and ans["target"][1] >= GATE and not ans["compound"][0]:
        t = sub_action(ans, "timer")  # "how long is left?" reads like a question but it's a timer command
        if t:
            return ("actions", [t])
    wact, wconf = ans["weather_action"]
    if wact == "fetch" and wconf >= 0.5 and cat != "unclear":
        return ("weather", None)
    op = memory_override(text) if text else None
    if op is None:
        mact, mconf = ans["memory_action"]
        if mact == "forget" and mconf >= 0.5:
            op = "forget"
    if op in ("save", "forget"):
        return ("memory", op)
    if op == "recall":
        return ("llm", None)  # memory rides the LLM context automatically
    skill, sconf = ans["info_skill"]
    if skill != "none" and sconf >= 0.5:
        return ("skill", skill)  # explicit skill intent wins even over an unclear category
    if cat == "chit_chat" and cconf >= GATE:
        return ("reply", "chit_chat")
    if cat == "information_request" and cconf >= GATE:
        return ("llm", None)
    if cat == "unclear" and cconf >= GATE:
        return ("clarify", None)
    if ans["compound"][0] and ans["compound"][1] >= GATE:
        return ("split", None)
    a = pick_action(ans)
    if a:
        return ("actions", [a])
    return ("llm", None) if cat == "information_request" else ("clarify", None)


def pick_action(ans):
    """Trust Jev's target if it's reasonably sure, else take the single most confident action anywhere."""
    target, tconf = ans["target"]
    a = sub_action(ans, target) if tconf >= 0.5 else None
    if a is None:
        cands = [x for x in (sub_action(ans, t) for t in TARGETS) if x]
        a = max(cands, key=lambda x: x[0]) if cands else None
    return a


def split_actions(text, ans):
    """Second Jev call with first/second slots, so two actions in one sentence each get their own answers."""
    sans, ms, cost = jev(text, SPLIT_QUESTIONS)
    print(f"  -- split call: jev {ms}ms  ${cost:.6f}")
    acts = []
    for slot in ("first", "second"):
        half = {k[len(slot) + 1:]: v for k, v in sans.items() if k.startswith(slot + "_")}
        a = pick_action(half)
        print(f"  {slot:15} {a[1] if a else 'nothing confident'}" + (f" {a[2]}" if a and a[2] else ""))
        if a and (a[1], a[2]) not in [(x[1], x[2]) for x in acts]:
            acts.append(a)
    if len(acts) < 2:  # split didn't separate them, fall back to whatever the first fan-out was sure about
        acts = [a for a in (sub_action(ans, t) for t in TARGETS) if a]
    return acts


# --------------------------------------------------------------------------- One turn
misses = 0
LAST_TURN_COST = {"jev": 0.0, "llm": 0.0}
TURN_CANCEL = {"flag": False}


class TurnCancelled(Exception):
    pass


def request_cancel():
    """Ask the in-flight turn to stop at its next checkpoint."""
    TURN_CANCEL["flag"] = True


def _cancel_check(notify=None):
    if TURN_CANCEL["flag"]:
        emit(notify, "Ready", "Cancelled")
        raise TurnCancelled()


def emit(notify, state, detail=""):
    if notify:
        notify(state, detail)


def handle(text, stt_ms=None, notify=None):
    global misses
    LAST_TURN_COST.update({"jev": 0.0, "llm": 0.0})
    print(f"\n> heard: {text!r}" + (f"  (stt {stt_ms}ms)" if stt_ms is not None else ""))
    if not text.strip():
        emit(notify, "Ready", "Didn't catch anything")
        return
    emit(notify, "Thinking", text)
    ans, jev_ms, cost = jev(text)
    LAST_TURN_COST["jev"] = cost
    _cancel_check(notify)
    for k, (v, c) in ans.items():
        flag = "" if c >= GATE else "  <- below gate"
        print(f"  {k:15} {str(v):22} {c:.2f}{flag}")
    print(f"  jev {jev_ms}ms  ${cost:.6f}")
    kind, payload = decide(ans, text)
    if kind == "split":
        payload = split_actions(text, ans)
        kind = "actions" if payload else "clarify"
    if kind == "clarify":
        misses += 1
        line = say_line("give_up") if misses >= 2 else say_line("clarify")
        if misses >= 2:
            misses = 0
    else:
        misses = 0
        if kind == "reply":
            line = say_line(payload)
        elif kind == "weather":
            line = weather_line(text)
        elif kind == "memory":
            op = payload
            sink = MEMORY_SINK
            if sink is None:
                line = say_line("memory_unsupported")
            elif op == "save":
                fact = memory_fact(text)
                if not fact:
                    line = say_line("memory_unclear")
                else:
                    sink("save", fact)
                    line = say_line("memory_saved")
            else:  # forget
                sink("forget", memory_forget(text))
                line = say_line("memory_forgot")
        elif kind == "skill":
            line = skill_line(payload, text)
            if line is None:  # e.g. "who wrote X" — the encyclopedia can't answer that
                line, llm_ms, llm_cost = ask_llm(text,
                                                 need_time=ans["needs_time"][0],
                                                 need_machine=ans["needs_machine"][0],
                                                 memory=MEMORY_CURRENT)
                LAST_TURN_COST["llm"] = llm_cost or 0.0
                print(f"  llm fallback {LLM_MODEL} {llm_ms}ms  ${llm_cost}")
        elif kind == "llm":
            _cancel_check(notify)
            line, llm_ms, llm_cost = ask_llm(text,
                                             need_time=ans["needs_time"][0],
                                             need_machine=ans["needs_machine"][0],
                                             memory=MEMORY_CURRENT)
            LAST_TURN_COST["llm"] = llm_cost or 0.0
            print(f"  llm {LLM_MODEL} {llm_ms}ms  ${llm_cost}")
        else:
            default_line = lambda: say_line(payload[0][3], **payload[0][4]) if len(payload) == 1 else say_line("compound_done")
            speak_first = any(a[1] in SPEAK_FIRST or (a[1].endswith("volume_set") and a[2] == "silent") for a in payload)
            if speak_first:
                line = default_line()
                _cancel_check(notify)
                say(line, notify)
            done, timer_reply = 0, None
            for _, action, arg, _, _ in payload:
                try:
                    emit(notify, "Doing it", text)
                    if action.startswith("timer_"):
                        timer_reply = run_timer(action, text)
                    else:
                        ACTIONS[action](arg)
                    print(f"  action: {action} {arg or ''}")
                    done += 1
                except Exception as e:
                    print(f"  action failed: {action} {e}")
            if speak_first:
                emit(notify, "Ready", line)
                return
            if not done:
                line = say_line("unsupported")
            elif timer_reply and len(payload) == 1:
                line = say_line(timer_reply[0], **timer_reply[1])
            else:
                line = default_line()
    _cancel_check(notify)
    say(line, notify)
    emit(notify, "Ready", line)


def say(line, notify):
    print(f"  say: {line}")
    emit(notify, "Speaking", line)
    tts_ms = speak(line)
    print(f"  fish {'cached' if tts_ms == 0 else str(tts_ms) + 'ms'}")


# --------------------------------------------------------------------------- Mic + push to talk
def pick_input():
    """Windows sometimes has no default recording device set; fall back to the first available microphone."""
    if sd.default.device[0] != -1:
        return None
    devices = sd.query_devices()
    ins = [i for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    mics = [i for i in ins if "monitor" not in devices[i]["name"].lower()]
    named = [i for i in mics if "mic" in devices[i]["name"].lower() or "input" in devices[i]["name"].lower()]
    pick = (named or mics or ins)[0] if (named or mics or ins) else None
    if pick is not None:
        print(f"[mic] no default input device set on Windows — using "
              f"{pick}: {devices[pick]['name']!r} (override with --device)")
    return pick


class Recorder:
    BLOCK = 1600  # 100ms at 16kHz

    def __init__(self, device=None):
        self.frames, self.on = [], False
        self.wake, self.paused = False, False
        self.segments = queue.Queue()
        self.noise = 0.005
        self._reset_segment()
        self.stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                                     blocksize=self.BLOCK, callback=self._cb,
                                     device=device if device is not None else pick_input())
        self.stream.start()

    def _reset_segment(self):
        self.speech, self.silent = [], 0
        self.preroll = collections.deque(maxlen=3)

    def _cb(self, indata, *_):
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
        if self.silent >= 8 or len(self.speech) >= 150:  # 0.8s pause ends a phrase, 15s max
            if len(self.speech) - self.silent >= 4:
                self.segments.put(np.concatenate(self.speech))
            self._reset_segment()

    def start(self):
        self.frames, self.on = [], True

    def stop(self):
        self.on = False
        return np.concatenate(self.frames)[:, 0] if self.frames else np.zeros(0, dtype="float32")


def ready_text(wake):
    return "Say \u201cHey Jev\u201d and your command" if wake else "Ready when you are"


_WHISPER_SPEC = None


def whisper_spec():
    """(model_name, language) for STT. With non-English languages configured,
    uses the multilingual 'small' model when it is cached (language=None so
    Whisper auto-detects); otherwise the English-only default."""
    global _WHISPER_SPEC
    if _WHISPER_SPEC is not None:
        return _WHISPER_SPEC
    if not (WHISPER_LANGUAGES - {"en"}):
        _WHISPER_SPEC = (WHISPER_MODEL, "en")
        return _WHISPER_SPEC
    hub = os.path.join(os.getenv("HF_HOME") or os.path.join(os.path.expanduser("~"), ".cache", "huggingface"),
                       "hub", "models--Systran--faster-whisper-" + MULTILINGUAL_MODEL)
    if os.path.isdir(hub):
        print(f"[stt] multilingual model '{MULTILINGUAL_MODEL}' active "
              f"(languages: {sorted(WHISPER_LANGUAGES)}, auto-detected)")
        _WHISPER_SPEC = (MULTILINGUAL_MODEL, None)
    else:
        print(f"[stt] languages {sorted(WHISPER_LANGUAGES)} configured but the multilingual "
              f"model is not cached — run install.sh; using {WHISPER_MODEL} (en only)")
        _WHISPER_SPEC = (WHISPER_MODEL, "en")
    return _WHISPER_SPEC


def run_voice_assistant(notify=None, controls=None, mode="ptt", device=None):
    from faster_whisper import WhisperModel
    print("loading whisper...")
    emit(notify, "Starting", "Loading Whisper…")
    model_name, language = whisper_spec()
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    load_timers()
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
                handle(text, stt_ms, notify)
            except Exception as exc:
                print(f"\n  turn failed: {exc}")
                emit(notify, "Something went wrong", str(exc))
                time.sleep(2)
                emit(notify, "Ready", ready_text(rec.wake))
            finally:
                time.sleep(0.3)
                rec.paused = False

    def ptt_turn(audio):
        emit(notify, "Transcribing", "Working out what you said…")
        try:
            text, ms = transcribe(audio, COMMAND_PROMPT)
        except Exception as exc:
            emit(notify, "Something went wrong", str(exc))
            return
        run_turn(text, ms)

    def wake_loop():
        while True:
            try:
                audio = rec.segments.get(timeout=1)
            except queue.Empty:
                if armed_until[0] and time.time() > armed_until[0]:
                    armed_until[0] = 0
                    emit(notify, "Ready", ready_text(rec.wake))
                continue
            if not rec.wake or busy.locked():
                continue
            try:
                text, ms = transcribe(audio, WAKE_PROMPT)
            except Exception as exc:
                print(f"\n  transcribe failed: {exc}")
                continue
            m = WAKE.match(text)
            if m:
                rest = text[m.end():].strip(" .,!?")
                if rest:
                    armed_until[0] = 0
                    run_turn(rest, ms)
                else:
                    with busy:
                        rec.paused = True
                        say(say_line("wake"), notify)
                        time.sleep(0.2)
                        rec.paused = False
                    armed_until[0] = time.time() + WAKE_WINDOW
                    emit(notify, "Listening", "Go ahead…")
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
            emit(notify, "Ready", ready_text(rec.wake))

    def start_recording():
        if not rec.wake and not rec.on and not busy.locked():
            rec.start()
            print("\n[listening]", end="", flush=True)
            emit(notify, "Listening", "Release right Alt when you\u2019re done")

    def stop_recording():
        if rec.on:
            audio = rec.stop()
            if len(audio) > SAMPLE_RATE * 0.3:
                threading.Thread(target=ptt_turn, args=(audio,), daemon=True).start()

    def timer_done(t):
        with busy:
            rec.paused = True
            try:
                emit(notify, "Time's up", t["label"] or "Timer finished")
                chime()
                say(timer_done_line(t), notify)
            finally:
                time.sleep(0.3)
                rec.paused = False
        emit(notify, "Ready", ready_text(rec.wake))

    start_timer_loop(timer_done)
    threading.Thread(target=warm_cache, daemon=True).start()
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

    if keyboard is None:
        print("[ptt] no keyboard listener (headless) — use --wake or the web remote")
        threading.Event().wait()
    else:
        with keyboard.Listener(on_press=on_press, on_release=on_release) as l:
            l.join()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="skip the mic, run one turn on this transcript")
    ap.add_argument("--ui", action="store_true", help="show the floating status window (tray icon)")
    ap.add_argument("--wake", action="store_true", help="always listening, say \"Hey Jev\" instead of holding Alt")
    ap.add_argument("--remote", action="store_true", help="serve the browser mic/PTT remote")
    ap.add_argument("--device", help="input device name/index for the mic (see --list-devices)")
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
    if not FISH_KEY:
        sys.exit("need FISH_AUDIO_API_KEY in Credential Manager or .env")
    if decision_backend() is None:
        sys.exit("need a decision backend in Credential Manager or .env: "
                 "TYPESAFE_API_KEY, or KEV_URL + KEV_API_KEY, or OPENROUTER_API_KEY")
    if args.text:
        handle(args.text)
        return
    run_voice_assistant(mode="wake" if args.wake else "ptt", device=device)


if __name__ == "__main__":
    main()
