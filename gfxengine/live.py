"""What's on air: the Preview and Program buses.

Each bus has the graphics that are on it and the field values they show.
Graphics are cued up and edited on Preview, then Take puts Preview on
Program with a transition (cut, fade, stinger...). A graphic can also be
taken in or out of Program on its own, and its new values sent to air
without a transition.

    {"preview": {"on": [comp ids], "values": {comp id: {field: value}}},
     "program": {...same...},
     "take": {"seq", "transition": {...}, "comps": [ids] or null}}

Every change to Program bumps take.seq (a transition plays) or
program.seq (new values only, shown in place).
"""

import copy
import json
import os
import threading
import time

BUSES = ("preview", "program")


def _bus():
    return {"on": [], "values": {}, "seq": 0}


class Live:
    def __init__(self, workspace, path=None):
        self.ws = workspace
        self.path = path or os.path.join(workspace.folder, "live.json")
        self.lock = threading.RLock()
        self.listeners = []
        self.state = {"preview": _bus(), "program": _bus(), "take": {"seq": 0, "transition": {"type": "cut"}, "comps": None}}
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    saved = json.load(f)
                for bus in BUSES:
                    self.state[bus].update(saved.get(bus) or {})
            except (OSError, ValueError):
                pass

    def get(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def _changed(self):
        with self.lock:
            snapshot = json.dumps({b: self.state[b] for b in BUSES})
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(snapshot)
        os.replace(tmp, self.path)
        for fn in list(self.listeners):
            fn()

    def _ids(self):
        return {c["id"] for c in self.ws.get()["compositions"]}

    def _transition(self, tid):
        """The transition to play, by id (default: the project's default)."""
        project = self.ws.get()
        tid = tid or project.get("default_transition")
        t = next((t for t in project["transitions"] if t["id"] == tid), None)
        if not t and tid == "cut":
            t = {"id": "cut", "name": "Cut", "type": "cut"}
        if not t:
            raise KeyError(f"No transition {tid!r}")
        return t

    def _quick(self, tid):
        """For one graphic in or out: the transition asked for, else the
        graphic's own animation."""
        return self.ws.transition(tid) or {"id": "animate", "type": "animate"}

    def _order(self, ids):
        """ids in the project's order (which is also their stacking order)."""
        order = [c["id"] for c in self.ws.get()["compositions"]]
        return [i for i in order if i in ids]

    # --- Preview -------------------------------------------------------

    def cue(self, cid, on=True):
        """Put a graphic on Preview (or take it off)."""
        if cid not in self._ids():
            raise KeyError("No such graphic")
        with self.lock:
            on_now = set(self.state["preview"]["on"])
            on_now.add(cid) if on else on_now.discard(cid)
            self.state["preview"]["on"] = self._order(on_now)
            self.state["preview"]["seq"] += 1
        self._changed()

    def set_values(self, cid, values, bus="preview"):
        """Change a graphic's field values on a bus ("preview", "program" or "both")."""
        if cid not in self._ids():
            raise KeyError("No such graphic")
        buses = BUSES if bus == "both" else (bus,)
        with self.lock:
            for b in buses:
                if b not in BUSES:
                    raise ValueError(f"No bus {b!r}")
                current = self.state[b]["values"].setdefault(cid, {})
                for k, v in values.items():
                    if v is None:
                        current.pop(k, None)
                    else:
                        current[str(k)] = v if isinstance(v, (str, int, float, bool)) else json.dumps(v)
                self.state[b]["seq"] += 1
        self._changed()

    def send_values(self, cid):
        """Show a graphic's Preview values on Program, in place (no transition)."""
        with self.lock:
            values = copy.deepcopy(self.state["preview"]["values"].get(cid, {}))
            self.state["program"]["values"][cid] = values
            self.state["program"]["seq"] += 1
        self._changed()

    # --- Program -------------------------------------------------------

    def take(self, transition=None):
        """Preview goes to Program with a transition."""
        t = self._transition(transition)
        with self.lock:
            self.state["program"]["on"] = list(self.state["preview"]["on"])
            self.state["program"]["values"] = copy.deepcopy(self.state["preview"]["values"])
            self.state["program"]["seq"] += 1
            self._bump_take(t, None)
        self._changed()
        return t

    def program(self, cid, on, transition="animate"):
        """Take one graphic in or out of Program, leaving the rest as it is."""
        if cid not in self._ids():
            raise KeyError("No such graphic")
        t = self._quick(transition)
        with self.lock:
            on_now = set(self.state["program"]["on"])
            if on:
                on_now.add(cid)
                # Goes on air with what it shows on Preview.
                if cid in self.state["preview"]["values"]:
                    self.state["program"]["values"][cid] = copy.deepcopy(self.state["preview"]["values"][cid])
            else:
                on_now.discard(cid)
            self.state["program"]["on"] = self._order(on_now)
            self.state["program"]["seq"] += 1
            self._bump_take(t, [cid])
        self._changed()

    def clear(self, bus="program", transition="animate"):
        with self.lock:
            if bus == "preview":
                self.state["preview"]["on"] = []
                self.state["preview"]["seq"] += 1
            else:
                t = self._quick(transition)
                self.state["program"]["on"] = []
                self.state["program"]["seq"] += 1
                self._bump_take(t, None)
        self._changed()

    def _bump_take(self, t, comps):
        self.state["take"] = {"seq": self.state["take"]["seq"] + 1, "transition": copy.deepcopy(t),
                              "comps": comps, "at": time.time()}

    def forget(self, cid):
        """A graphic was deleted: take it off both buses."""
        with self.lock:
            for b in BUSES:
                if cid in self.state[b]["on"]:
                    self.state[b]["on"].remove(cid)
                    self.state[b]["seq"] += 1
                self.state[b]["values"].pop(cid, None)
        self._changed()
