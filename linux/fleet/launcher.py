"""hey-jev fleet launcher backend: static site + same-origin health proxy."""
import asyncio
import json
import os

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

BASE = os.path.dirname(os.path.abspath(__file__))
app = FastAPI(title="hey-jev fleet launcher")


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
