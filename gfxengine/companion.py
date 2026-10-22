"""Bitfocus Companion control (the module is in companion-module/).

    GET  /api/companion   the graphics (and which are on Preview and Program),
                          the transitions, the quick functions' states and the
                          variables (Companion polls this for its feedbacks)
    POST /api/companion   {"action": "preview" | "program", "id": graphic, "mode": "toggle" | "on" | "off",
                           "transition": "" (program only: "" = the graphic's own animation)}
                          {"action": "take", "transition": "" (= the default)}
                          {"action": "clear", "bus": "program" | "preview" | "both"}
                          {"action": "send", "id": graphic or "" (= everything on Program)}
                          {"action": "run", "id": "score_left_up"}

A graphic is its id or its name (so a button still works in another
workspace that has the same graphics).
"""

from .globalcfg import CASTER_SCALE, CLOCK_LABELS, timer_now, timer_running
from .log import log

# Quick functions: id -> name. Each has a state (lit on the button) where it makes sense.
QUICK = {
    "score_left_up": "Score: left team +1",
    "score_left_down": "Score: left team -1",
    "score_right_up": "Score: right team +1",
    "score_right_down": "Score: right team -1",
    "score_reset": "Score: reset to 0-0",
    "clock_time": "Clock: local time",
    "clock_soon": "Clock: Starting Soon countdown",
    "clock_brb": "Clock: Be Right Back countdown",
    "timer_toggle": "Timer: start / pause",
    "timer_reset": "Timer: reset",
    "bgloop": "Background loop: on / off",
    "roster_left": "Player graphics: left team",
    "roster_right": "Player graphics: right team",
    **{f"caster_{n}": f"Casters: {n} box{'es' if n > 1 else ''}" for n in sorted(CASTER_SCALE)},
}

# On/off states that can only be read (feedbacks).
STATES = {
    "preview_any": "Something is on Preview",
    "program_any": "Something is on Program",
}


def _names(ws):
    return {c["id"]: c["name"] for c in ws.get()["compositions"]}


def find(ws, key):
    """A graphic's id, from its id or its name."""
    comps = ws.get()["compositions"]
    key = str(key or "").strip()
    for c in comps:
        if c["id"] == key:
            return c["id"]
    for c in comps:
        if c["name"].strip().lower() == key.lower():
            return c["id"]
    raise ValueError(f"No graphic {key!r} in this workspace")


def state(engine):
    project = engine.ws.get()
    live = engine.live.get()
    g = engine.global_config()
    pvw, pgm = live["preview"]["on"], live["program"]["on"]
    graphics = [{"id": c["id"], "name": c["name"], "kind": c.get("kind") or "overlay",
                 "preview": c["id"] in pvw, "program": c["id"] in pgm} for c in project["compositions"]]
    transitions = [{"id": t["id"], "name": t.get("name") or t["id"]} for t in project["transitions"]
                   if t.get("enabled") is not False]
    names = _names(engine.ws)
    on = {
        "preview_any": bool(pvw), "program_any": bool(pgm),
        "clock_time": g["clock"]["mode"] == "time", "clock_soon": g["clock"]["mode"] == "soon",
        "clock_brb": g["clock"]["mode"] == "brb", "timer_toggle": timer_running(g["timer"]), "bgloop": g["bgloop"]["on"],
        "roster_left": g["roster"] == "left", "roster_right": g["roster"] == "right",
        **{f"caster_{n}": g["caster"]["count"] == n for n in CASTER_SCALE},
    }
    default = next((t["name"] for t in transitions if t["id"] == project.get("default_transition")), "")
    variables = {
        "workspace": project.get("name", ""),
        "preview": ", ".join(names.get(i, "") for i in pvw),
        "program": ", ".join(names.get(i, "") for i in pgm),
        "default_transition": default,
        "clock": CLOCK_LABELS.get(g["clock"]["mode"], ""),
        "timer": "%02d:%02d" % divmod(int(timer_now(g["timer"]) + (0.999 if g["timer"]["down"] else 0)), 60),
        "best_of": str(g["best_of"]),
        "casters": str(g["caster"]["count"]),
    }
    for side in ("left", "right"):
        for key in ("name", "short", "score"):
            variables[f"{side}_{key}"] = str(g[side][key])
    return {"graphics": graphics, "transitions": transitions, "default_transition": project.get("default_transition"),
            "states": on, "variables": variables}


def _run(engine, key):
    g = engine.global_config()
    if key.startswith("score_"):
        if key == "score_reset":
            engine.set_global({"left": {"score": 0}, "right": {"score": 0}})
        else:
            _, side, way = key.split("_")
            engine.set_global({side: {"score": max(0, g[side]["score"] + (1 if way == "up" else -1))}})
    elif key.startswith("clock_"):
        engine.set_global({"clock": dict(g["clock"], mode=key.split("_", 1)[1])})
    elif key.startswith("timer_"):
        engine.timer(key.split("_", 1)[1])
    elif key == "bgloop":
        engine.set_global({"bgloop": {"on": not g["bgloop"]["on"]}})
    elif key.startswith("roster_"):
        engine.set_global({"roster": key.split("_", 1)[1]})
    elif key.startswith("caster_"):
        engine.set_global({"caster": dict(g["caster"], count=int(key.split("_", 1)[1]))})
    else:
        raise ValueError(f"Unknown quick function: {key}")


def act(engine, body):
    """Do one Companion action; returns state(engine)."""
    action = body.get("action")
    live, ws = engine.live, engine.ws
    if action in ("preview", "program"):
        cid = find(ws, body.get("id"))
        mode = body.get("mode") or "toggle"
        now = cid in live.get()[action]["on"]
        want = (not now) if mode == "toggle" else mode == "on"
        if action == "preview":
            if want != now:
                live.cue(cid, want)
        elif want or now:
            # (taking a graphic that's on air again replays it with its Preview values)
            live.program(cid, want, body.get("transition") or "animate")
    elif action == "take":
        live.take(body.get("transition") or None)
    elif action == "clear":
        bus = body.get("bus") or "program"
        if bus in ("preview", "both"):
            live.clear("preview")
        if bus in ("program", "both"):
            live.clear("program", body.get("transition") or "animate")
    elif action == "send":
        now = live.get()
        ids = ([find(ws, body["id"])] if body.get("id") else
               [i for i in now["program"]["on"] if i in now["preview"]["values"]])   # (not ones never edited)
        for cid in ids:
            live.send_values(cid)
    elif action == "run":
        key = body.get("id") or ""
        if key not in QUICK:
            raise ValueError(f"Unknown quick function: {key}")
        _run(engine, key)
        log(f"Companion: {QUICK[key]}")
    else:
        raise ValueError(f"Unknown action: {action}")
    return state(engine)
