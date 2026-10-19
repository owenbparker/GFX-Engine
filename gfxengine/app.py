"""The running engine: the workspace, what's on air, the data sources, and
the web server for the control panel and the outputs.

    /control              the control panel (Control, Composer, Assets, Data, Transitions, Outputs)
    /output               Program, 1920x1080, see-through (OBS / vMix browser source)
    /output?bus=preview   Preview
    /output?comp=<id>     one graphic as it is on Program (its own browser source)
"""

import json
import mimetypes
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse

from . import discover, export
from .assets import Assets
from .config import WEB_DIR, WORKSPACE_DIR, Settings, safe_join
from .data import Sources
from .live import Live
from .log import log, since
from .media import Jobs, ffmpeg_path, stinger_cut
from .project import Workspace, blank_comp, blank_layer, new_id
from .updater import Updater, clean_up_old_update

for ext, kind in ((".ttf", "font/ttf"), (".otf", "font/otf"), (".woff", "font/woff"), (".woff2", "font/woff2"),
                  (".svg", "image/svg+xml"), (".webm", "video/webm"), (".mp4", "video/mp4"), (".json", "application/json"),
                  (".webp", "image/webp"), (".mjs", "text/javascript"), (".js", "text/javascript")):
    mimetypes.add_type(kind, ext)

PAGES = {"/": "/control", "/control": "control.html", "/output": "output.html"}


def _is_local(ip):
    return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


class Engine:
    def __init__(self, settings=None, workspace_dir=WORKSPACE_DIR, starter=None):
        from .config import STARTER_DIR
        self.settings = settings or Settings()
        self.ws = Workspace(workspace_dir, STARTER_DIR if starter is None else starter)
        self.live = Live(self.ws)
        self.jobs = Jobs()
        self.assets = Assets(self.ws, self.jobs)
        self.sources = Sources(self.ws)
        self.updater = Updater()
        self.server = None
        self.assets_rev = 0
        self.version = 0
        self._cond = threading.Condition()
        for thing in (self.ws, self.live, self.sources, self.jobs):
            thing.listeners.append(self.changed)
        self.jobs.listeners.append(self._job_changed)
        self.beacon = discover.Beacon(self._beacon_info)

    def _beacon_info(self):
        s = self.settings.get()
        return {"name": self.name(), "port": s["http_port"], "network": s["allow_network"], "version": self.updater.current}

    def name(self):
        return self.settings.get().get("name") or socket.gethostname()

    def _job_changed(self):
        if any(j["status"] != "running" for j in self.jobs.list()):
            self.assets_rev += 1

    def changed(self):
        with self._cond:
            self.version += 1
            self._cond.notify_all()

    def wait(self, timeout):
        with self._cond:
            self._cond.wait(timeout)

    def state(self):
        """Everything the pages show (the outputs only use project, live and data)."""
        s = self.settings.get()
        return {
            "app": {"name": self.name(), "version": self.updater.current, "port": s["http_port"],
                    "network": s["allow_network"], "addresses": discover.own_addresses(),
                    "ffmpeg": bool(ffmpeg_path()), "platform": platform.system()},
            "rev": self.ws.rev, "assets_rev": self.assets_rev,
            "project": self.ws.get(), "live": self.live.get(), "data": self.sources.snapshot(),
            "fonts": self.assets.fonts(), "jobs": self.jobs.list(), "update": self.updater.info(),
        }

    def stop(self):
        self.sources.stop()
        self.beacon.stop()
        if self.server:
            self.server.stop()
        self.ws.close()

    # --- changes that touch several parts ----------------------------------

    def delete_comp(self, cid):
        self.ws.delete_comp(cid)
        self.live.forget(cid)

    def set_sources(self, sources):
        clean, names = [], set()
        for s in sources:
            s = {k: v for k, v in s.items() if k in ("id", "name", "type", "url", "path", "sheet", "refresh")}
            s.setdefault("id", new_id("s"))
            s["name"] = re.sub(r"[!{}#|]", "", str(s.get("name") or "Data")).strip() or "Data"
            base, n = s["name"], 2
            while s["name"].lower() in names:
                s["name"], n = f"{base} {n}", n + 1
            names.add(s["name"].lower())
            if s.get("type") not in ("gsheet", "file", "url"):
                raise ValueError("A data source is a Google Sheet, a file or a web address")
            s["refresh"] = max(1, min(3600, float(s.get("refresh") or 5)))
            clean.append(s)
        gone = {s["id"] for s in self.ws.get()["sources"]} - {s["id"] for s in clean}
        self.ws.set_sources(clean)
        for sid in gone:
            self.sources.forget(sid)
        threading.Thread(target=self.sources.refresh, daemon=True).start()

    def add_sources(self, new):
        if new:
            self.set_sources(self.ws.get()["sources"] + new)

    def upload(self, name, rfile, length, fps=None):
        name = os.path.basename(name.replace("\\", "/"))
        if not name:
            raise ValueError("No file name")
        tmp_dir = os.path.join(self.ws.folder, ".uploads")
        os.makedirs(tmp_dir, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=tmp_dir, suffix=os.path.splitext(name)[1])
        with os.fdopen(fd, "wb") as f:
            left = length
            while left > 0:
                chunk = rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left > 0:
            os.remove(tmp)
            raise ValueError("The upload was cut short")
        result = self.assets.add(name, tmp, fps=fps)
        self.add_sources(result.get("sources"))
        self.assets_rev += 1
        self.changed()
        log(f"Added {name}")
        return result

    def stinger_cut(self, src):
        path = self.ws.asset_path(src)
        if not path or not os.path.isfile(path):
            raise ValueError("No such video")
        return stinger_cut(path)


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def parse_range(header, size):
    m = re.match(r"bytes=(\d*)-(\d*)$", header or "")
    if not m or (not m.group(1) and not m.group(2)):
        return None
    if m.group(1):
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
    else:
        start, end = max(0, size - int(m.group(2))), size - 1
    if start >= size or start > end:
        return None
    return start, min(end, size - 1)


