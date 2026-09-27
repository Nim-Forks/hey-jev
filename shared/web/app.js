// hey-jev web remote: press-and-hold PTT, streams PCM to the PC over
// WebSocket, plays the reply wav.
const $ = (id) => document.getElementById(id);
const COLORS = {
  Starting: "#e0913d", Ready: "#3fbf5f", Listening: "#e04545",
  Transcribing: "#3d7be0", Thinking: "#9355d6", "Doing it": "#e0913d",
  Speaking: "#3fbfb5", "Something went wrong": "#e04545", "Time's up": "#d6c437",
};
let ws = null, wsReady = false, session = null, workletNode = null;
let recording = false, chunksSent = 0;

// ------------------------------------------------------------- keys (localStorage)
const KEY_FIELDS = [
  ["TYPESAFE_API_KEY", "TypeSafe (Jev) — leave empty if using KEV"],
  ["FISH_AUDIO_API_KEY", "Fish Audio (required for the voice)"],
  ["OPENROUTER_API_KEY", "OpenRouter (optional, questions)"],
  ["KEV_URL", "KEV URL (with KEV_API_KEY: overrides TypeSafe)"],
  ["KEV_API_KEY", "KEV API key"],
];
function loadKeys() {
  try { return JSON.parse(localStorage.getItem("heyjev.keys") || "{}"); }
  catch { return {}; }
}
function saveKeys() {
  const keys = {};
  for (const [name] of KEY_FIELDS) {
    const v = $(`k-${name}`) ? $(`k-${name}`).value.trim() : "";
    if (v) keys[name] = v;
  }
  localStorage.setItem("heyjev.keys", JSON.stringify(keys));
  return keys;
}

// ------------------------------------------------------------- memory (localStorage)
function loadMemory() {
  try { return JSON.parse(localStorage.getItem("heyjev.memory") || "[]"); }
  catch { return []; }
}
function saveMemory(list) {
  localStorage.setItem("heyjev.memory", JSON.stringify(list.slice(0, 50)));
}
function syncMemory() {
  send({ type: "memory-sync", items: loadMemory() });
}
function applyMemoryOp(op, text) {
  const mem = loadMemory();
  if (op === "save") {
    mem.push(text);
    saveMemory(mem);
    setStatusDetailHint("Saved in this device's memory (" + mem.length + " facts)");
  } else if (op === "forget") {
    const kept = (text === "*") ? [] : mem.filter((m) => !m.toLowerCase().includes(text.toLowerCase()));
    saveMemory(kept);
    setStatusDetailHint("Memory now has " + kept.length + " facts");
  }
  syncMemory();
}
function setStatusDetailHint(text) {
  const d = $("detail");
  if (d && (document.getElementById("state").textContent === "Ready")) d.textContent = text;
}

// ------------------------------------------------------------- server-key quota
function loadUses() {
  const n = parseInt(localStorage.getItem("heyjev.serverUses") || "0", 10);
  return Number.isFinite(n) && n > 0 ? n : 0;
}
function saveUses(n) {
  localStorage.setItem("heyjev.serverUses", String(Math.max(0, n)));
}

// ------------------------------------------------------------- ntfy (per device)
function loadNtfy() { return localStorage.getItem("heyjev.ntfy") || ""; }
function saveNtfy(url) { localStorage.setItem("heyjev.ntfy", url); }
function syncNtfy() { send({ type: "ntfy-sync", url: loadNtfy() }); }
function askNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    try { Notification.requestPermission().catch(() => {}); } catch {}
  }
}

