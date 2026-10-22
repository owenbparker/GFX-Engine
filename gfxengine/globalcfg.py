"""Global configuration: the event's basics (the two teams, the series, the
event), set once per workspace and used by any graphic as the data source
"Global": {{Global!Left name}}, {{Global!Left logo}}, {{Global!Left score}}...
(a logo is a picture's path, so an image field can use it too).

It also holds what most graphics share: the tournament's logo, the sponsors
(shown one after another wherever a graphic has the sponsor spot, each for
its own number of seconds) and the background loop behind the full-screen
boards (its video, colour, brightness and speed), the ticker's lines and
the tournament's brackets (see tournament.py) and the upcoming schedule
(see schedule.py).

Game HUDs connected to the engine keep the series score up to date, and can
take the team names, short names and logos from here.
"""

import copy
import re
import time

from . import schedule, tournament

DEFAULT = {
    "event": "", "stage": "", "best_of": 3, "game": "",   # game: "" = from the score
    # (game: the team's game in the team list, for the one school with several)
    "left": {"name": "", "short": "", "logo": "", "color": "#0b6b3a", "score": 0, "game": ""},
    "right": {"name": "", "short": "", "logo": "", "color": "#b8191c", "score": 0, "game": ""},
    "custom": [],    # [[label, value], ...]
    "tournament_logo": "",
    # [{"logo": "assets/sponsors/x.png", "secs": 10}, ...]; the rotation is
    # counted from sponsor_epoch (when the list last changed) so every output
    # shows the same one at the same time.
    "sponsors": [], "sponsor_epoch": 0,
    "bgloop": {"on": True, "src": "", "color": "#2fa85a", "brightness": 1.6, "speed": 1},
    "ticker": [],    # its lines, shown one after another
    "tournament": tournament.default(),
    "schedule": schedule.default(),
    # The clock graphics show ({{clock}} and {{Global!Clock label}}): the time of
    # day, or a countdown to "until" for Starting Soon or Be Right Back.
    "clock": {"mode": "time", "until": "", "zone": "EST"},
    # The timer ({{timer}}): "secs" when stopped (or when it was started), counting
    # from "started" (the engine's time.time(), 0 = stopped), up or "down" to 0.
    # Reset goes back to "from".
    "timer": {"secs": 0, "from": 0, "down": False, "started": 0},
    "roster": "left",    # whose players the player graphics show
    # who the Player stats page shows: the top player ("auto") or one picked ("left 3")
    "player_stats": "auto",
    # The caster lower third: how many boxes, the box's colour (primary) and
    # the text and shadow's (secondary).
    "caster": {"count": 1, "primary": "#c2bdff", "secondary": "#001a1a"},
    # The graphics whose own output (/output?comp=id) is switched on: it always
    # shows its graphic, on Program or not (the rest show nothing, to save the PC).
    "outputs_on": [],
    # What the stats pages show for each team's players: their "headshot" or "champion".
    "pictures": {"team": {"left": "headshot", "right": "headshot"}, "player": {"left": "headshot", "right": "headshot"}},
}
# The caster box in the design (x, y, w, h), and where the boxes go: their
# bottom edge, the gap between them, and how big they are for 1-4 boxes.
CASTER_BOX = (619, 451, 683, 178)
CASTER_BOTTOM, CASTER_GAP = 975, 40
CASTER_SCALE = {1: 1, 2: 1, 3: 0.85, 4: 0.63}


def caster_moves(count):
    """Each caster box's "dx dy scale" from the design's place: side by side,
    centred, along the bottom of the screen."""
    x, y, w, h = CASTER_BOX
    sc = CASTER_SCALE[count]
    total = count * w * sc + (count - 1) * CASTER_GAP
    left = (1920 - total) / 2
    dy = CASTER_BOTTOM - h * sc - y
    return [f"{round(left + i * (w * sc + CASTER_GAP) - x)} {round(dy)} {sc}" for i in range(count)]
