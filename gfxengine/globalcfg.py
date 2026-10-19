"""Global configuration: the event's basics (the two teams, the series, the
event), set once per workspace and used by any graphic as the data source
"Global": {{Global!Left name}}, {{Global!Left logo}}, {{Global!Left score}}...
(a logo is a picture's path, so an image field can use it too).

Game HUDs connected to the engine keep the series score up to date, and can
take the team names, short names and logos from here.
"""

import copy

DEFAULT = {
    "event": "", "stage": "", "best_of": 3, "game": "",   # game: "" = from the score
    "left": {"name": "", "short": "", "logo": "", "color": "#0b6b3a", "score": 0},
    "right": {"name": "", "short": "", "logo": "", "color": "#b8191c", "score": 0},
    "custom": [],    # [[label, value], ...]
}
TEAM_KEYS = ("name", "short", "logo", "color", "score")


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
    return out


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
                [f"{S} color", t["color"]], [f"{S} score", str(t["score"])]]
    out += [[k, v] for k, v in g["custom"]]
    return out