// ------------------------------------------------------------- websocket
let retryTimer = null, retries = 0, sentNtfy = null;
const BUSY_STATES = ["Transcribing", "Thinking", "Doing it", "Speaking"];
function setStatus(state, detail) {
  $("dot").style.color = COLORS[state] || "#fff";
  $("state").textContent = state;
  $("cancelbtn").style.display = BUSY_STATES.includes(state) ? "inline-block" : "none";
  clearInterval(setStatus._t);
  setStatus._base = detail || "";
  $("detail").textContent = setStatus._base;
  if (["Transcribing", "Thinking", "Doing it", "Speaking"].includes(state)) {
    const t0 = Date.now();
    setStatus._t = setInterval(() => {
      $("detail").textContent = setStatus._base + " (" + ((Date.now() - t0) / 1000 | 0) + "s)";
    }, 1000);
  }
}
function send(obj) { if (wsReady && ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }

function connect() {
  if (ws && ws.readyState === 0) return;
  clearTimeout(retryTimer);
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => {
    retries = 0;
    wsReady = true;
    const auth = { type: "auth" };
    const keys = loadKeys();
    const token = localStorage.getItem("heyjev.token");
    if (token) auth.token = token;
    if (Object.keys(keys).length) auth.keys = keys;
    auth.memory = loadMemory();
    auth.uses = loadUses();
    auth.ntfy = loadNtfy();
    sentNtfy = auth.ntfy;
    send(auth);
    setStatus("Ready", "Connected");
    pollTimers();
    send({ type: "tiles" });
  };
  ws.onclose = () => {
    wsReady = false;
    setStatus("Something went wrong", "Disconnected — retrying…");
    const delay = Math.min(8000, 1000 * 2 ** retries++);
    retryTimer = setTimeout(connect, delay);
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      const msg = JSON.parse(ev.data);
      if (msg.type === "state") {
        setStatus(msg.state, msg.detail);
      } else if (msg.type === "heard") {
        $("heard").innerHTML = "heard: <b>" + escapeHtml(msg.text) + "</b>";
        lastEntry = { heard: msg.text, line: "", ts: Date.now() };
      } else if (msg.type === "reply") {
        $("heard").innerHTML = "she said: <b>" + escapeHtml(msg.line) + "</b>";
        if (lastEntry && !lastEntry.line) lastEntry.line = msg.line;
        else lastEntry = { heard: "(typed/replayed)", line: msg.line, ts: Date.now() };
        pushHistory(lastEntry);
        lastEntry = null;
      } else if (msg.type === "cost") {
        if (msg.total > 0) {
          $("heard").innerHTML += ' <span class="cost">$' + msg.total.toFixed(5) + "</span>";
          const h = loadHistory();
          if (h.length) { h[0].cost = msg.total; saveHistory(h); renderHistory(); }
        }
      } else if (msg.type === "auth-error") {
        setStatus("Something went wrong", "Access token required");
        showTokenPrompt();
      } else if (msg.type === "timers") {
        renderTimers(msg.timers);
      } else if (msg.type === "tiles") {
        lastTiles = msg.tiles;
        renderTiles();
      } else if (msg.type === "tile-weather") {
        locWeather = msg.weather;
        locWeatherUntil = Date.now() + 30 * 60 * 1000;
        renderTiles();
        setStatusDetailHint("Weather for your location (keeps for 30 min)");
      } else if (msg.type === "usage") {
        saveUses(msg.used);
        const left = msg.limit - msg.used;
        if (left <= 2) {
          setStatusDetailHint("Server keys: only " + left + " free turns left — add your own in Settings");
        }
      } else if (msg.type === "key-limit") {
        setStatus("Something went wrong",
          "Server key limit reached (" + msg.used + "/" + msg.limit + ") — opening Settings…");
        setTimeout(() => { location.href = "/settings"; }, 1500);
      } else if (msg.type === "memory") {
        applyMemoryOp(msg.op, msg.text);
      } else if (msg.type === "timer-fired") {
        setStatus("Time's up", msg.label);
        try { navigator.vibrate?.([300, 100, 300]); } catch {}
        try {
          if ("Notification" in window && Notification.permission === "granted") {
            new Notification("Hey Jev — " + msg.label, { body: msg.line, icon: "/favicon.png" });
          }
        } catch {}
        unlockAudio();
        send({ type: "replay", text: msg.line });
      }
    } else {
      playWav(ev.data);
    }
  };
}

