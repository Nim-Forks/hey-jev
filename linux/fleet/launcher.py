"""hey-jev fleet launcher backend: static site + same-origin health proxy +
persona proposal queue (page form -> validated queue -> admin adoption)."""
import asyncio
import hmac
import json
import os
import re
import subprocess
import threading
import time

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

BASE = os.path.dirname(os.path.abspath(__file__))
PROD = "/home/nimesin/hey-jev-prod"
REQUESTS = os.path.join(BASE, "persona-requests.json")
MASTER = os.path.join(BASE, "personas-catalog.json")
_req_lock = threading.Lock()
META_RE = re.compile(r"^https?://(?:www\.)?archive\.org/details/([^/?#]+)")
_DL_RE = re.compile(r"^https?://(?:www\.)?archive\.org/download/([^/]+)/([^/?#]+)$")


def _prod_env(name):
    try:
        for line in open(os.path.join(PROD, ".env")):
            if line.startswith(name + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


def _authed(request) -> bool:
    """The fleet access token gates proposals and adoption. Read from the prod
    checkout's .env at call time, compared constant-time, never echoed."""
    token = _prod_env("REMOTE_TOKEN")
    auth = request.headers.get("authorization", "")
    return bool(token and hmac.compare_digest(auth, "Bearer " + token))


def _requests():
    try:
        return json.load(open(REQUESTS, encoding="utf-8"))
    except Exception:
        return []


@app.get("/api/persona/requests")
async def persona_requests():
    return {"requests": _requests()}


@app.post("/api/persona/propose")
async def persona_propose(request):
    """Public form body {name, reader, description, source_url, start_s, duration_s}
    + Bearer = the fleet access token. Strict validation; nothing is fetched
    except archive.org item metadata, and nothing is adopted automatically."""
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = json.loads(await request.body())
    except Exception:
        return JSONResponse({"error": "bad json"}, status_code=400)
    name = re.sub(r"[^a-z0-9_-]", "", str(body.get("name", "")).lower())[:32]
    reader = str(body.get("reader", "")).strip()[:80]
    desc = str(body.get("description", "")).strip()[:120]
    url = str(body.get("source_url", "")).strip()
    m = _DL_RE.match(url)
    if not (name and reader and m):
        return JSONResponse({"error": "need name, reader and a valid archive.org/download/<item>/<file>.mp3 URL"},
                            status_code=422)
    item = m.group(1)
    try:
        r = httpx.get(f"https://archive.org/metadata/{item}", timeout=10)
        meta = r.json().get("metadata", {})
    except Exception:
        return JSONResponse({"error": "archive.org metadata fetch failed"}, status_code=502)
    licenseurl = str(meta.get("licenseurl", "") or "")
    colls = meta.get("collection") or []
    if isinstance(colls, str):
        colls = [colls]
    permissive = any(p in licenseurl.lower() for p in ("publicdomain", "cc0")) or \
        any("cc0" in (c or "").lower() for c in colls)
    if not permissive or "librivoxaudio" not in colls:
        return JSONResponse(
            {"ok": False, "name": name,
             "reason": f"license screen failed: licenseurl={licenseurl or 'none'} collections={colls}"},
            status_code=200)
    start_s = max(0.0, min(float(body.get("start_s") or 0), 3600.0))
    duration_s = max(1.0, min(float(body.get("duration_s") or 25.0), 30.0))
    entry = {"name": name, "reader": reader, "description": desc, "source_url": url,
             "source_license": "publicdomain", "start_s": start_s, "duration_s": duration_s,
             "item": item, "status": "proposed", "ts": int(time.time())}
    with _req_lock:
        reqs = _requests()
        if any(q["name"] == name for q in reqs) or any(
                q.get("item") == item and q.get("source_url") == url for q in reqs):
            return JSONResponse({"ok": True, "dup": True, "note": "already proposed"})
        reqs.append(entry)
        kept = [q for q in reqs if q.get("status") != "adopted"]
        json.dump(reqs[-50:], open(REQUESTS, "w", encoding="utf-8"), indent=1)
    return {"ok": True, "entry": entry, "note": "queued for adoption; adoption is manual"}


@app.post("/api/persona/adopt")
async def persona_adopt(request):
    """Admin action (same access token): move a proposed persona into the
    master catalog and fan the file out to every checkout root on this box.
    Instances read the catalog at call time — no restart needed."""
    if not _authed(request):
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    try:
        body = json.loads(await request.body())
    except Exception:
        return JSONResponse({"error": "bad json"}, status_code=400)
    name = re.sub(r"[^a-z0-9_-]", "", str(body.get("name", "")).lower())[:32]
    with _req_lock:
        reqs = _requests()
        pick = next((q for q in reqs if q["name"] == name and q.get("status") == "proposed"), None)
        if not pick:
            return JSONResponse({"error": f"no proposed persona named {name}"}, status_code=404)
        try:
            master = json.load(open(MASTER, encoding="utf-8"))
        except Exception:
            master = {"personas": []}
        entry = {k: pick.get(k) for k in ("name", "reader", "description", "source_url",
                                          "source_license", "start_s", "duration_s")}
        master.setdefault("personas", [])
        master["personas"] = [e for e in master["personas"] if e.get("name") != name] + [entry]
        json.dump(master, open(MASTER, "w", encoding="utf-8"), indent=1)
        for q in reqs:
            if q["name"] == name and q.get("status") == "proposed":
                q["status"] = "adopted"
                q["adopted_ts"] = int(time.time())
        json.dump(reqs[-50:], open(REQUESTS, "w", encoding="utf-8"), indent=1)
    try:
        out = subprocess.run(["bash", "-c", f"""
set -e
cp {MASTER} {PROD}/personas-catalog.json
cp {MASTER} /home/nimesin/hey-jev/personas-catalog.json
for d in /home/nimesin/combo/*/; do cp {MASTER} "$d/personas-catalog.json"; done
"""], capture_output=True, text=True, check=True)
        fanout = out.stderr.strip()
    except subprocess.CalledProcessError as e:
        return JSONResponse({"ok": True, "name": name,
                             "warning": f"catalog updated but fan-out failed: {e.stderr[:200]}"})
    return {"ok": True, "name": name, "fanned_out": True}


@app.get("/api/health")
async def health():
    try:
        checks = json.load(open(os.path.join(BASE, "checks.json")))
    except Exception:
        return JSONResponse({"error": "checks.json missing"}, status_code=503)
    loop = asyncio.get_event_loop()

    async def one(c):
        t0 = loop.time()
        try:
            r = await client.get(c["target"])
            return {"name": c["name"], "up": r.status_code == 200, "ms": int((loop.time() - t0) * 1000)}
        except Exception:
            return {"name": c["name"], "up": False, "ms": int((loop.time() - t0) * 1000)}

    async with httpx.AsyncClient(timeout=5.0) as client:
        results = await asyncio.gather(*(one(c) for c in checks))
    return {"up": sum(1 for r in results if r["up"]), "total": len(results), "results": results}


app.mount("/", StaticFiles(directory=BASE, html=True), name="static")
