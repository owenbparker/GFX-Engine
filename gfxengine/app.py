"""The running engine: the workspace, what's on air, the data sources, and
the web server for the control panel and the outputs.

    /control              the control panel (Control, Composer, Assets, Data, Transitions, Outputs)
    /output               Program, 1920x1080, see-through (OBS / vMix browser source)
    /output?bus=preview   Preview
    /output?comp=<id>     one graphic as it is on Program (its own browser source)

Game HUDs connect to it: they POST /api/ingest (their stats and the series
score) and GET /api/global (the teams' names, short names and logos).
Bitfocus Companion uses /api/companion (see companion.py).
"""

import copy
import ipaddress
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

from . import companion, discover, export, globalcfg, pack
from .assets import Assets
from .config import WEB_DIR, Settings, safe_join
from .data import Sources
from .live import Live
from .log import log, since
from .media import Jobs, ffmpeg_path, stinger_cut
from .project import Workspace, blank_comp, blank_layer, new_id
from .stats import GAMES, Stats, read as read_stats, rows as stats_rows
from .teams import Teams, ign_key, player_named, roster_rows
from . import schedule, standings, tournament
from .updater import Updater, clean_up_old_update
from .workspaces import Workspaces

for ext, kind in ((".ttf", "font/ttf"), (".otf", "font/otf"), (".woff", "font/woff"), (".woff2", "font/woff2"),
                  (".svg", "image/svg+xml"), (".webm", "video/webm"), (".mp4", "video/mp4"), (".json", "application/json"),
                  (".webp", "image/webp"), (".mjs", "text/javascript"), (".js", "text/javascript")):
    mimetypes.add_type(kind, ext)

PAGES = {"/": "/control", "/control": "control.html", "/output": "output.html"}


def _is_local(ip):
    return ip in ("127.0.0.1", "::1", "::ffff:127.0.0.1")