function showTokenPrompt() {
  $("tokeninput").value = localStorage.getItem("heyjev.token") || "";
  $("tokenbox").style.display = "flex";
  setTimeout(() => $("tokeninput").focus(), 60);
}
function saveTokenAndConnect() {
  const t = $("tokeninput").value.trim();
  if (t) localStorage.setItem("heyjev.token", t);
  else localStorage.removeItem("heyjev.token");
  $("tokenbox").style.display = "none";
  clearTimeout(retryTimer);
  retries = 0;
  try { ws && ws.readyState < 3 && ws.close(); } catch {}
  setStatus("Starting", "Reconnecting…");
  connect();
}

// ------------------------------------------------------------- audio capture
async function startMic() {
  const stream = await navigator.mediaDevices.getUserMedia(
    { audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } });
  const ctx = new AudioContext({ sampleRate: 48000 });
  await ctx.audioWorklet.addModule("/worklet.js");
  workletNode = new AudioWorkletNode(ctx, "resample16k", { numberOfOutputs: 0 });
  const src = ctx.createMediaStreamSource(stream);
  src.connect(workletNode);
  workletNode.port.onmessage = (e) => {
    if (recording && wsReady) {
      ws.send(e.data);
      chunksSent += e.data.byteLength;
      const f = e.data;
      let sum = 0;
      for (let i = 0; i < f.length; i++) sum += f[i] * f[i];
      const rms = Math.sqrt(sum / f.length);
      $("levelbar").style.width = Math.min(100, rms * 600) + "%";
    }
  };
  session = { ctx, stream };
}

async function pttDown(ev) {
  ev.preventDefault();
  askNotificationPermission();
  if (!wsReady) {
    clearTimeout(retryTimer);
    setStatus("Something went wrong", "Reconnecting…");
    retries = 0;
    connect();
    return;
  }
  if (recording) return;
  unlockAudio();
  if (!session) await startMic();
  if (session.ctx.state === "suspended") await session.ctx.resume();
  recording = true; chunksSent = 0;
  send({ type: "audio-start", format: "f32le", rate: 16000, channels: 1 });
  $("ptt").classList.add("held");
  navigator.wakeLock?.request?.("screen").then(l => { window._wl = l; }).catch(() => {});
}
function pttUp(ev) {
  ev.preventDefault();
  if (!recording) return;
  recording = false;
  send({ type: "audio-end" });
  $("ptt").classList.remove("held");
  $("levelbar").style.width = "0";
  setStatus("Transcribing", "Working out what you said…");
  window._wl?.release?.().catch(() => {});
}

// ------------------------------------------------------------- playback
let audioCtx = null;
function unlockAudio() {
  audioCtx = audioCtx || new AudioContext();
  audioCtx.resume().catch(() => {});
  if (!audioCtx._unlocked) {
    const silent = audioCtx.createBuffer(1, 1, 22050);
    const src = audioCtx.createBufferSource();
    src.buffer = silent;
    src.connect(audioCtx.destination);
    src.start();
    audioCtx._unlocked = true;
  }
}
function playWav(buf) {
  audioCtx = audioCtx || new AudioContext();
  const play = (decoded) => {
    const src = audioCtx.createBufferSource();
    src.buffer = decoded;
    src.connect(audioCtx.destination);
    src.start();
  };
  audioCtx.decodeAudioData(buf).then(play).catch(() => {
    audioCtx.resume().then(() => audioCtx.decodeAudioData(buf).then(play))
      .catch((e) => setStatus("Something went wrong", "cannot play reply: " + e.message));
  });
}