def make_handler(engine):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _allowed(self):
            return _is_local(self.client_address[0]) or engine.settings.get()["allow_network"]

        def _send(self, body, ctype="application/json", status=200, headers=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, data, status=200):
            self._send(json.dumps(data), status=status)

        def _file(self, path, cache=False):
            size = os.path.getsize(path)
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            span = parse_range(self.headers.get("Range"), size)
            start, end = span if span else (0, size - 1)
            self.send_response(206 if span else 200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if span:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            if self.command == "HEAD":
                return
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = f.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def _stream(self):
            """Server-sent events: the whole state whenever it changes (at most 30 a second)."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            last, sent = None, 0.0
            try:
                self.wfile.write(b"retry: 1000\n\n")
                while True:
                    engine.wait(1.0)
                    now = time.monotonic()
                    if engine.version == last:
                        if now - sent > 10:   # keep the connection alive
                            self.wfile.write(b": ping\n\n")
                            self.wfile.flush()
                            sent = now
                        continue
                    if now - sent < 1 / 30:
                        time.sleep(1 / 30 - (now - sent))
                    last, sent = engine.version, time.monotonic()
                    self.wfile.write(b"data: " + json.dumps(engine.state()).encode() + b"\n\n")
                    self.wfile.flush()
            except (ConnectionError, OSError):
                pass

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Filename")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            if not self._allowed():
                return self._json({"error": "This engine doesn't allow other PCs (Outputs > Network)"}, 403)
            url = urlparse(self.path)
            path, q = url.path, parse_qs(url.query)
            if path in PAGES:
                target = PAGES[path]
                if target.startswith("/"):
                    self.send_response(302)
                    self.send_header("Location", target)
                    self.send_header("Content-Length", "0")
                    return self.end_headers()
                path = "/" + target
            if path == "/api/hello":
                return self._json({"app": discover.APP, "name": engine.name(), "version": engine.updater.current,
                                   "port": engine.settings.get()["http_port"]})
            if path == "/api/state":
                return self._json(engine.state())
            if path == "/api/stream":
                return self._stream()
            if path == "/api/assets":
                return self._json({"assets": engine.assets.list(), "rev": engine.assets_rev})
            if path == "/api/log":
                return self._json({"lines": since(int((q.get("after") or ["0"])[0]))})
            if path == "/api/engines":
                return self._json({"engines": engine.beacon.engines()})
            if path == "/api/scan":
                port = engine.settings.get()["http_port"]
                found = discover.scan(port)
                for e in found:
                    engine.beacon.add(e["ip"], e["port"], e.get("name", e["ip"]), e.get("version", ""))
                return self._json({"engines": engine.beacon.engines()})
            if path.startswith("/api/source/"):
                return self._json(engine.sources.table(path.rsplit("/", 1)[1]))
            if path == "/api/stinger-cut":
                return self._json({"cut": engine.stinger_cut((q.get("src") or [""])[0])})
            if path == "/api/export":
                ids = [i for i in (q.get("comps") or [""])[0].split(",") if i]
                bus = (q.get("bus") or ["preview"])[0]
                values = engine.live.get().get(bus, {}).get("values", {})
                blob = export.build(engine.ws, engine.assets, ids, values, engine.sources.snapshot()["tables"])
                name = re.sub(r"[^\w\- ]+", "", (q.get("name") or [engine.ws.get()["name"]])[0]).strip() or "graphics"
                return self._send(blob, "application/zip", headers={
                    "Content-Disposition": f"attachment; filename=\"{name}.zip\"; filename*=UTF-8''{quote(name)}.zip"})
            if path == "/api/backup":
                engine.ws.save()
                tmp = tempfile.mkdtemp()
                try:
                    zip_path = shutil.make_archive(os.path.join(tmp, "workspace"), "zip", engine.ws.folder)
                    with open(zip_path, "rb") as f:
                        blob = f.read()
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
                return self._send(blob, "application/zip", headers={
                    "Content-Disposition": f"attachment; filename=\"GFX workspace {time.strftime('%Y-%m-%d')}.zip\""})
            if path.startswith("/assets/"):
                full = engine.ws.asset_path(unquote(path[1:]))
                if not full or not os.path.isfile(full):
                    return self._json({"error": "not found"}, 404)
                return self._file(full)
            full = safe_join(WEB_DIR, unquote(path))
            if not full:
                return self._json({"error": "not found"}, 404)
            return self._file(full, cache="/vendor/" in path or "/fonts/" in path)

        def do_POST(self):
            if not self._allowed():
                return self._json({"error": "This engine doesn't allow other PCs (Outputs > Network)"}, 403)
            path = urlparse(self.path).path
            q = parse_qs(urlparse(self.path).query)
            local = _is_local(self.client_address[0])
            try:
                length = int(self.headers.get("Content-Length") or 0)
                if path == "/api/upload":
                    name = unquote(self.headers.get("X-Filename") or (q.get("name") or [""])[0])
                    fps = float((q.get("fps") or ["0"])[0]) or None
                    return self._json(engine.upload(name, self.rfile, length, fps))
                body = json.loads(self.rfile.read(length) or b"{}")
                result = {"ok": True}
                ws, live = engine.ws, engine.live
                # --- graphics ---
                if path == "/api/comp/new":
                    comp = body.get("comp") or blank_comp(body.get("name") or "New graphic")
                    result = {"comp": ws.add_comp(comp, after=body.get("after"))}
                elif path == "/api/comp/save":
                    result = {"comp": ws.put_comp(body["comp"])}
                elif path == "/api/comp/duplicate":
                    result = {"comp": ws.duplicate_comp(body["id"])}
                elif path == "/api/comp/delete":
                    engine.delete_comp(body["id"])
                elif path == "/api/comp/order":
                    ws.order_comps(body["ids"])
                elif path == "/api/layer/blank":
                    result = {"layer": blank_layer(body.get("type", "text"))}
                elif path == "/api/project":
                    ws.rename(body.get("name", ""))
                # --- on air ---
                elif path == "/api/cue":
                    live.cue(body["id"], bool(body.get("on", True)))
                elif path == "/api/values":
                    live.set_values(body["id"], body.get("values") or {}, body.get("bus", "preview"))
                elif path == "/api/send":
                    live.send_values(body["id"])
                elif path == "/api/take":
                    result = {"transition": live.take(body.get("transition"))}
                elif path == "/api/program":
                    live.program(body["id"], bool(body.get("on")), body.get("transition") or "animate")
                elif path == "/api/clear":
                    live.clear(body.get("bus", "program"), body.get("transition") or "animate")
                # --- transitions, data ---
                elif path == "/api/transitions":
                    ws.set_transitions(body["transitions"], body.get("default"))
                elif path == "/api/sources":
                    engine.set_sources(body["sources"])
                elif path == "/api/source/refresh":
                    engine.sources.refresh(body.get("id"))
                # --- files ---
                elif path == "/api/asset/delete":
                    ws.delete_asset(body["path"])
                    engine.assets_rev += 1
                    engine.changed()
                elif path == "/api/open":
                    if not local:
                        raise ValueError("Folders can only be opened on the engine's own PC")
                    open_folder(ws.assets_dir if body.get("what") == "assets" else ws.folder)
                # --- the app ---
                elif path == "/api/settings":
                    if not local:
                        raise ValueError("Settings can only be changed on the engine's own PC")
                    engine.settings.update(body)
                    engine.changed()
                elif path == "/api/update/check":
                    engine.updater.check()
                    engine.changed()
                elif path == "/api/update/install":
                    if not local:
                        raise ValueError("Updates can only be installed on the engine's own PC")
                    engine.updater.install_in_background()
                else:
                    return self._json({"error": "not found"}, 404)
                self._json(result)
            except KeyError as e:
                self._json({"error": f"Missing or unknown: {e}"}, 400)
            except (ValueError, TypeError, OSError) as e:
                self._json({"error": str(e)}, 400)

    return Handler


class Server:
    def __init__(self, engine, port):
        self.port = port
        # Always on every network card: other PCs are turned away unless allowed,
        # so allowing them needs no restart.
        self.httpd = ThreadingHTTPServer(("0.0.0.0", port), make_handler(engine))
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def start(engine):
    """Starts the web server (raises OSError if the port is taken)."""
    port = engine.settings.get()["http_port"]
    engine.server = Server(engine, port)
    clean_up_old_update()
    engine.updater.check_in_background()
    threading.Thread(target=engine.sources.refresh, daemon=True).start()
    log(f"GFX Engine {engine.updater.current} running - control panel http://localhost:{port}/control")
    log(f"Program output (browser source, 1920x1080): http://localhost:{port}/output")
    return engine.server
