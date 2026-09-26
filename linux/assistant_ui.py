"""Small status window for the Hey Jev voice assistant on Windows (tkinter + pystray tray icon)."""
import os
import queue
import sys
import threading

import tkinter as tk

from secrets_store import KEY_NAMES, get_secret, missing_secrets, save_secret


BASE_HEIGHT, ROW = 154, 24
HINTS = {"ptt": "Hold right Alt to talk", "wake": "Say \u201cHey Jev\u201d, then your command"}
MODES = ("ptt", "wake")

STATUS_COLORS = {
    "Starting": "#e0913d",
    "Ready": "#3fbf5f",
    "Listening": "#e04545",
    "Transcribing": "#3d7be0",
    "Thinking": "#9355d6",
    "Doing it": "#e0913d",
    "Speaking": "#3fbfb5",
    "Something went wrong": "#e04545",
    "Time's up": "#d6c437",
}

ICON_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "icon.png"))


def make_tray_image():
    try:
        from PIL import Image
        if os.path.exists(ICON_PATH):
            return Image.open(ICON_PATH).convert("RGBA").resize((64, 64))
    except Exception:
        pass
    return None


class App:
    def __init__(self):
        self.controls = queue.Queue()
        self.worker_started = False
        self.mode = self._load_pref("mode", "ptt")
        if self.mode not in MODES:
            self.mode = "ptt"
        self.on_top = self._load_pref("keep_on_top", False)

        self.root = tk.Tk()
        self.root.title("Hey Jev - Fish Audio")
        self.root.geometry("420x154+80+80")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e22")
        self.root.attributes("-topmost", self.on_top)

        body = tk.Frame(self.root, bg="#1e1e22")
        body.pack(fill="both", expand=True, padx=16, pady=10)

        top = tk.Frame(body, bg="#1e1e22")
        top.pack(fill="x")
        self.dot = tk.Label(top, text="\u25cf", fg=STATUS_COLORS["Starting"], bg="#1e1e22", font=("Segoe UI", 16))
        self.dot.pack(side="left")
        self.status = tk.Label(top, text="Starting", fg="#ffffff", bg="#1e1e22", font=("Segoe UI Semibold", 15), anchor="w")
        self.status.pack(side="left", padx=(8, 0))
        keys_btn = tk.Button(top, text="Keys\u2026", command=self.show_settings, bd=0, bg="#2c2c31", fg="#e8e8e8",
                             activebackground="#3a3a40", activeforeground="#ffffff", padx=10, pady=1)
        keys_btn.pack(side="right")

        self.detail = tk.Label(body, text="Loading Whisper\u2026", fg="#9a9aa2", bg="#1e1e22", font=("Segoe UI", 10), anchor="w")
        self.detail.pack(fill="x", pady=(2, 4))

        bottom = tk.Frame(body, bg="#1e1e22")
        bottom.pack(fill="x", side="bottom")
        self.hint = tk.Label(bottom, text=HINTS[self.mode], fg="#6f6f77", bg="#1e1e22", font=("Segoe UI", 9))
        self.hint.pack(side="left")

        self.mode_var = tk.StringVar(value={"ptt": "Hold Alt", "wake": "Hey Jev"}[self.mode])
        for text, mode in (("Hold Alt", "ptt"), ("Hey Jev", "wake")):
            rb = tk.Radiobutton(bottom, text=text, variable=self.mode_var, value=text,
                                command=self._mode_changed, indicatoron=False, bd=0,
                                selectcolor="#3d3d45", bg="#1e1e22", fg="#9a9aa2",
                                activebackground="#2c2c31", activeforeground="#ffffff",
                                padx=10, pady=2, highlightthickness=0)
            rb.pack(side="right", padx=(4, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._hide)

        self.timer_rows = []
        self.tray = None
        self._start_tray()
        self.root.after(500, self._tick)
        if missing_secrets():
            self.notify("Starting", "Add your API keys to begin")
            self.root.after(300, self.show_settings)
        else:
            self._start_worker()

    # ------------------------------------------------------------- prefs
    @staticmethod
    def _pref_path():
        return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "heyjev.win.json")

    def _load_pref(self, key, default):
        try:
            import json
            with open(self._pref_path(), encoding="utf-8") as f:
                return json.load(f).get(key, default)
        except Exception:
            return default

    def _save_pref(self, key, value):
        import json
        try:
            data = {}
            if os.path.exists(self._pref_path()):
                with open(self._pref_path(), encoding="utf-8") as f:
                    data = json.load(f)
            data[key] = value
            with open(self._pref_path(), "w", encoding="utf-8") as f:
                json.dump(data, f)
        except Exception:
            pass

    # ------------------------------------------------------------- tray
    def _start_tray(self):
        try:
            import pystray
            img = make_tray_image()
            if img is None:
                from PIL import Image, ImageDraw
                img = Image.new("RGBA", (64, 64), (30, 30, 34, 255))
                d = ImageDraw.Draw(img)
                d.ellipse((16, 16, 48, 48), fill=(63, 191, 95, 255))
            self.tray = pystray.Icon("heyjev", img, "Hey Jev - Fish Audio", menu=pystray.Menu(
                pystray.MenuItem("Show", self._tray_show, default=True),
                pystray.MenuItem("Quit", self._tray_quit),
            ))
            threading.Thread(target=self.tray.run, daemon=True).start()
        except Exception as e:
            print(f"(no tray icon: {e})")

    def _tray_show(self, icon=None, item=None):
        self.root.after(0, self._show)

    def _tray_quit(self, icon=None, item=None):
        self.root.after(0, self._quit)

    def _hide(self):
        self.root.withdraw()

    def _show(self):
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", self.on_top)

    def _quit(self):
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.root.destroy()
        os._exit(0)

    # ------------------------------------------------------------- worker
    def _start_worker(self):
        if self.worker_started:
            return
        self.worker_started = True
        threading.Thread(target=self._run_assistant, daemon=True).start()

    def _run_assistant(self):
        from siri import run_voice_assistant
        try:
            run_voice_assistant(self.notify, self.controls, self.mode)
        except Exception as exc:
            self.notify("Something went wrong", str(exc))

    def _mode_changed(self):
        self.mode = {"Hold Alt": "ptt", "Hey Jev": "wake"}[self.mode_var.get()]
        self._save_pref("mode", self.mode)
        self.hint.config(text=HINTS[self.mode])
        self.controls.put(("mode", self.mode))

    # ------------------------------------------------------------- status
    def notify(self, state, detail=""):
        self.root.after(0, self._update_status, str(state), str(detail))

    def _update_status(self, state, detail):
        self.status.config(text=state)
        self.detail.config(text=detail)
        self.dot.config(fg=STATUS_COLORS.get(state, "#ffffff"))

    def _tick(self):
        try:
            import siri
            timers = siri.timer_snapshot()[:3]
        except Exception:
            timers = []
        if len(timers) != len(self.timer_rows):
            self._layout_timer_rows(len(timers))
        for (name_label, time_label), (name, left) in zip(self.timer_rows, timers):
            name_label.config(text=name)
            total = int(left + 0.999)
            h, rem = divmod(total, 3600)
            m, sec = divmod(rem, 60)
            time_label.config(text=f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}")
        self.root.after(500, self._tick)

    def _layout_timer_rows(self, count):
        for name_label, time_label in self.timer_rows:
            name_label.destroy()
            time_label.destroy()
        self.timer_rows = []
        for i in range(count):
            row = tk.Frame(self.root, bg="#1e1e22")
            row.pack(fill="x", pady=0)
            name_label = tk.Label(row, text="", fg="#9a9aa2", bg="#1e1e22", font=("Segoe UI", 10), anchor="w")
            name_label.pack(side="left")
            time_label = tk.Label(row, text="", fg="#3fbfb5", bg="#1e1e22", font=("Consolas", 10))
            time_label.pack(side="right")
            self.timer_rows.append((name_label, time_label))

    # ------------------------------------------------------------- keys
    def show_settings(self):
        if getattr(self, "settings_win", None) and self.settings_win.winfo_exists():
            self.settings_win.lift()
            return
        win = tk.Toplevel(self.root)
        win.title("API keys")
        win.geometry("400x230")
        win.configure(bg="#1e1e22")
        win.attributes("-topmost", True)
        self.settings_win = win

        tk.Label(win, text="API keys", fg="#ffffff", bg="#1e1e22", font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=16, pady=(12, 0))
        tk.Label(win, text="Saved in Windows Credential Manager. Existing keys stay hidden.",
                 fg="#9a9aa2", bg="#1e1e22", font=("Segoe UI", 9)).pack(anchor="w", padx=16)

        frame = tk.Frame(win, bg="#1e1e22")
        frame.pack(fill="both", expand=True, padx=16, pady=8)
        self.key_fields = {}
        for row, (title, key_name) in enumerate((("TypeSafe", "TYPESAFE_API_KEY"),
                                                 ("Fish Audio", "FISH_AUDIO_API_KEY"),
                                                 ("OpenRouter", "OPENROUTER_API_KEY"))):
            tk.Label(frame, text=title, fg="#e8e8e8", bg="#1e1e22", font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=4)
            entry = tk.Entry(frame, show="\u2022", width=34, bd=0, bg="#2c2c31", fg="#ffffff",
                             insertbackground="#ffffff", relief="flat", ipady=3)
            entry.grid(row=row, column=1, padx=(10, 0), pady=4)
            self.key_fields[key_name] = entry

        msg = tk.Label(win, text="", fg="#e04545", bg="#1e1e22", font=("Segoe UI", 9))
        msg.pack(anchor="w", padx=16)
        btns = tk.Frame(win, bg="#1e1e22")
        btns.pack(fill="x", padx=16, pady=(0, 12))
        save = tk.Button(btns, text="Save", command=lambda: self._save_settings(msg, win), bd=0,
                         bg="#3fbf5f", fg="#10240f", activebackground="#4dd06e", padx=14, pady=3)
        save.pack(side="right")
        cancel = tk.Button(btns, text="Cancel", command=win.destroy, bd=0,
                           bg="#2c2c31", fg="#e8e8e8", activebackground="#3a3a40", padx=14, pady=3)
        cancel.pack(side="right", padx=(0, 8))

    def _save_settings(self, msg, win):
        try:
            for key_name in KEY_NAMES:
                value = self.key_fields[key_name].get()
                if value:
                    save_secret(key_name, value)
            still_missing = missing_secrets()
            if still_missing:
                names = ", ".join(n.replace("_API_KEY", "").replace("_", " ").title() for n in still_missing)
                msg.config(text=f"Still needed: {names}")
                return
            from siri import reload_keys
            reload_keys()
            win.destroy()
            self._start_worker()
        except Exception as exc:
            msg.config(text=str(exc))


def run_app():
    App().root.mainloop()
