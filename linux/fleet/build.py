"""Ship the fleet site's data + generated pages. Runs ON the geekom:

    /home/nimesin/deciders/opendecider/venv/bin/python build.py

Inputs:  ~/hey-jev-prod (git log, shared/personas catalog), instances.json
Outputs: checks.json, personas.json, changelog.json, docs/*.html, qr/*.svg
No secrets: this only builds public data.
"""
import json
import os
import subprocess
import sys

import markdown
import qrcode
import qrcode.image.svg

HERE = os.path.dirname(os.path.abspath(__file__))
PROD = "/home/nimesin/hey-jev-prod"


def build_checks():
    checks = []
    for entry in sorted(os.listdir("/home/nimesin/combo")):
        envf = f"/home/nimesin/combo/{entry}/.env"
        try:
            for line in open(envf):
                if line.startswith("REMOTE_PORT="):
                    checks.append({"name": entry, "target": f"http://127.0.0.1:{line.split('=',1)[1].strip()}/health"})
        except OSError:
            pass
    for name, envf in (("beta", "/home/nimesin/hey-jev/.env"), ("prod", "/home/nimesin/hey-jev-prod/.env")):
        try:
            for line in open(envf):
                if line.startswith("REMOTE_PORT="):
                    checks.append({"name": name, "target": f"http://127.0.0.1:{line.split('=',1)[1].strip()}/health"})
        except OSError:
            pass
    checks.append({"name": "alpha", "target": "https://hey-jev.overgate.online/health"})
    json.dump(checks, open(os.path.join(HERE, "checks.json"), "w"))
    return f"checks: {len(checks)}"


def build_personas():
    sys.path.insert(0, PROD)
    try:
        from shared import personas
        npersonas = personas.catalog()
        json.dump(npersonas, open(os.path.join(HERE, "personas.json"), "w"), indent=1)
        return f"personas: {len(npersonas)}"
    finally:
        sys.path.pop(0)


def build_changelog():
    out = subprocess.run(
        ["git", "-C", PROD, "log", "--pretty=format:%h|%ad|%s", "--date=short", "-40"],
        capture_output=True, text=True, check=True).stdout
    rows = [dict(zip(("hash", "date", "subject"), ln.split("|", 2))) for ln in out.splitlines() if ln.strip()]
    json.dump(rows, open(os.path.join(HERE, "changelog.json"), "w"), indent=1)
    return f"changelog: {len(rows)}"


def build_docs():
    n = 0
    flatdir = os.path.join(HERE, "docs")
    os.makedirs(flatdir, exist_ok=True)
    css = ("body{font:14px/1.65 -apple-system,Segoe UI,Roboto,sans-serif;background:#0b0e14;"
           "color:#c8d1e0;max-width:900px;margin:32px auto;padding:0 16px}"
           "h1,h2,h3{color:#8ab4ff}a{color:#6fa8ff}code{background:#1b2331;padding:1px 5px;border-radius:4px}"
           "pre{background:#131822;padding:12px;border-radius:8px;overflow:auto}td,th{border:1px solid #2a3444;"
           "padding:4px 8px}table{border-collapse:collapse}")
    srcs = {"07-combo-instances", "08-systemone-backends", "09-instance-inventory"}
    for grupo in srcs:
        s = os.path.join(PROD, "linux", "doc", f"{grupo}.md")
        html = markdown.markdown(open(s, encoding="utf-8").read(), extensions=["tables", "fenced_code"])
        open(os.path.join(flatdir, f"{grupo}.html"), "w", encoding="utf-8").write(
            f"<!DOCTYPE html><html><head><meta charset='utf-8'><title>hey-jev {grupo}</title>"
            f"<style>{css}</style></head><body>{html}</body></html>")
        n += 1
    return f"docs: {n}"


def build_qr():
    instances = json.load(open(os.path.join(HERE, "instances.json")))
    qrdir = os.path.join(HERE, "qr")
    os.makedirs(qrdir, exist_ok=True)
    for inst in instances["instances"]:
        img = qrcode.make(inst["url"], image_factory=qrcode.image.svg.SvgPathImage, box_size=10)
        img.save(os.path.join(qrdir, f"{inst['name']}.svg"))
    return f"qr: {len(instances['instances'])}"


if __name__ == "__main__":
    print(build_checks())
    print(build_personas())
    print(build_changelog())
    print(build_docs())
    print(build_qr())
    print("build ok")