CLOCK_LABELS = {"time": "LOCAL TIME", "soon": "STARTING SOON", "brb": "BE RIGHT BACK"}
TICKER_GAP = "  |  "
TEAM_KEYS = ("name", "short", "logo", "color", "score", "game")
DEFAULT_LOOP = "loops/scc-bg-loop.webm"   # (comes with the engine, in web/)


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def clean(g):
    out = copy.deepcopy(DEFAULT)
    g = g or {}
    for k in ("event", "stage", "game"):
        out[k] = str(g.get(k, out[k]) or "")[:200]
    try:
        out["best_of"] = max(1, min(9, int(g.get("best_of") or 3)))
    except (TypeError, ValueError):
        pass
    for side in ("left", "right"):
        team = g.get(side) or {}
        for k in TEAM_KEYS:
            if k in team:
                out[side][k] = team[k]
        try:
            out[side]["score"] = max(0, int(out[side]["score"] or 0))
        except (TypeError, ValueError):
            out[side]["score"] = 0
        out[side] = {k: (v if k == "score" else str(v or "")[:300]) for k, v in out[side].items()}
    out["custom"] = [[str(r[0])[:80], str(r[1])[:500]] for r in (g.get("custom") or [])
                     if isinstance(r, (list, tuple)) and len(r) >= 2 and str(r[0]).strip()]
    out["tournament_logo"] = str(g.get("tournament_logo") or "")[:300]
    # (white: drawn all white in the rows of sponsor logos, like the design's)
    out["sponsors"] = [{"logo": str(sp.get("logo"))[:300], "secs": _num(sp.get("secs"), 1, 600, 10), "white": sp.get("white", True) is not False}
                       for sp in (g.get("sponsors") or []) if isinstance(sp, dict) and sp.get("logo")][:40]
    out["sponsor_epoch"] = _num(g.get("sponsor_epoch"), 0, 1e11, 0)
    loop = dict(DEFAULT["bgloop"], **(g.get("bgloop") or {}))
    out["bgloop"] = {"on": bool(loop.get("on")), "src": str(loop.get("src") or "")[:300],
                     "color": str(loop.get("color") or DEFAULT["bgloop"]["color"])[:30],
                     "brightness": _num(loop.get("brightness"), 0, 4, 1.6), "speed": _num(loop.get("speed"), 0.1, 4, 1)}
    out["ticker"] = [str(x).strip()[:300] for x in (g.get("ticker") or []) if str(x).strip()][:40]
    out["tournament"] = tournament.clean(g.get("tournament"))
    out["schedule"] = schedule.clean(g.get("schedule"))
    out["roster"] = "right" if g.get("roster") == "right" else "left"
    pick = str(g.get("player_stats") or "")
    out["player_stats"] = pick if re.match(r"^(left|right) ([1-9]|10)$", pick) else "auto"
    caster = dict(DEFAULT["caster"], **(g.get("caster") or {}))
    try:
        count = int(caster.get("count") or 1)
    except (TypeError, ValueError):
        count = 1
    colour = lambda v, d: v if isinstance(v, str) and re.match(r"^#[0-9a-fA-F]{6}$", v) else d
    # Team stats ("team") and Player stats ("player") each have their own;
    # the one setting before (v1.0.20-23: {"left", "right"}) becomes both.
    pics = g.get("pictures") or {}
    if "left" in pics or "right" in pics:
        pics = {"team": pics, "player": pics}
    out["pictures"] = {page: {side: "champion" if (pics.get(page) or {}).get(side) == "champion" else "headshot"
                              for side in ("left", "right")} for page in ("team", "player")}
    out["outputs_on"] = [str(i)[:40] for i in (g.get("outputs_on") or []) if isinstance(i, str)][:200]
    out["caster"] = {"count": count if count in CASTER_SCALE else 1,
                     "primary": colour(caster.get("primary"), DEFAULT["caster"]["primary"]),
                     "secondary": colour(caster.get("secondary"), DEFAULT["caster"]["secondary"])}
    clock = dict(DEFAULT["clock"], **(g.get("clock") or {}))
    until = str(clock.get("until") or "").strip()
    out["clock"] = {"mode": clock.get("mode") if clock.get("mode") in CLOCK_LABELS else "time",
                    "until": until if re.match(r"^\d{1,2}:\d{2}$", until) else "",
                    "zone": str(clock.get("zone") or "")[:12]}
    timer = dict(DEFAULT["timer"], **(g.get("timer") or {}))
    out["timer"] = {"secs": _num(timer.get("secs"), 0, 359999, 0), "from": _num(timer.get("from"), 0, 359999, 0),
                    "down": bool(timer.get("down")), "started": _num(timer.get("started"), 0, 1e11, 0)}
    return out


def timer_now(t, now=None):
    """The timer's seconds at a moment."""
    if not t["started"]:
        return t["secs"]
    run = (now or time.time()) - t["started"]
    return max(0.0, t["secs"] - run) if t["down"] else t["secs"] + run


def timer_running(t, now=None):
    """Running (a countdown that reached 0 has stopped)."""
    return bool(t["started"]) and not (t["down"] and timer_now(t, now) <= 0)


