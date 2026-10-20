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
    "roster": "left",    # whose players the player graphics show
}
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
    out["sponsors"] = [{"logo": str(sp.get("logo"))[:300], "secs": _num(sp.get("secs"), 1, 600, 10)}
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
    clock = dict(DEFAULT["clock"], **(g.get("clock") or {}))
    until = str(clock.get("until") or "").strip()
    out["clock"] = {"mode": clock.get("mode") if clock.get("mode") in CLOCK_LABELS else "time",
                    "until": until if re.match(r"^\d{1,2}:\d{2}$", until) else "",
                    "zone": str(clock.get("zone") or "")[:12]}
    return out


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
    loop = g["bgloop"]
    sp = g["sponsors"]
    out += [["Tournament logo", g["tournament_logo"]],
            ["Sponsor logo", sp[0]["logo"] if sp else ""], ["Sponsors", str(len(sp))],
            ["BG loop", (loop["src"] or DEFAULT_LOOP) if loop["on"] else ""], ["BG loop colour", loop["color"]],
            ["BG loop brightness", str(loop["brightness"])], ["BG loop speed", str(loop["speed"])],
            ["Ticker", TICKER_GAP.join(g["ticker"]) + (TICKER_GAP if g["ticker"] else "")],
            ["Clock mode", g["clock"]["mode"]], ["Clock until", g["clock"]["until"]], ["Clock zone", g["clock"]["zone"]],
            ["Clock label", CLOCK_LABELS[g["clock"]["mode"]]]]
    out += [[k, v] for k, v in g["custom"]]
    return out


def sponsor_rows(g):
    """The "Sponsors" table the sponsor spots rotate through: logo | seconds | from (s)."""
    g = clean(g)
    return [["Logo", "Seconds", "Epoch"]] + [[s["logo"], str(s["secs"]), str(g["sponsor_epoch"])] for s in g["sponsors"]]