// ------------------------------------------------------------- timers
let timerTimer = null;
function pollTimers() {
  clearInterval(timerTimer);
  timerTimer = setInterval(() => { send({ type: "timers" }); send({ type: "tiles" }); }, 500);
  setInterval(() => send({ type: "tiles" }), 60000);
  setInterval(tickClock, 1000);
  tickClock();
}
function renderTimers(timers) {
  const ul = $("timers"); ul.innerHTML = "";
  for (const [name, left] of timers) {
    const total = Math.ceil(left), h = Math.floor(total / 3600),
      m = Math.floor((total % 3600) / 60), s = total % 60;
    const li = document.createElement("li");
    li.textContent = `${name} — ${h ? h + ":" : ""}${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    ul.appendChild(li);
  }
}

// ------------------------------------------------------------- tiles
let lastTiles = null, locWeather = null, locWeatherUntil = 0;
function renderTiles() {
  if (!lastTiles) return;
  $("t-date").textContent = lastTiles.date || "";
  const w = (Date.now() < locWeatherUntil && locWeather) ? locWeather : lastTiles.weather;
  if (w) {
    $("t-temp").textContent = w.temp + "°";
    $("t-weather").innerHTML = escapeHtml(w.desc) + "<br>" +
      escapeHtml(w.lo) + "–" + escapeHtml(w.hi) + "° · " + escapeHtml(w.area);
  }
  updateSunTile();
}
function updateSunTile() {
  if (!lastTiles || !lastTiles.sun) return;
  const toMin = (s) => { const [h, m] = s.split(":").map(Number); return h * 60 + (m || 0); };
  const sr = toMin(lastTiles.sun.sunrise), ss = toMin(lastTiles.sun.sunset);
  const now = new Date();
  const nm = now.getHours() * 60 + now.getMinutes();
  const daytime = nm >= sr && nm < ss;
  const big = daytime ? lastTiles.sun.sunset : lastTiles.sun.sunrise;
  const label = daytime ? "sunset" : "sunrise";
  const other = daytime ? ("sunrise " + lastTiles.sun.sunrise) : ("sunset " + lastTiles.sun.sunset);
  $("t-sunrise").textContent = big;
  $("t-sunset").innerHTML = label + "<br>" + other;
}
function tickClock() {
  const now = new Date();
  $("t-clock").textContent = pad(now.getHours()) + ":" + pad(now.getMinutes());
  updateSunTile();
  const ntfy = loadNtfy();
  if (wsReady && sentNtfy !== null && ntfy !== sentNtfy) {
    sentNtfy = ntfy;
    syncNtfy();
  }
  if (lastTiles && !lastTiles.date) renderTiles();
}

// ------------------------------------------------------------- history (replayable)
let lastEntry = null;
function loadHistory() {
  let h = [];
  try { h = JSON.parse(localStorage.getItem("heyjev.history") || "[]"); } catch { h = []; }
  let changed = false;
  h.forEach((e, i) => { if (!e.id) { e.id = String(e.ts || Date.now()) + "-" + i; changed = true; } });
  if (changed) localStorage.setItem("heyjev.history", JSON.stringify(h));
  return h;
}
function saveHistory(h) { localStorage.setItem("heyjev.history", JSON.stringify(h.slice(0, 20))); }
function pushHistory(entry) {
  if (!entry.line) return;
  const h = loadHistory();
  entry.id = Date.now() + "-" + Math.random().toString(36).slice(2, 7);
  h.unshift(entry);
  saveHistory(h);
  renderHistory();
}
function deleteEntry(id) {
  saveHistory(loadHistory().filter((e) => e.id !== id));
  renderHistory();
}
function deleteDay(dayStr) {
  saveHistory(loadHistory().filter((e) => dayOf(e.ts) !== dayStr));
  renderHistory();
}
function clearAllHistory() {
  if (!confirm("Clear the entire history?")) return;
  saveHistory([]);
  renderHistory();
}
function dayOf(ts) {
  const d = new Date(ts || Date.now());
  const wd = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][d.getDay()];
  return wd + " " + pad(d.getDate()) + "." + pad(d.getMonth() + 1) + "." + d.getFullYear();
}
function fmtTime(ts) {
  const d = new Date(ts || Date.now());
  return pad(d.getHours()) + ":" + pad(d.getMinutes());
}
function pad(n) { return String(n).padStart(2, "0"); }
function renderHistory() {
  const ul = $("history");
  ul.innerHTML = "";
  const items = loadHistory();
  $("historycount").textContent = items.length ? "(" + items.length + ")" : "(empty)";
  let lastDay = null;
  for (const e of items) {
    const day = dayOf(e.ts);
    if (day !== lastDay) {
      lastDay = day;
      const head = document.createElement("div");
      head.className = "hday";
      const label = document.createElement("span");
      label.textContent = day;
      const del = document.createElement("button");
      del.className = "trash";
      del.textContent = "🗑";
      del.title = "clear this day";
      del.onclick = () => { deleteDay(day); };
      head.append(label, del);
      ul.appendChild(head);
    }
    const li = document.createElement("li");
    const edit = document.createElement("button");
    edit.className = "editbtn";
    edit.textContent = "✎";
    edit.title = "edit before sending";
    edit.onclick = () => {
      const box = $("textbox");
      box.value = e.heard || "";
      box.focus();
      box.setSelectionRange(box.value.length, box.value.length);
      setStatus("Ready", "Edit and press Enter…");
    };
    const rep = document.createElement("button");
    rep.className = "rerun";
    rep.textContent = "↻";
    rep.title = "run this command again";
    rep.onclick = () => {
      if (!wsReady || !e.heard || e.heard.startsWith("(")) return;
      setStatus("Thinking", e.heard);
      send({ type: "text", text: e.heard });
    };
    const main = document.createElement("span");
    main.className = "hmain";
    main.innerHTML = fmtTime(e.ts) + " " + escapeHtml(e.heard || "…") +
      " <i>→ " + escapeHtml(e.line) + "</i>" +
      (e.cost ? ' <span class="cost">$' + e.cost.toFixed(5) + "</span>" : "");
    const btn = document.createElement("button");
    btn.textContent = "▶";
    btn.title = "replay";
    btn.onclick = () => {
      unlockAudio();
      setStatus("Speaking", e.line);
      send({ type: "replay", text: e.line });
    };
    const del = document.createElement("button");
    del.className = "trash";
    del.textContent = "🗑";
    del.title = "delete";
    del.onclick = () => { deleteEntry(e.id); };
    li.append(edit, rep, main, btn, del);
    ul.appendChild(li);
  }
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ------------------------------------------------------------- typed text
function sendText() {
  const box = $("textbox");
  const text = box.value.trim();
  if (!text || !wsReady) return;
  askNotificationPermission();
  unlockAudio();
  box.value = "";
  setStatus("Thinking", text);
  send({ type: "text", text });
}

// ------------------------------------------------------------- wire-up
window.addEventListener("load", () => {
  connect();
  renderHistory();
  const ptt = $("ptt");
  ptt.addEventListener("pointerdown", pttDown);
  ptt.addEventListener("pointerup", pttUp);
  ptt.addEventListener("pointerleave", pttUp);
  ptt.addEventListener("contextmenu", (e) => e.preventDefault());
  $("textform").addEventListener("submit", (e) => { e.preventDefault(); sendText(); });
  $("t-weather-tile").addEventListener("click", requestLocationWeather);
  $("clearhist").addEventListener("click", (e) => { e.preventDefault(); e.stopPropagation(); clearAllHistory(); });
  $("cancelbtn").addEventListener("click", () => {
    send({ type: "cancel" });
    setStatus("Ready", "Cancelled — the server stops at its next checkpoint");
  });
  $("tokensave").addEventListener("click", saveTokenAndConnect);
  $("tokeninput").addEventListener("keydown", (e) => { if (e.key === "Enter") saveTokenAndConnect(); });
});

function requestLocationWeather() {
  if (!wsReady) return;
  if (!navigator.geolocation) {
    setStatusDetailHint("This browser has no geolocation — showing PC-area weather");
    return;
  }
  setStatusDetailHint("Getting your location…");
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      locWeatherUntil = Date.now() + 30 * 60 * 1000;
      send({ type: "weather-at", lat: pos.coords.latitude, lng: pos.coords.longitude });
      setStatusDetailHint("Fetching weather for your location…");
    },
    (err) => setStatusDetailHint("Location denied/unavailable — showing PC-area weather"),
    { timeout: 10000, maximumAge: 300000 });
}