def timer_action(t, action, secs=None, down=None, now=None):
    """The timer after start / stop / toggle / reset / set (secs, and down: up or down)."""
    now = now or time.time()
    running = timer_running(t, now)
    t = dict(t, secs=round(timer_now(t, now), 3))
    if action == "toggle":
        action = "stop" if running else "start"
    if action == "start":
        if t["down"] and t["secs"] <= 0:
            t["secs"] = t["from"]   # (a countdown that ran out starts again)
        t["started"] = round(now, 3)
    elif action == "stop":
        t["started"] = 0
    elif action == "reset":
        t["secs"] = t["from"]
        t["started"] = round(now, 3) if running else 0
    elif action == "set":
        if down is not None:
            t["down"] = bool(down)
        if secs is not None:
            t["secs"] = t["from"] = _num(secs, 0, 359999, 0)
            t["started"] = round(now, 3) if running else 0
    else:
        raise ValueError("start, stop, toggle, reset or set")
    return t


def parse_secs(v):
    """Seconds from "m:ss", "h:mm:ss" or a number."""
    parts = str(v or "0").strip().split(":")
    try:
        n = [float(x or 0) for x in parts][-3:]
    except ValueError:
        raise ValueError("A time like 5:00 or 1:30:00")
    total = 0.0
    for x in n:
        total = total * 60 + x
    return total


def sponsors_changed(old, new):
    """The rotation starts again from the first sponsor when the list changes."""
    if [(s["logo"], s["secs"]) for s in old.get("sponsors", [])] != [(s["logo"], s["secs"]) for s in new["sponsors"]]:
        new["sponsor_epoch"] = round(time.time(), 3)
    return new


def sponsor_now(g, now=None):
    """(index of the sponsor showing, seconds it has left) at a moment, or (-1, 0)."""
    sp = g.get("sponsors") or []
    if not sp:
        return -1, 0
    total = sum(s["secs"] for s in sp)
    t = ((now or time.time()) - g.get("sponsor_epoch", 0)) % total
    for i, s in enumerate(sp):
        if t < s["secs"]:
            return i, s["secs"] - t
        t -= s["secs"]
    return len(sp) - 1, 0


def game_number(g):
    return g.get("game") or str(int(g["left"]["score"]) + int(g["right"]["score"]) + 1)


def rows(g):
    """The "Global" data source's table: label | value."""
    g = clean(g)
    out = [["Field", "Value"], ["Event", g["event"]], ["Stage", g["stage"]], ["Best of", str(g["best_of"])],
           ["Game", game_number(g)]]
    for side in ("left", "right"):
        t = g[side]
        S = side.title()
        out += [[f"{S} name", t["name"]], [f"{S} short", t["short"]], [f"{S} logo", t["logo"]],
                [f"{S} color", t["color"]], [f"{S} score", str(t["score"])], [f"{S} game", t["game"]]]
        # (the boxes for games won: "1" once the team has won n games)
        out += [[f"{S} won {n}", "1" if int(t["score"]) >= n else ""] for n in range(1, 5)]
    # (how many of those boxes a side shows: the games to win the series)
    out += [[f"Game box {n}", "1" if n <= (int(g["best_of"]) + 1) // 2 else ""] for n in range(1, 5)]
    loop = g["bgloop"]
    sp = g["sponsors"]
    out += [["Tournament logo", g["tournament_logo"]],
            ["Sponsor logo", sp[0]["logo"] if sp else ""], ["Sponsors", str(len(sp))],
            ["BG loop", (loop["src"] or DEFAULT_LOOP) if loop["on"] else ""], ["BG loop colour", loop["color"]],
            ["BG loop brightness", str(loop["brightness"])], ["BG loop speed", str(loop["speed"])],
            ["Ticker", TICKER_GAP.join(g["ticker"]) + (TICKER_GAP if g["ticker"] else "")],
            ["Clock mode", g["clock"]["mode"]], ["Clock until", g["clock"]["until"]], ["Clock zone", g["clock"]["zone"]],
            ["Clock label", CLOCK_LABELS[g["clock"]["mode"]]],
            ["Timer secs", str(g["timer"]["secs"])], ["Timer started", str(g["timer"]["started"])],
            ["Timer down", "1" if g["timer"]["down"] else ""]]
    c = g["caster"]
    moves = caster_moves(c["count"])
    out += [["Caster boxes", str(c["count"])], ["Caster primary", c["primary"]], ["Caster secondary", c["secondary"]]]
    for i in range(4):
        out += [[f"Caster {i + 1} shown", "1" if i < c["count"] else ""], [f"Caster {i + 1} move", moves[i] if i < c["count"] else ""]]
    out += [[k, v] for k, v in g["custom"]]
    return out


def sponsor_rows(g):
    """The "Sponsors" table the sponsor spots rotate through: logo | seconds | from (s) | white in rows."""
    g = clean(g)
    return [["Logo", "Seconds", "Epoch", "White"]] + [[s["logo"], str(s["secs"]), str(g["sponsor_epoch"]), "1" if s["white"] else ""]
                                                      for s in g["sponsors"]]
