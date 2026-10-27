"""The workspace: every graphic (composition), the transitions, the data
sources, and the asset files they use.

    workspace/project.json   compositions, transitions, data sources
    workspace/assets/...     images, video, fonts, Lottie files (served as assets/...)

A composition is a 1920x1080 graphic made of layers, bottom to top:

    {"id", "name", "layer": 0 (stacking on the output: higher is in front),
     "kind": "board" | "lower third" | "overlay" (one board and one lower third on air at a time),
     "layers": [{"id", "name", "type": "image" | "video" | "text" | "rect" | "lottie",
                 "x", "y", "w", "h", "opacity", "rotation", "visible", "blend",
                 "field": "" (the name it's edited by in Control; "" = fixed),
                 "anim": {"in": {"type", "dur", "delay"}, "out": {...}},
                 ...type's own: src, fit, loop (media); text, font, size, color,
                 align, valign, tracking, caps, lineHeight, fit, scroll (text);
                 fill, radius, stroke, strokeWidth (rect)}]}
"""

import copy
import json
import os
import secrets
import shutil
import threading

from .log import log

TRANSITION_TYPES = ("cut", "fade", "dip", "wipe", "animate", "stinger")

DEFAULT_TRANSITIONS = [
    {"id": "cut", "name": "Cut", "type": "cut", "enabled": True},
    {"id": "fade", "name": "Fade", "type": "fade", "dur": 500, "enabled": True},
    {"id": "animate", "name": "Animate", "type": "animate", "enabled": True},
    {"id": "dip", "name": "Dip to black", "type": "dip", "dur": 800, "color": "#000000", "enabled": False},
    {"id": "wipe", "name": "Wipe", "type": "wipe", "dur": 600, "direction": "left", "enabled": False},
]

ANIM_NONE = {"type": "fade", "dur": 300, "delay": 0}


def new_id(prefix=""):
    return prefix + secrets.token_hex(4)


def blank_project():
    return {"name": "My graphics", "compositions": [], "transitions": copy.deepcopy(DEFAULT_TRANSITIONS),
            "default_transition": "fade", "sources": []}


def blank_layer(kind, **extra):
    layer = {"id": new_id("l"), "name": kind.title(), "type": kind, "x": 760, "y": 440, "w": 400, "h": 200,
             "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
             "anim": {"in": dict(ANIM_NONE), "out": dict(ANIM_NONE)}}
    if kind == "text":
        layer.update({"text": "Text", "font": "Inter", "size": 72, "color": "#ffffff", "align": "left",
                      "valign": "top", "tracking": 0, "caps": False, "lineHeight": 1.15, "fit": "shrink",
                      "weight": 700, "italic": False, "scroll": 0, "h": 90})
    elif kind == "rect":
        layer.update({"fill": "#0b6b3a", "radius": 0, "stroke": "#f5c518", "strokeWidth": 0})
    elif kind in ("image", "video", "lottie"):
        layer.update({"src": "", "fit": "contain", "loop": True})
    layer.update(extra)
    return layer


def blank_comp(name="New graphic"):
    return {"id": new_id("c"), "name": name, "layer": 0, "layers": []}


