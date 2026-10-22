"""The SCC graphics that come with the engine (starter/), and keeping a
workspace's copies of them up to date.

When the engine has newer versions of the SCC graphics, a workspace that
still has a graphic exactly as an older version shipped it (not changed in
Composer) gets the new one in its place, with any files it needs. A graphic
that was changed is left alone; Outputs > Workspace can still add the SCC
graphics a workspace doesn't have.

starter/project.json keeps, for each graphic, the signatures of the
versions shipped before ("pack_history": {name: [signature, ...]}), and
the graphics added to the pack since the first ("pack_new"): a workspace
made from the pack gets each of those once (if it was deleted, it stays
deleted).
"""

import copy
import hashlib
import json
import os
import shutil
import time

from . import export
from .log import log
from .project import new_id


def signature(comp):
    """What a graphic looks like (everything but its id)."""
    body = {k: v for k, v in comp.items() if k != "id"}
    return hashlib.sha1(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def _read(starter):
    try:
        with open(os.path.join(starter, "project.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError, TypeError):
        return {}


def copy_files(comp, starter, ws):
    """The files a graphic from the pack uses, into the workspace (if not there)."""
    used = set()
    export._walk_assets(comp, used)
    for rel in used:
        src = os.path.join(starter, rel)
        dest = ws.asset_path(rel)
        if dest and os.path.isfile(src) and not os.path.exists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)


def upgrade(ws, starter):
    """Brings the workspace's untouched SCC graphics up to date. Returns their names."""
    project = _read(starter) if starter else {}
    history = project.get("pack_history") or {}
    if not history:
        return []
    latest = {c["name"]: c for c in project.get("compositions", [])}
    done = []
    with ws.lock:
        comps = ws.data["compositions"]
        seen = list(ws.data.get("pack_seen") or [])
        # (only for workspaces made from the pack: an empty one stays empty)
        from_pack = any(c.get("name") in latest for c in comps)
        for name in project.get("pack_new") or []:
            if name in seen or name not in latest:
                continue
            seen.append(name)
            if from_pack and not any(c.get("name") == name for c in comps):
                fresh = copy.deepcopy(latest[name])
                fresh["id"] = new_id("c")
                copy_files(fresh, starter, ws)
                comps.append(fresh)
                done.append(name)
        if seen != list(ws.data.get("pack_seen") or []):
            ws.data["pack_seen"] = seen
            ws.changed()
        for i, comp in enumerate(comps):
            new = latest.get(comp.get("name"))
            if not new or signature(comp) not in history.get(comp["name"], []):
                continue
            if signature(comp) == signature(new):
                continue
            fresh = copy.deepcopy(new)
            fresh["id"] = comp["id"]
            copy_files(fresh, starter, ws)
            comps[i] = fresh
            done.append(comp["name"])
        # Graphics taken out of the pack: the untouched copies go.
        removed = set(project.get("pack_removed") or [])
        keep = [c for c in comps if not (c.get("name") in removed and signature(c) in history.get(c["name"], []))]
        if len(keep) != len(comps):
            done += [c["name"] for c in comps if c not in keep]
            comps[:] = keep
        # What the graphics now share, for a workspace that never set it.
        g = ws.data.get("global") or {}
        pg = project.get("global") or {}
        changed_global = False
        if not g.get("sponsors") and not g.get("sponsor_epoch") and pg.get("sponsors"):
            for sp in pg["sponsors"]:
                copy_files({"src": sp["logo"]}, starter, ws)
            g["sponsors"] = copy.deepcopy(pg["sponsors"])
            changed_global = True
        # A newer set of sponsors, for a workspace that still has the pack's old one.
        old_set = {"assets/sponsors/Subway.png", "assets/sponsors/NAC Esports.png"}
        if pg.get("sponsor_set", 1) > 1 and g.get("sponsors") and all(sp.get("logo") in old_set for sp in g["sponsors"]):
            for sp in pg["sponsors"]:
                copy_files({"src": sp["logo"]}, starter, ws)
            g["sponsors"] = copy.deepcopy(pg["sponsors"])
            g["sponsor_epoch"] = round(time.time(), 3)
            changed_global = True
        if "ticker" not in g and pg.get("ticker"):
            g["ticker"] = list(pg["ticker"])
            changed_global = True
        if "schedule" not in g and pg.get("schedule"):
            g["schedule"] = copy.deepcopy(pg["schedule"])
            changed_global = True
        if changed_global:
            ws.data["global"] = g
        if done or changed_global:
            ws.changed()
    if done:
        log(f"Brought {len(done)} SCC graphic(s) up to date (or took out the ones the pack no longer has)")
    return done
