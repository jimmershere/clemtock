"""clemtock control server — serves the studio UI + a small job API on floor2.

Endpoints (JSON unless noted):
  GET  /api/health                 -> {ok, jobs}
  GET  /api/library                -> assets/library.json (heroes/characters/models)
  GET  /api/recipes                -> web/recipes.json (ad formats)
  GET  /api/outputs                -> rendered MP4s in out/ (name, size, url)
  GET  /api/jobs                   -> list jobs
  GET  /api/jobs/<id>              -> {status, returncode, log, out}
  POST /api/run     {command,args} -> run an allowlisted clemtock subcommand (power/AI use)
  POST /api/build   {recipe,prompt,hero,character,model,duration} -> recipe-driven `run`

Static: /library/* -> assets/ (library + thumbs); everything else -> web/ (incl. out/ symlink).

Safe by construction: subprocess uses an argv list (no shell), the command is checked against
ALLOWED, and the vault is loaded into the process env at startup so jobs get provider keys.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from . import library as lib_mod
from . import vault as vault_mod

SCAN_EVERY = 15 * 60  # auto-rescan the asset library every 15 minutes
MAX_UPLOADS = 3

REPO = Path(__file__).resolve().parents[2]
WEB = REPO / "web"
LIB = REPO / "assets"
OUT = REPO / "out"
JOBLOG = OUT / "jobs"

ALLOWED = {"script", "assets", "video", "avatar", "compose", "run", "export", "probe",
           "accounts", "publish", "patch", "music"}

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_counter = [0]


def _new_job(argv: list[str], out_file: str | None) -> dict:
    with _lock:
        _counter[0] += 1
        jid = f"job{int(time.time())}_{_counter[0]}"
    JOBLOG.mkdir(parents=True, exist_ok=True)
    log_path = JOBLOG / f"{jid}.log"
    fh = open(log_path, "wb")
    fh.write((" ".join(argv) + "\n\n").encode())
    fh.flush()
    proc = subprocess.Popen(argv, cwd=str(REPO / "backend"), stdout=fh,
                            stderr=subprocess.STDOUT, env=os.environ.copy())
    job = {"id": jid, "argv": argv, "proc": proc, "fh": fh, "log": str(log_path),
           "out": out_file, "started": time.time()}
    _jobs[jid] = job
    return job


def _job_view(job: dict, tail: int = 8000) -> dict:
    proc = job["proc"]
    rc = proc.poll()
    status = "running" if rc is None else ("done" if rc == 0 else "failed")
    log = ""
    try:
        log = Path(job["log"]).read_text(errors="replace")[-tail:]
    except Exception:
        pass
    out_ready = bool(job["out"]) and (OUT / Path(job["out"]).name).exists()
    return {"id": job["id"], "status": status, "returncode": rc,
            "cmd": " ".join(job["argv"]), "log": log,
            "out": (f"out/{Path(job['out']).name}" if out_ready else None)}


def _clemtock_argv(command: str, args: list[str]) -> list[str]:
    return ["python3", "-m", "clemtock", command] + [str(a) for a in args]


class Handler(BaseHTTPRequestHandler):
    server_version = "clemtock/0.1"

    def log_message(self, *a):  # quiet
        pass

    # ---- helpers ----
    def _send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.is_file():
            self.send_error(404); return
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        self.wfile.write(data)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode())
        except Exception:
            return {}

    # ---- routing ----
    def do_GET(self):
        p = urlparse(self.path).path
        if p == "/api/health":
            return self._send_json({"ok": True, "jobs": len(_jobs)})
        if p == "/api/library":
            return self._send_file(LIB / "library.json")
        if p == "/api/recipes":
            return self._send_file(WEB / "recipes.json")
        if p == "/api/music":
            from .pipeline import music as music_mod
            return self._send_json({"tracks": music_mod.list_tracks(REPO)})
        if p == "/api/outputs":
            items = []
            if OUT.exists():
                for f in sorted(OUT.glob("*.mp4"), key=lambda x: -x.stat().st_mtime):
                    items.append({"name": f.name, "size": f.stat().st_size, "url": f"out/{f.name}"})
            return self._send_json({"outputs": items})
        if p == "/api/jobs":
            return self._send_json({"jobs": [_job_view(j, tail=200) for j in _jobs.values()]})
        if p.startswith("/api/jobs/"):
            job = _jobs.get(p.rsplit("/", 1)[-1])
            return self._send_json(_job_view(job)) if job else self._send_json({"error": "no such job"}, 404)
        # static
        if p in ("/", ""):
            return self._send_file(WEB / "studio.html")
        if p.startswith("/library/"):
            return self._send_file((LIB / p[len("/library/"):]).resolve())
        target = (WEB / p.lstrip("/")).resolve()
        if str(target).startswith(str(WEB.resolve())) or str(target).startswith(str(OUT.resolve())):
            return self._send_file(target)
        self.send_error(404)

    def do_POST(self):
        p = urlparse(self.path).path
        body = self._body()
        if p == "/api/rescan":
            return self._send_json(lib_mod.rebuild())
        if p == "/api/upload":
            return self._upload(body)
        if p == "/api/run":
            command = body.get("command")
            if command not in ALLOWED:
                return self._send_json({"error": f"command not allowed: {command}"}, 400)
            lib_mod.rebuild()  # scan before executing so new assets aren't missed
            args = body.get("args") or []
            out_file = None
            for i, a in enumerate(args):
                if a == "--out" and i + 1 < len(args):
                    out_file = args[i + 1]
            job = _new_job(_clemtock_argv(command, args), out_file)
            return self._send_json({"id": job["id"]})
        if p == "/api/build":
            lib_mod.rebuild()  # scan before planning + executing
            return self._build(body)
        self.send_error(404)

    def _upload(self, body: dict):
        """Accept up to 3 reference images (base64 data URLs) into assets/uploads/."""
        files = (body.get("files") or [])[:MAX_UPLOADS]
        up_dir = LIB / "uploads"
        up_dir.mkdir(parents=True, exist_ok=True)
        saved = []
        for i, f in enumerate(files):
            data = f.get("dataUrl", "")
            if "," in data:
                data = data.split(",", 1)[1]
            raw = base64.b64decode(data + "===")
            if len(raw) > 12 * 1024 * 1024:
                continue  # skip oversize
            stem = re.sub(r"[^A-Za-z0-9_-]", "-", Path(f.get("name", f"upload-{i}")).stem)[:48] or f"upload-{i}"
            ext = Path(f.get("name", "")).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".webp"):
                ext = ".png"
            dest = up_dir / f"{stem}{ext}"
            dest.write_bytes(raw)
            saved.append(dest.name)
        summary = lib_mod.rebuild()
        return self._send_json({"saved": saved, "library": summary})

    def _build(self, body: dict):
        """Recipe-driven: prep chosen library assets, augment the prompt, run `clemtock run`."""
        recipes = {r["id"]: r for r in json.loads((WEB / "recipes.json").read_text())["recipes"]}
        recipe = recipes.get(body.get("recipe"))
        if not recipe:
            return self._send_json({"error": "unknown recipe"}, 400)
        library = {a["id"]: a for a in json.loads((LIB / "library.json").read_text())["assets"]}

        # stage chosen hero/character images into web/assets so the renderer can resolve them
        staged = []
        for slot in ("hero", "character"):
            aid = body.get(slot)
            if aid and aid in library:
                src = LIB / library[aid]["file"]
                dst = WEB / "assets" / f"lib-{aid}.png"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                staged.append(f"{slot}: assets/{dst.name} ({library[aid]['name']})")

        # uploaded / picked reference images (up to 3)
        for aid in (body.get("references") or [])[:MAX_UPLOADS]:
            if aid in library:
                src = LIB / library[aid]["file"]
                dst = WEB / "assets" / f"lib-{aid}.png"
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
                staged.append(f"reference: assets/{dst.name} ({library[aid]['name']})")

        model = body.get("model")
        prompt = (body.get("prompt") or "").strip()
        aug = [recipe["brief_hint"], prompt]
        if staged:
            aug.append("Use these provided images as assets (source:upload): " + "; ".join(staged) + ".")
        if model and recipe["format"].get("avatar"):
            aug.append(f"Include a talking spokesperson (model='{model}') as an avatar scene.")
        full_prompt = "\n".join(x for x in aug if x)

        name = body.get("name") or f"{recipe['id']}"
        out_file = f"out/{name}.mp4"
        duration = body.get("duration") or recipe["format"]["duration"]
        args = ["--prompt", full_prompt, "--duration", str(duration),
                "--assets", str(WEB / "assets"), "--out", str(REPO / out_file)]
        job = _new_job(_clemtock_argv("run", args), out_file)
        return self._send_json({"id": job["id"], "prompt": full_prompt, "out": out_file})


def _scan_loop():
    while True:
        time.sleep(SCAN_EVERY)
        try:
            lib_mod.rebuild()
        except Exception as e:
            print(f"library scan failed: {e}")


def main(host: str = "0.0.0.0", port: int = 3053):
    vault_mod.apply_to_env()  # provider keys for jobs
    mimetypes.add_type("video/mp4", ".mp4")
    try:
        print(f"library scan at startup: {lib_mod.rebuild()}")
    except Exception as e:
        print(f"startup library scan failed: {e}")
    threading.Thread(target=_scan_loop, daemon=True).start()  # rescan every 15 min
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"clemtock server on http://{host}:{port}  (studio + /api · 15-min asset scan)")
    httpd.serve_forever()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=3053)
    a = ap.parse_args()
    main(a.host, a.port)
