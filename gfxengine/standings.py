"""The tournament standings: the teams the Standings graphics list (8 or 16),
each one's wins, losses, points and map difference, set on the Tournament
page and kept in the workspace's global configuration.

    {"title": "", "subtitle": "LEADERBOARD", "count": 8,
     "stat": "record", "stat2": "",
     "teams": [{"name", "w", "l", "pts", "diff"}, ...16]}

title: blank shows Global's event. stat / stat2: what the box (and a second
box beside it, "" for none) shows for each team: see STATS.

The "Standings" data table: {{Standings!Title}}, {{Standings!Subtitle}},
{{Standings!Stat 1 title}}, and for each team n: {{Standings!Team n}},
{{Standings!Team n logo}}, {{Standings!Team n stat 1}}, {{Standings!Team n stat 2}},
{{Standings!Team n shown}} (the row has a team), {{Standings!Team n record}}...
"""

COUNTS = (8, 16)
ROWS = 16
# What a box can show: key -> (its title over the column, in the Tournament page's list)
STATS = {"record": ("W-L", "Record (W-L)"), "wins": ("W", "Wins"), "losses": ("L", "Losses"),
         "points": ("PTS", "Points"), "winpct": ("WIN %", "Win %"), "diff": ("+/-", "Map difference (+/-)")}


def _num(v):
    v = str(v if v is not None else "").strip()[:6]
    try:
        float(v)
    except ValueError:
        return ""
    return v


def _team(t):
    t = t if isinstance(t, dict) else {}
    return {"name": str(t.get("name") or "").strip()[:120], "w": _num(t.get("w")), "l": _num(t.get("l")),
            "pts": _num(t.get("pts")), "diff": _num(t.get("diff"))}


def default():
    return {"title": "", "subtitle": "LEADERBOARD", "count": 8, "stat": "record", "stat2": "",
            "teams": [_team(None) for _ in range(ROWS)]}


def clean(s):
    s = s if isinstance(s, dict) else {}
    try:
        count = int(s.get("count") or 8)
    except (TypeError, ValueError):
        count = 8
    teams = [_team(t) for t in (s.get("teams") if isinstance(s.get("teams"), list) else [])][:ROWS]
    stat = s.get("stat") if s.get("stat") in STATS else "record"
    stat2 = s.get("stat2") if s.get("stat2") in STATS and s.get("stat2") != stat else ""
    return {"title": str(s.get("title") or "").strip()[:80],
            "subtitle": str(s.get("subtitle") if s.get("subtitle") is not None else "LEADERBOARD").strip()[:80],
            "count": count if count in COUNTS else 8, "stat": stat, "stat2": stat2,
            "teams": teams + [_team(None) for _ in range(ROWS - len(teams))]}


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def value(t, stat):
    """What a box shows for a team ("" while nothing's entered)."""
    w, l = t["w"], t["l"]
    if stat == "record":
        return f"{w or 0}-{l or 0}" if (w or l) else ""   # (spaced out on the graphic, like the design's 6-1)
    if stat == "wins":
        return w
    if stat == "losses":
        return l
    if stat == "points":
        return t["pts"]
    if stat == "diff":
        d = t["diff"]
        return ("+" + d.lstrip("+")) if d and float(d) > 0 else d
    if stat == "winpct":
        played = _int(w) + _int(l)
        return f"{round(100 * _int(w) / played)}%" if played else ""
    return ""


def sort_key(t):
    """Best first: most wins, fewest losses, most points, best difference."""
    f = lambda v: float(v) if v else 0.0
    return (-f(t["w"]), f(t["l"]), -f(t["pts"]), -f(t["diff"]))


def rows(s, find=None, event=""):
    """The "Standings" data table: label | value. find(name) -> a team from the team list."""
    s = clean(s)
    out = [["Field", "Value"], ["Title", s["title"] or event], ["Subtitle", s["subtitle"]], ["Teams", str(s["count"])],
           ["Stat 1 title", STATS[s["stat"]][0]], ["Stat 2 title", STATS[s["stat2"]][0] if s["stat2"] else ""],
           # (one box: the team's name has the room up to it; two: up to the second)
           ["Stat 2 shown", "1" if s["stat2"] else ""], ["One stat", "" if s["stat2"] else "1"],
           # (the titles over the boxes: needed unless it's just the record)
           ["Stat titles shown", "1" if s["stat2"] or s["stat"] != "record" else ""]]
    for n, t in enumerate(s["teams"][:s["count"]], 1):
        info = (find(t["name"]) if find and t["name"] else None) or {}
        out += [[f"Team {n}", t["name"]], [f"Team {n} short", info.get("short") or t["name"]],
                [f"Team {n} logo", info.get("logo", "")], [f"Team {n} shown", "1" if t["name"] else ""],
                [f"Team {n} stat 1", value(t, s["stat"])], [f"Team {n} stat 2", value(t, s["stat2"]) if s["stat2"] else ""],
                [f"Team {n} stat 2 shown", "1" if t["name"] and s["stat2"] else ""],
                [f"Team {n} wins", t["w"]], [f"Team {n} losses", t["l"]], [f"Team {n} points", t["pts"]],
                [f"Team {n} diff", value(t, "diff")], [f"Team {n} record", value(t, "record")]]
    return out
