"""The game's stats, the same way whatever the game: the "Stats" data source.

A connected game HUD sends its own fields (League: "P1 KDA", VALORANT:
"LEFT P1 K", Rocket League: "left_p1_goals"...). They're turned into one
table every stats graphic can use, whichever HUD is connected:

    {{Stats!Left player 1}}, {{Stats!Left player 1 stat 1}} ... stat 3,
    {{Stats!Stat 1 title}} (KILLS / GOALS...), {{Stats!Left stat 1}} (the
    team's total), {{Stats!MVP}}, {{Stats!MVP stat 1}}, {{Stats!Status}}
    (LIVE, or FINAL once the HUD stops sending)

The last game's stats are kept (in the workspace's stats.json) after the
game ends or the HUD disconnects, so the post-game graphics still have them,
until the next game starts or they're cleared.
"""

import json
import os
import threading
import time

SIDES = ("left", "right")
TITLES = {"lol": ("KILLS", "DEATHS", "ASSISTS"), "valorant": ("KILLS", "DEATHS", "ASSISTS"),
          "rl": ("GOALS", "SAVES", "SCORE")}
GAMES = {"lol": "League of Legends", "valorant": "VALORANT", "rl": "Rocket League", "cod": "Call of Duty"}
LIVE_FOR = 10   # seconds without news before the stats are FINAL


def _int(v):
    try:
        return int(float(str(v).strip() or 0))
    except (TypeError, ValueError):
        return 0


def _lol(f):
    teams = {}
    for i, side in enumerate(SIDES):
        players = []
        for n in range(1, 6):
            p = n + i * 5
            k, d, a = (str(f.get(f"P{p} KDA") or "").split("/") + ["", "", ""])[:3]
            players.append({"name": f.get(f"P{p} NAME") or "", "character": f.get(f"P{p} CHAMPION") or "",
                            "stats": [_int(k), _int(d), _int(a)], "extra": f.get(f"P{p} CS", "")})
        teams[side] = {"score": _int(f.get(f"KILLS {side.upper()}")), "players": players}
    return teams


def _valorant(f):
    teams = {}
    for side in SIDES:
        S = side.upper()
        players = [{"name": f.get(f"{S} P{n} NAME") or "", "character": f.get(f"{S} P{n} AGENT") or "",
                    "stats": [_int(f.get(f"{S} P{n} {x}")) for x in ("K", "D", "A")],
                    "extra": f.get(f"{S} P{n} CREDITS", "")} for n in range(1, 6)]
        teams[side] = {"score": _int(f.get(f"SCORE {S}")), "players": players}
    return teams


def _rl(f):
    teams = {}
    for side in SIDES:
        players = [{"name": f.get(f"{side}_p{n}_name") or "", "character": "",
                    "stats": [_int(f.get(f"{side}_p{n}_{x}")) for x in ("goals", "saves", "score")],
                    "extra": f.get(f"{side}_p{n}_assists", "")} for n in range(1, 5)]
        teams[side] = {"score": _int(f.get(f"{side}_goals")), "players": players}
    return teams


READERS = {"lol": _lol, "valorant": _valorant, "rl": _rl}


def read(game, fields):
    """A HUD's fields -> {"game", "titles", "left"/"right": {"score", "players"}}, or
    None if they have no players (no game going, or a HUD without player stats)."""
    reader = READERS.get(game)
    if not reader:
        return None
    teams = reader(fields or {})
    if not any(p["name"] for side in SIDES for p in teams[side]["players"]):
        return None
    return {"game": game, "titles": list(TITLES[game]), **teams}


def _kd(k, d):
    return f"{k / d:.2f}" if d else f"{k:.2f}" if k else "0.00"


def rows(stats, live, names=None):
    """The "Stats" table: label | value."""
    names = names or {}
    out = [["Field", "Value"]]
    if not stats:
        out += [["Status", ""], ["Game", ""]] + [[f"Stat {i} title", t] for i, t in enumerate(("KILLS", "DEATHS", "ASSISTS"), 1)]
        return out
    t = stats["titles"]
    out += [["Status", "LIVE" if live else "FINAL"], ["Game", GAMES.get(stats["game"], stats["game"])],
            ["From", stats.get("source", "")], ["Updated", time.strftime("%H:%M", time.localtime(stats.get("at", 0)))]]
    out += [[f"Stat {i + 1} title", t[i]] for i in range(3)]
    best = None
    for side in SIDES:
        S = side.title()
        team = stats[side]
        players = team["players"]
        out += [[f"{S} name", names.get(side, "")], [f"{S} score", str(team["score"])]]
        for i in range(3):
            out.append([f"{S} stat {i + 1}", str(sum(p["stats"][i] for p in players))])
        for n, p in enumerate(players, 1):
            k = f"{S} player {n}"
            out += [[k, p["name"]], [f"{k} character", p["character"]]]
            out += [[f"{k} stat {i + 1}", str(p["stats"][i]) if p["name"] else ""] for i in range(3)]
            out.append([f"{k} K/D", _kd(p["stats"][0], p["stats"][1]) if p["name"] else ""])
            # Best: most of stat 1 (kills, goals), then stat 3, then fewest stat 2.
            rank = (p["stats"][0], p["stats"][2], -p["stats"][1]) if stats["game"] != "rl" else (p["stats"][2], p["stats"][0])
            if p["name"] and (best is None or rank > best[0]):
                best = (rank, side, p)
    if best:
        _, side, p = best
        out += [["MVP", p["name"]], ["MVP team", names.get(side, side.title())], ["MVP character", p["character"]]]
        out += [[f"MVP stat {i + 1}", str(p["stats"][i])] for i in range(3)]
        out.append(["MVP K/D", _kd(p["stats"][0], p["stats"][1])])
    return out


class Stats:
    """The latest game's stats, kept on disk."""

    def __init__(self, folder):
        self.path = os.path.join(folder, "stats.json")
        self.lock = threading.Lock()
        self.data = None
        self.heard = 0.0      # when a HUD last sent stats
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except (OSError, ValueError):
            self.data = None

    def update(self, source, game, fields):
        """Returns True if the stats changed."""
        new = read(game, fields)
        if not new:
            return False
        self.heard = time.time()
        new["source"] = source
        with self.lock:
            old = self.data
            same = old and {k: v for k, v in old.items() if k != "at"} == new
            if same:
                return False
            new["at"] = time.time()
            self.data = new
            self._save()
        return True

    def clear(self):
        with self.lock:
            self.data = None
            self._save()

    def _save(self):
        if self.data is None:
            if os.path.exists(self.path):
                os.remove(self.path)
            return
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.data, f)
        os.replace(tmp, self.path)

    def live(self):
        return time.time() - self.heard < LIVE_FOR

    def rows(self, names=None):
        with self.lock:
            data = self.data
        return rows(data, self.live(), names)