class Engine:
    def __init__(self, settings=None, workspaces_dir=None, starter=None, library_dir=None, legacy_dir=None):
        from . import config
        self.settings = settings or Settings()
        self.workspaces = Workspaces(workspaces_dir or config.WORKSPACES_DIR,
                                     config.STARTER_DIR if starter is None else starter,
                                     legacy=config.LEGACY_WORKSPACE_DIR if legacy_dir is None else legacy_dir)
        self.library_dir = library_dir or config.LIBRARY_DIR
        self.teams = Teams(self.library_dir)
        self.jobs = Jobs()
        self.updater = Updater()
        self.server = None
        self.assets_rev = 0
        self.version = 0
        # Data sent by game HUDs ("League HUD" -> its fields), kept while the engine runs.
        self.feeds = {}
        self.feeds_rev = 0
        self.ws = self.live = self.assets = self.sources = self.stats = None
        self._cond = threading.Condition()
        self._parts_lock = threading.Lock()
        self._parts = None      # (version, made at, {key: JSON}): the state, made once for every output
        self._fonts_cache = (None, 0, [])
        self._ffmpeg_cache = (0, False)
        threading.Thread(target=self._trim_photos, daemon=True).start()
        self._open_lock = threading.Lock()
        self.jobs.listeners.append(self.changed)
        self.jobs.listeners.append(self._job_changed)
        wid = self.settings.get().get("workspace")
        if not self.workspaces.path(wid):
            listed = self.workspaces.list()
            wid = listed[0]["id"] if listed else self.workspaces.create("SCC Broadcast", "scc")
        self.open(wid)
        self.beacon = discover.Beacon(self._beacon_info)
        threading.Thread(target=self._watch_stats, daemon=True).start()

    def _watch_stats(self):
        """The stats go from LIVE to FINAL when the HUD stops sending: tell the pages."""
        was = None
        while True:
            time.sleep(2)
            now = self.stats.live() if self.stats else False
            if was is not None and now != was:
                self.feeds_rev += 1
                self.changed()
            was = now

    def open(self, wid):
        """Opens a workspace: its graphics go on the control panel and the outputs."""
        folder = self.workspaces.path(wid)
        if not folder:
            raise KeyError("No such workspace")
        with self._open_lock:
            old = (self.ws, self.sources)
            ws = Workspace(folder, starter=None)
            updated = pack.upgrade(ws, self.workspaces.starter)
            live = Live(ws)
            assets = Assets(ws, self.jobs, self.library_dir)
            sources = Sources(ws)
            for thing in (ws, live, sources):
                thing.listeners.append(self.changed)
            self.ws, self.live, self.assets, self.sources = ws, live, assets, sources
            self.stats = Stats(folder)
            if old[1]:
                old[1].stop()
            if old[0]:
                old[0].close()
            if self.settings.get().get("workspace") != wid:
                self.settings.update({"workspace": wid})
            self.workspace_id = wid
        self.assets_rev += 1
        threading.Thread(target=sources.refresh, daemon=True).start()
        log(f"Opened the workspace {ws.get()['name']}")
        if updated:
            log(f"Updated the SCC graphics: {', '.join(updated)}")
        self.changed()

    def _beacon_info(self):
        s = self.settings.get()
        return {"name": self.name(), "port": s["http_port"], "network": s["allow_network"], "version": self.updater.current,
                "address": s.get("network_address") or ""}

    def name(self):
        return self.settings.get().get("name") or socket.gethostname()

    def _job_changed(self):
        if any(j["status"] != "running" for j in self.jobs.list()):
            self.assets_rev += 1

    def changed(self):
        with self._cond:
            self.version += 1
            self._cond.notify_all()

    def wait(self, timeout, version=None):
        """Waits for a change (or, given the version last seen, returns at once if it's already changed)."""
        with self._cond:
            if version is None or self.version == version:
                self._cond.wait(timeout)

    def global_config(self):
        return globalcfg.clean(copy.deepcopy(self.ws.snapshot().get("global")))

    def data_snapshot(self):
        """The tables graphics read: the data sources, "Global", and what game HUDs send."""
        snap = self.sources.snapshot()
        g = self.global_config()
        snap["tables"]["Global"] = globalcfg.rows(g)
        snap["tables"]["Sponsors"] = globalcfg.sponsor_rows(g)
        try:
            snap["tables"]["Stats"] = self.stats.rows(
                {side: g[side]["name"] for side in ("left", "right")}, g["player_stats"],
                lambda side, name: player_named(self.teams.find(g[side]["name"], g[side]["game"]), name), g["pictures"])
        except Exception as e:   # (the game's stats can't take the whole engine down)
            if not getattr(self, "_stats_failed", False):
                log(f"Couldn't read the game's stats: {e!r}")
            self._stats_failed = True
            snap["tables"]["Stats"] = stats_rows(None, False)
        snap["tables"]["Tournament"] = tournament.rows(g["tournament"], self.teams.find)
        snap["tables"]["Teams"] = self.teams.rows()
        snap["tables"]["Schedule"] = schedule.rows(g["schedule"], self.teams.find)
        snap["tables"]["Standings"] = standings.rows(g["standings"], self.teams.find, g["event"])
        side = g["roster"]
        stats_names = dict(r[:2] for r in snap["tables"]["Stats"][1:] if len(r) >= 2)
        snap["tables"]["Roster"] = roster_rows(self.teams.find(g[side]["name"], g[side]["game"]), side,
                                               [stats_names.get(f"{side.title()} player {i}", "") for i in range(1, 6)])
        for name, feed in self.feeds.items():
            snap["tables"][name] = feed["rows"]
        snap["tables"]["HUDs"] = self.hud_rows()
        snap["rev"] = f"{snap['rev']}.{self.ws.rev}.{self.feeds_rev}.{int(self.stats.live())}.{self.teams.rev}"
        snap["now"] = time.time()   # (the outputs line their clocks up with it: the sponsors change together)
        snap["stats"] = {"live": self.stats.live(), "kept": bool(self.stats.data),
                         "from": (self.stats.data or {}).get("source", ""), "at": (self.stats.data or {}).get("at", 0)}
        snap["feeds"] = {name: {"from": f["from"], "game": f["game"], "age": round(time.time() - f["at"], 1),
                                # (a HUD on another PC must let other PCs read it for its pages to show here)
                                "unreachable": bool(f.get("hud") and f["hud"]["remote"] and not f["hud"]["network"])}
                         for name, f in self.feeds.items()}
        return snap

    def state(self):
        """Everything the pages show (the outputs only use project, live and data)."""
        s = self.settings.get()
        project = self.ws.snapshot()
        return {
            "app": {"name": self.name(), "version": self.updater.current, "port": s["http_port"],
                    "network": s["allow_network"],
                    # (where other PCs reach it: the one network chosen, or every one)
                    "addresses": [s["network_address"]] if s.get("network_address") else discover.own_addresses(),
                    "all_addresses": discover.own_addresses(), "network_address": s.get("network_address") or "",
                    "ffmpeg": self._has_ffmpeg(), "platform": platform.system()},
            "workspace": {"id": self.workspace_id, "name": project.get("name", ""),
                          "picture": bool(project.get("picture"))},
            "rev": self.ws.rev, "assets_rev": self.assets_rev,
            "project": project, "live": self.live.get(), "data": self.data_snapshot(),
            "global": globalcfg.clean(project.get("global")),
            "teams": self.teams.list(),
            "games": list(GAMES.values()),   # (the games there are HUDs for)
            "camera_looks": s.get("camera_looks") or [],
            "fonts": self._fonts(), "jobs": self.jobs.list(), "update": self.updater.info(),
        }

    def _fonts(self):
        key = (id(self.ws), self.assets_rev)
        if self._fonts_cache[0] != key or time.monotonic() - self._fonts_cache[1] > 5:
            self._fonts_cache = (key, time.monotonic(), self.assets.fonts())
        return self._fonts_cache[2]

    def _has_ffmpeg(self):
        if time.monotonic() - self._ffmpeg_cache[0] > 30:
            self._ffmpeg_cache = (time.monotonic(), bool(ffmpeg_path()))
        return self._ffmpeg_cache[1]

    def state_parts(self):
        """The state as {key: JSON text}, made once per change however many
        pages follow it (the outputs, the monitors, the control panel); the
        data's "now" is left out (state_json puts it back)."""
        with self._parts_lock:
            version = self.version
            p = self._parts
            if not p or p[0] != version or time.monotonic() - p[1] > 1:
                state = self.state()
                data = dict(state["data"])
                data.pop("now", None)
                state["data"] = data
                p = self._parts = (version, time.monotonic(), {k: json.dumps(v) for k, v in state.items()})
            return p[2]

    def state_json(self, parts=None, keys=None):
        """The state (or just `keys` of it) as JSON text."""
        parts = parts or self.state_parts()
        out = []
        for k in (parts if keys is None else keys):
            v = parts[k]
            if k == "data":
                v = v[:-1] + ',"now":%r}' % time.time()
            out.append(json.dumps(k) + ":" + v)
        return "{" + ",".join(out) + "}"

    def stop(self):
        self.sources.stop()
        self.beacon.stop()
        if self.server:
            self.server.stop()
        self.ws.close()

    # --- global configuration, and the game HUDs ----------------------------

    def set_global(self, changes):
        old = self.global_config()
        g = json.loads(json.dumps(old))
        for k, v in (changes or {}).items():
            if k == "pictures" and isinstance(v, dict) and not ({"left", "right"} & set(v)):
                for page, sides in v.items():   # ({"team": {"left": "champion"}}: just that one)
                    if isinstance(sides, dict):
                        g[k].setdefault(page, {}).update(sides)
            elif k in ("left", "right", "bgloop", "caster", "pictures") and isinstance(v, dict):
                g[k].update(v)
            else:
                g[k] = v
        g = globalcfg.sponsors_changed(old, globalcfg.clean(g))
        self.ws.set_global(g)
        return g

    def timer(self, action, secs=None, down=None):
        """Starts, stops, resets or sets the timer ({{timer}}); secs can be "m:ss"."""
        if secs is not None and secs != "":
            secs = globalcfg.parse_secs(secs)
        else:
            secs = None
        t = globalcfg.timer_action(self.global_config()["timer"], action, secs, down)
        return self.set_global({"timer": t})

    def save_global_logo(self, side, filename, blob):
        """A picture for Global: a team's logo ("left", "right"), the tournament's
        logo ("tournament"), one more sponsor ("sponsor") or the background loop
        ("bgloop", a video)."""
        if side not in ("left", "right", "tournament", "sponsor", "bgloop"):
            raise ValueError("left, right, tournament, sponsor or bgloop")
        ext = os.path.splitext(filename or "")[1].lower()
        if side == "bgloop":
            if ext not in (".mp4", ".webm", ".mov", ".m4v"):
                raise ValueError("The loop must be an MP4, WEBM or MOV video")
        elif ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
            raise ValueError("The logo must be a PNG, JPG, WEBP, SVG or GIF")
        base = re.sub(r"[^\w\- ]+", "_", os.path.splitext(os.path.basename(filename))[0]) or side
        rel, path = self.ws.unique_asset(base + ext, {"sponsor": "sponsors", "bgloop": "loops"}.get(side, "logos"))
        with open(path, "wb") as f:
            f.write(blob)
        self.assets_rev += 1
        if side == "tournament":
            return self.set_global({"tournament_logo": rel})
        if side == "sponsor":
            g = self.global_config()
            secs = g["sponsors"][-1]["secs"] if g["sponsors"] else 10
            return self.set_global({"sponsors": g["sponsors"] + [{"logo": rel, "secs": secs}]})
        if side == "bgloop":
            return self.set_global({"bgloop": {"src": rel, "on": True}})
        return self.set_global({side: {"logo": rel}})

    def save_teams(self, teams):
        out = self.teams.save(teams)
        self.changed()
        return out

    def import_teams(self, text):
        n = self.teams.import_csv(text)
        self.assets_rev += 1
        self.changed()
        return n

    def roster_links(self, game=None, fields=None):
        """For a HUD's "Save IGN to player": each side's team (from Global), its
        roster, and the game's players, each with the roster player it's linked
        to by in-game ID (or None). The players are the HUD's own fields when it
        sends them, else the last stats the engine got."""
        g = self.global_config()
        st = read_stats(game, fields) if fields else self.stats.data
        out = {}
        for side in ("left", "right"):
            team = self.teams.find(g[side]["name"], g[side]["game"])
            members = (team or {}).get("players") or []
            keys = [ign_key(m["ign"]) for m in members]
            players = []
            for p in ((st or {}).get(side) or {}).get("players") or []:
                if p["name"]:
                    k = ign_key(p["name"])
                    players.append({"ign": p["name"], "linked": keys.index(k) if k in keys else None})
            out[side] = {"team": (team or {}).get("name") or g[side]["name"], "found": bool(team),
                         "members": [{"index": i, "name": m["name"], "ign": m["ign"]} for i, m in enumerate(members)],
                         "players": players}
        return {"sides": out}

    def link_player(self, side, index, ign):
        """Saves a game's in-game name to a roster player of a side's team."""
        g = self.global_config()
        if side not in ("left", "right"):
            raise ValueError("Unknown side")
        team = self.teams.link(g[side]["name"], g[side]["game"], int(index), ign)
        self.changed()
        return team

    def _trim_photos(self):
        """Headshots kept before they were trimmed on upload: trimmed now."""
        n = self.teams.trim_photos()
        if n:
            log(f"Trimmed the empty space around {n} headshot(s), so they line up on the player graphics")
            self.assets_rev += 1
            self.changed()

    def save_team_photo(self, name, filename, blob):
        photo = self.teams.save_photo(name, filename, blob)
        self.assets_rev += 1
        return photo

    def save_team_logo(self, name, filename, blob, game=""):
        logo = self.teams.save_logo(name, filename, blob, game)
        self.assets_rev += 1
        self.changed()
        return logo

    def ingest(self, body, client):
        """A game HUD's data: its fields (a table named after the HUD) and the
        series score (into Global)."""
        name = re.sub(r"[!{}#|]", "", str(body.get("source") or "Game")).strip()[:40] or "Game"
        fields = body.get("fields") or {}
        if not isinstance(fields, dict):
            raise ValueError("fields must be an object")
        rows = [["Field", "Value"]] + [[str(k)[:80], "" if v is None else str(v)[:500]] for k, v in fields.items()]
        old = self.feeds.get(name)
        was_live = self.stats.live()
        self.feeds[name] = {"rows": rows, "from": client, "game": str(body.get("game") or ""), "at": time.time(),
                            "hud": self._hud_pages(name, body.get("hud"), client)}
        if self.feeds[name]["hud"] != (old or {}).get("hud"):
            self.feeds_rev += 1
            self._add_hud_graphics(name, self.feeds[name]["hud"])
        if not old or old["rows"] != rows:
            self.feeds_rev += 1
            if not old:
                log(f"{name} connected from {client}")
        if self.stats.update(name, str(body.get("game") or ""), fields) or was_live != self.stats.live():
            self.feeds_rev += 1
        # The series into Global: a value the HUD changed (or its first, for the
        # score, unless 0), and names only where Global has none - so connecting a HUD
        # doesn't undo what was set here.
        series = body.get("series") or {}
        prev = (old or {}).get("series") or {}
        self.feeds[name]["series"] = series
        if series:
            g = self.global_config()
            changes = {}
            for side in ("left", "right"):
                team, before = series.get(side) or {}, prev.get(side) or {}
                for key in ("score", "name", "short", "color"):
                    if team.get(key) in (None, ""):
                        continue
                    value = int(team[key]) if key == "score" else str(team[key])
                    first = key not in before
                    moved = not first and before.get(key) != team[key]
                    blank = key != "score" and not g[side][key]
                    first_score = first and key == "score" and value > 0   # (a HUD at 0-0 keeps the score set here)
                    if (moved or blank or first_score) and value != g[side][key]:
                        changes.setdefault(side, {})[key] = value
            bo = series.get("best_of")
            if bo and int(bo) != g["best_of"] and ("best_of" not in prev or prev.get("best_of") != bo):
                changes["best_of"] = int(bo)
            if changes:
                self.set_global(changes)
        self.changed()

    # --- a game HUD's own graphics (VALORANT's agent select...) -------------------

    def _hud_pages(self, name, hud, client):
        """What a HUD says it can show ({"port", "network", "graphics": [{"id",
        "name", "path", "kind"}]}) -> its pages' addresses, as outputs reach them:
        a HUD on this PC at localhost, one on another PC at its address."""
        if not isinstance(hud, dict) or not hud.get("port"):
            return None
        host = "localhost" if _is_local(client) else client
        pages = []
        for g in hud.get("graphics") or []:
            if isinstance(g, dict) and g.get("id") and g.get("path"):
                pages.append({"id": re.sub(r"[^\w-]", "", str(g["id"]))[:30], "name": str(g.get("name") or g["id"])[:40],
                              "kind": g.get("kind") if g.get("kind") in ("board", "lower third", "overlay") else "overlay",
                              "url": f"http://{host}:{int(hud['port'])}/{str(g['path']).lstrip('/')}",
                              "backdrop": bool(g.get("backdrop"))})
        return {"pages": pages, "remote": not _is_local(client), "network": bool(hud.get("network"))}

    def _add_hud_graphics(self, name, hud):
        """Adds a graphic for each of a HUD's pages the first time the HUD
        offers it (deleting one keeps it gone)."""
        if not hud:
            return
        with self.ws.lock:
            added = self.ws.data.setdefault("hud_graphics", [])
            for p in hud["pages"]:
                key = f"{name}/{p['id']}"
                if key in added:
                    # (one added before the HUD asked for the boards' backdrop: given it now)
                    comp = next((c for c in self.ws.data["compositions"] if c.get("hud") == key), None)
                    if comp and p.get("backdrop") and not any(l.get("name") == "Background loop" for l in comp["layers"]):
                        comp["layers"][0:0] = self._board_backdrop()
                        self.ws.changed()
                    continue
                added.append(key)
                comp = blank_comp(f"{p['name']} ({name})")
                comp.update(kind=p["kind"], hud=key)
                comp["layers"] = (self._board_backdrop() if p.get("backdrop") else []) + [
                    blank_layer("web", name=p["name"], x=0, y=0, w=1920, h=1080, src=f"{{{{HUDs!{name} {p['name']}}}}}")]
                self.ws.add_comp(comp)
                log(f"Added the {name}'s {p['name']} to the graphics")

    def _board_backdrop(self):
        """The boards' backdrop and background loop (as on Team stats), for a
        HUD's full-screen page that goes over them (VALORANT's map bans)."""
        out = []
        for cname in ("Team stats", "Player stats", "Schedule"):
            comp = next((c for c in self.ws.data["compositions"] if c["name"] == cname), None)
            layers = {l.get("name"): l for l in (comp or {}).get("layers") or []}
            if "Background loop" in layers:
                out = [layers[n] for n in ("Layer 1", "Background loop") if n in layers]
                break
        out = [dict(copy.deepcopy(l), id=new_id("l")) for l in out]
        if not any(l["name"] == "Background loop" for l in out):
            out.append(blank_layer("video", name="Background loop", x=0, y=0, w=1920, h=1080, blend="screen", fit="cover",
                                   audio=False, src="{{Global!BG loop}}", tint="{{Global!BG loop colour}}",
                                   brightness="{{Global!BG loop brightness}}", speed="{{Global!BG loop speed}}"))
        return out

    def hud_rows(self):
        """The "HUDs" data table: each connected HUD's pages' addresses."""
        out = [["Field", "Value"]]
        for name, f in self.feeds.items():
            for p in (f.get("hud") or {}).get("pages") or []:
                out.append([f"{name} {p['name']}", p["url"]])
        return out

    # --- workspaces ------------------------------------------------------

    def workspaces_info(self):
        return {"workspaces": self.workspaces.list(), "current": self.workspace_id}

    def create_workspace(self, name, template="scc", open_it=True):
        wid = self.workspaces.create(name, template)
        if open_it:
            self.open(wid)
        return wid

    def rename_workspace(self, wid, name):
        if wid == self.workspace_id:
            self.ws.rename(name)
        else:
            self.workspaces.rename(wid, name)
        self.changed()

    def set_workspace_picture(self, wid, filename, blob):
        pic = self.workspaces.set_picture(wid, filename, blob)
        if wid == self.workspace_id:
            self.ws.set_picture(pic)
        else:
            self.workspaces.set_field(wid, "picture", pic)
        self.changed()
        return pic

    def delete_workspace(self, wid):
        if wid == self.workspace_id:
            raise ValueError("Open another workspace before deleting this one")
        self.workspaces.delete(wid)
        self.changed()

    def pack(self):
        """The SCC graphics that come with the engine, and which this workspace has."""
        have = {c["name"] for c in self.ws.get()["compositions"]}
        return [{"id": c["id"], "name": c["name"], "have": c["name"] in have,
                 "w": c.get("width", 1920), "h": c.get("height", 1080)}
                for c in self.workspaces.starter_project().get("compositions", [])]

    def import_pack(self, ids=None):
        """Copies graphics from the SCC pack (all this workspace doesn't have, or ids) with their files."""
        starter = self.workspaces.starter
        project = self.workspaces.starter_project()
        have = {c["name"] for c in self.ws.get()["compositions"]}
        comps = [c for c in project.get("compositions", [])
                 if (c["id"] in ids if ids else c["name"] not in have)]
        for comp in comps:
            used = set()
            export._walk_assets(comp, used)
            for rel in used:
                src = os.path.join(starter, rel)
                dest = self.ws.asset_path(rel)
                if dest and os.path.isfile(src) and not os.path.exists(dest):
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(src, dest)
            comp = json.loads(json.dumps(comp))
            comp["id"] = new_id("c")
            self.ws.add_comp(comp)
        if comps:
            self.assets_rev += 1
            log(f"Added {len(comps)} graphic(s) from the SCC pack")
        self.changed()
        return [c["name"] for c in comps]

    # --- changes that touch several parts ----------------------------------

    def clear_stats(self):
        self.stats.clear()
        self.feeds_rev += 1
        self.changed()

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

    def upload(self, name, rfile, length, fps=None, graphic=False):
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
        result = self.assets.add(name, tmp, fps=fps, graphic=graphic)
        self.add_sources(result.get("sources"))
        self.assets_rev += 1
        self.changed()
        log(f"Added {name}")
        return result

    def stinger_cut(self, src):
        path = self.assets.path_of(src)
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
            last, sent, had = None, 0.0, {}
            try:
                self.wfile.write(b"retry: 1000\n\n")
                while True:
                    if last is not None:
                        engine.wait(1.0, last)
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
                    # Only what changed since the last message (a take is a few hundred
                    # bytes, not the whole project): the pages keep the rest.
                    parts = engine.state_parts()
                    keys = [k for k, v in parts.items() if had.get(k) != v]
                    had = dict(parts)
                    self.wfile.write(b"data: " + engine.state_json(parts, keys).encode() + b"\n\n")
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
                return self._send(engine.state_json())
            if path == "/api/stream":
                return self._stream()
            if path == "/api/companion":
                return self._json(companion.state(engine))
            if path == "/api/assets":
                return self._json({"assets": engine.assets.list(), "rev": engine.assets_rev})
            if path == "/api/log":
                return self._json({"lines": since(int((q.get("after") or ["0"])[0]))})
            if path == "/api/engines":
                return self._json({"engines": engine.beacon.engines()})
            if path == "/api/scan":
                port = engine.settings.get()["http_port"]
                found = discover.scan(port, only=engine.settings.get().get("network_address") or "")
                for e in found:
                    engine.beacon.add(e["ip"], e["port"], e.get("name", e["ip"]), e.get("version", ""))
                return self._json({"engines": engine.beacon.engines()})
            if path == "/api/workspaces":
                return self._json(engine.workspaces_info())
            if path.startswith("/api/workspace-picture/"):
                full = engine.workspaces.picture(unquote(path.rsplit("/", 1)[1]))
                return self._file(full) if full else self._json({"error": "not found"}, 404)
            if path == "/api/roster/links":
                return self._json(engine.roster_links())
            if path == "/api/global":
                # For game HUDs ("Use Global Information"): logos as addresses on this engine.
                g = engine.global_config()
                host = self.headers.get("Host") or f"localhost:{engine.settings.get()['http_port']}"
                for side in ("left", "right"):
                    logo = g[side]["logo"]
                    g[side]["logo_url"] = (f"http://{host}/{quote(logo)}" if logo and not re.match(r"https?://", logo)
                                           else logo)
                logo = g["tournament_logo"]
                g["tournament_logo_url"] = (f"http://{host}/{quote(logo)}" if logo and not re.match(r"https?://", logo)
                                            else logo)
                for sp in g["sponsors"]:
                    sp["logo_url"] = sp["logo"] if re.match(r"https?://", sp["logo"]) else f"http://{host}/{quote(sp['logo'])}"
                return self._json({"global": g, "workspace": engine.ws.get()["name"], "engine": engine.name()})
            if path == "/api/pack":
                return self._json({"graphics": engine.pack()})
            if path.startswith("/api/source/"):
                return self._json(engine.sources.table(path.rsplit("/", 1)[1]))
            if path == "/api/stinger-cut":
                return self._json({"cut": engine.stinger_cut((q.get("src") or [""])[0])})
            if path == "/api/export":
                ids = [i for i in (q.get("comps") or [""])[0].split(",") if i]
                bus = (q.get("bus") or ["preview"])[0]
                values = engine.live.get().get(bus, {}).get("values", {})
                blob = export.build(engine.ws, engine.assets, ids, values, engine.data_snapshot()["tables"])
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
            if path.startswith(("/assets/", "/library/")):
                full = engine.assets.path_of(unquote(path[1:]))
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
                    return self._json(engine.upload(name, self.rfile, length, fps, graphic=(q.get("graphic") or [""])[0] == "1"))
                if path in ("/api/teams/import", "/api/teams/logo", "/api/teams/photo"):
                    if length > 30 << 20:
                        raise ValueError("That file is too big (30 MB at most)")
                    blob = self.rfile.read(length)
                    if path == "/api/teams/import":
                        n = engine.import_teams(blob.decode("utf-8-sig", "replace"))
                        return self._json({"added": n, "teams": engine.teams.list()})
                    name = unquote(self.headers.get("X-Filename") or (q.get("name") or [""])[0])
                    if path == "/api/teams/photo":
                        return self._json({"photo": engine.save_team_photo((q.get("player") or [""])[0], name, blob)})
                    logo = engine.save_team_logo((q.get("team") or [""])[0], name, blob, (q.get("game") or [""])[0])
                    return self._json({"logo": logo, "teams": engine.teams.list()})
                if path in ("/api/workspaces/picture", "/api/global/logo"):
                    # (the picture's bytes are the body)
                    name = unquote(self.headers.get("X-Filename") or (q.get("name") or [""])[0])
                    video = path == "/api/global/logo" and (q.get("side") or [""])[0] == "bgloop"
                    if length > (400 << 20 if video else 30 << 20):
                        raise ValueError("That file is too big (" + ("400" if video else "30") + " MB at most)")
                    blob = self.rfile.read(length)
                    if path == "/api/global/logo":
                        return self._json({"global": engine.save_global_logo((q.get("side") or [""])[0], name, blob)})
                    return self._json({"picture": engine.set_workspace_picture((q.get("id") or [""])[0], name, blob)})
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
                    if "name" in body:
                        ws.rename(body.get("name", ""))
                    if "stinger_anim_delay" in body:
                        ws.set_stinger_delay(body["stinger_anim_delay"])
                # --- workspaces ---
                elif path == "/api/workspaces/create":
                    result = {"id": engine.create_workspace(body.get("name", ""), body.get("template", "scc"),
                                                            body.get("open", True))}
                elif path == "/api/workspaces/open":
                    engine.open(body["id"])
                elif path == "/api/workspaces/rename":
                    engine.rename_workspace(body["id"], body.get("name", ""))
                elif path == "/api/workspaces/delete":
                    engine.delete_workspace(body["id"])
                elif path == "/api/pack/import":
                    result = {"added": engine.import_pack(body.get("ids"))}
                # --- global configuration, game HUDs ---
                elif path == "/api/global":
                    result = {"global": engine.set_global(body.get("global") or {})}
                elif path == "/api/timer":
                    result = {"global": engine.timer(body.get("action") or "", body.get("secs"), body.get("down"))}
                elif path == "/api/teams":
                    result = {"teams": engine.save_teams(body.get("teams") or [])}
                elif path == "/api/roster/links":
                    result = engine.roster_links(body.get("game"), body.get("fields"))
                elif path == "/api/roster/link":
                    engine.link_player(body.get("side"), body.get("player", -1), body.get("ign", ""))
                    result = engine.roster_links(body.get("game"), body.get("fields"))
                elif path == "/api/stats/clear":
                    engine.clear_stats()
                elif path == "/api/ingest":
                    engine.ingest(body, self.client_address[0])
                    result = {"ok": True, "global": engine.global_config()}
                # --- on air ---
                elif path == "/api/companion":
                    result = companion.act(engine, body)
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
                    engine.assets.delete(body["path"])
                    ws.touch_assets()
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
                    if body.get("network_address"):
                        ipaddress.IPv4Address(str(body["network_address"]))   # (ValueError: not an address)
                    engine.settings.update(body)
                    if "network_address" in body and engine.server:
                        engine.server.rebind(engine.settings.get()["network_address"] or "")
                    engine.changed()
                elif path == "/api/camera-looks":
                    looks = body.get("looks")
                    if not isinstance(looks, list) or len(json.dumps(looks)) > 512 * 1024:
                        raise ValueError("Bad camera looks")
                    engine.settings.update({"camera_looks": [lk for lk in looks if isinstance(lk, dict) and lk.get("name")
                                                             and isinstance(lk.get("cams"), dict)]})
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
    """The web server: on every network card, or on this PC (127.0.0.1) and one
    network only (settings "network_address"). Other PCs are turned away unless
    allowed, so allowing them needs no restart; changing the network rebinds."""

    def __init__(self, engine, port, address=""):
        self.engine = engine
        self.port = port
        self.lock = threading.Lock()
        self.httpds = {}      # host -> server
        self.address = None
        self._bind(address, first=True)

    def _serve(self, host):
        httpd = ThreadingHTTPServer((host, self.port), make_handler(self.engine))
        httpd.daemon_threads = True
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.httpds[host] = httpd

    def _close(self):
        for httpd in self.httpds.values():
            httpd.shutdown()
            httpd.server_close()
        self.httpds = {}

    def _bind(self, address, first=False):
        with self.lock:
            self._close()
            self.address = address
            if not address:
                self._serve("0.0.0.0")
                return
            self._serve("127.0.0.1")
            try:
                self._serve(address)
                if not first:
                    log(f"Other PCs now reach this engine on {address} only")
            except OSError:
                log(f"This PC isn't on {address} right now: only this PC can use the engine until it is", "warn")
                threading.Thread(target=self._retry, args=(address,), daemon=True).start()

    def _retry(self, address):
        """Binds the chosen network once this PC is on it (the cable's back in, the VLAN's up)."""
        while True:
            time.sleep(10)
            with self.lock:
                if self.address != address or address in self.httpds:
                    return
                try:
                    self._serve(address)
                    log(f"On {address} now: other PCs can reach this engine there")
                    return
                except OSError:
                    pass

    def rebind(self, address):
        if address != self.address:
            # (a moment later: the request that asked for it gets its answer first)
            threading.Timer(0.3, self._bind, args=(address,)).start()

    def stop(self):
        with self.lock:
            self.address = None
            self._close()


def start(engine):
    """Starts the web server (raises OSError if the port is taken)."""
    s = engine.settings.get()
    port = s["http_port"]
    engine.server = Server(engine, port, s.get("network_address") or "")
    clean_up_old_update()
    engine.updater.check_in_background()
    threading.Thread(target=engine.sources.refresh, daemon=True).start()
    log(f"GFX Engine {engine.updater.current} running - control panel http://localhost:{port}/control")
    log(f"Program output (browser source, 1920x1080): http://localhost:{port}/output")
    return engine.server
