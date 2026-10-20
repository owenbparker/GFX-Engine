"""The SCC graphics that come with the engine (starter/), and keeping a
workspace's copies of them up to date.

When the engine has newer versions of the SCC graphics, a workspace that
still has a graphic exactly as an older version shipped it (not changed in
Composer) gets the new one in its place, with any files it needs. A graphic
that was changed is left alone; Outputs > Workspace can still add the SCC
graphics a workspace doesn't have.

starter/project.json keeps, for each graphic, the signatures of the
versions shipped before ("pack_history": {name: [signature, ...]}).
"""

import copy
import hashlib
import json
import os
import shutil

from . import export
from .log import log


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
        # What the graphics now share, for a workspace that never set it.
        g = ws.data.get("global") or {}
        pg = project.get("global") or {}
        changed_global = False
        if not g.get("sponsors") and not g.get("sponsor_epoch") and pg.get("sponsors"):
            for sp in pg["sponsors"]:
                copy_files({"src": sp["logo"]}, starter, ws)
            g["sponsors"] = copy.deepcopy(pg["sponsors"])
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
        log(f"Brought {len(done)} SCC graphic(s) up to date")
    return done