class Workspace:
    def __init__(self, folder, starter=None):
        self.folder = folder
        self.assets_dir = os.path.join(folder, "assets")
        self.path = os.path.join(folder, "project.json")
        self.lock = threading.RLock()
        self.rev = 0
        self.listeners = []
        os.makedirs(self.assets_dir, exist_ok=True)
        if not os.path.exists(self.path) and starter and os.path.isfile(os.path.join(starter, "project.json")):
            # First run: start with the example graphics.
            shutil.copytree(starter, folder, dirs_exist_ok=True)
            log("Created the workspace from the example graphics")
        self.data = blank_project()
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                self.data.update(json.load(f))
        self._timer = None

    # --- reading -------------------------------------------------------

    def get(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def snapshot(self):
        """Like get(), but the same copy until the project changes: read it,
        never change it (the outputs' state is made from it many times a second)."""
        with self.lock:
            if getattr(self, "_snap_rev", None) != self.rev:
                self._snap, self._snap_rev = copy.deepcopy(self.data), self.rev
            return self._snap

    def comp(self, cid):
        with self.lock:
            c = next((c for c in self.data["compositions"] if c["id"] == cid), None)
            return copy.deepcopy(c) if c else None

    def transition(self, tid):
        with self.lock:
            t = next((t for t in self.data["transitions"] if t["id"] == tid), None)
            return copy.deepcopy(t) if t else None

    # --- changing ------------------------------------------------------

    def changed(self):
        """Call with the lock held after changing self.data."""
        self.rev += 1
        if self._timer:
            self._timer.cancel()
        # Saves are batched: dragging a layer changes it many times a second.
        self._timer = threading.Timer(0.4, self.save)
        self._timer.daemon = True
        self._timer.start()
        for fn in list(self.listeners):
            fn()

    def close(self):
        """Saves now (and not again later)."""
        if self._timer:
            self._timer.cancel()
        self.save()

    def save(self):
        with self.lock:
            text = json.dumps(self.data, indent=1)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, self.path)

    def add_comp(self, comp=None, after=None):
        comp = comp or blank_comp()
        comp.setdefault("id", new_id("c"))
        with self.lock:
            comps = self.data["compositions"]
            if any(c["id"] == comp["id"] for c in comps):
                comp["id"] = new_id("c")
            idx = next((i + 1 for i, c in enumerate(comps) if c["id"] == after), len(comps))
            comps.insert(idx, comp)
            self.changed()
        return comp

    def put_comp(self, comp):
        with self.lock:
            comps = self.data["compositions"]
            for i, c in enumerate(comps):
                if c["id"] == comp.get("id"):
                    comps[i] = comp
                    self.changed()
                    return comp
        raise KeyError("No such graphic")

    def duplicate_comp(self, cid):
        comp = self.comp(cid)
        if not comp:
            raise KeyError("No such graphic")
        comp["id"] = new_id("c")
        comp["name"] += " copy"
        for layer in comp["layers"]:
            layer["id"] = new_id("l")
        return self.add_comp(comp, after=cid)

    def delete_comp(self, cid):
        with self.lock:
            self.data["compositions"] = [c for c in self.data["compositions"] if c["id"] != cid]
            self.changed()

    def order_comps(self, ids):
        with self.lock:
            by_id = {c["id"]: c for c in self.data["compositions"]}
            ordered = [by_id.pop(i) for i in ids if i in by_id]
            self.data["compositions"] = ordered + list(by_id.values())
            self.changed()

    def set_transitions(self, transitions, default=None):
        clean = []
        for t in transitions:
            if t.get("type") not in TRANSITION_TYPES:
                raise ValueError(f"Unknown transition type {t.get('type')!r}")
            t = dict(t)
            t.setdefault("id", new_id("t"))
            t.setdefault("name", t["type"].title())
            clean.append(t)
        if clean and not any(t.get("enabled", True) for t in clean):
            clean[0]["enabled"] = True
        with self.lock:
            self.data["transitions"] = clean
            if default is not None:
                self.data["default_transition"] = default
            if not any(t["id"] == self.data["default_transition"] for t in clean) and clean:
                self.data["default_transition"] = clean[0]["id"]
            self.changed()

    def set_global(self, g):
        with self.lock:
            self.data["global"] = g
            self.changed()

    def set_picture(self, name):
        with self.lock:
            self.data["picture"] = name
            self.changed()

    def set_sources(self, sources):
        with self.lock:
            self.data["sources"] = sources
            self.changed()

    def rename(self, name):
        with self.lock:
            self.data["name"] = str(name)[:80]
            self.changed()

    def set_stinger_delay(self, ms):
        """How long after a stinger TAKE the new graphics start their intro
        animations (ms; 0 = they cut in under the stinger, unanimated)."""
        try:
            ms = int(float(ms or 0))
        except (TypeError, ValueError):
            raise ValueError("The delay must be a number of milliseconds")
        with self.lock:
            self.data["stinger_anim_delay"] = max(0, min(ms, 60000))
            self.changed()

    # --- assets --------------------------------------------------------

    def asset_path(self, rel):
        """workspace/assets/... on disk for "assets/...", or None."""
        rel = rel.replace("\\", "/")
        if not rel.startswith("assets/"):
            return None
        path = os.path.normpath(os.path.join(self.folder, rel))
        root = os.path.normpath(self.assets_dir) + os.sep
        return path if path.startswith(root) else None

    def unique_asset(self, name, sub=""):
        """A free "assets/<sub>/<name>" (adds -2, -3 ... if taken) and its path on disk."""
        base, ext = os.path.splitext(os.path.basename(name.replace("\\", "/")))
        base = "".join(ch if ch.isalnum() or ch in " -_.()" else "_" for ch in base).strip() or "file"
        folder = os.path.join(self.assets_dir, sub) if sub else self.assets_dir
        os.makedirs(folder, exist_ok=True)
        n, candidate = 1, base + ext.lower()
        while os.path.exists(os.path.join(folder, candidate)):
            n += 1
            candidate = f"{base}-{n}{ext.lower()}"
        rel = "/".join(p for p in ("assets", sub.replace(os.sep, "/"), candidate) if p)
        return rel, os.path.join(folder, candidate)

    def touch_assets(self):
        """Files were added or changed: tell the pages."""
        with self.lock:
            self.changed()

    def delete_asset(self, rel):
        path = self.asset_path(rel)
        if not path or not os.path.exists(path):
            raise KeyError("No such file")
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        with self.lock:
            self.changed()

    def used_assets(self):
        """Every "assets/..." the project refers to."""
        found = set()

        def walk(v):
            if isinstance(v, dict):
                for x in v.values():
                    walk(x)
            elif isinstance(v, list):
                for x in v:
                    walk(x)
            elif isinstance(v, str) and v.startswith("assets/"):
                found.add(v)
        with self.lock:
            walk(self.data)
        return found
