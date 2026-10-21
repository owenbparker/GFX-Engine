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
import re
import threading
import time

SIDES = ("left", "right")
# Each game's own numbers for every player (League: CS, vision, gold...), and
# which of them the stats pages show: the Team stats columns ("Stat 1"... 3)
# and the Player stats rows ("Row 1"... 4). "kda" is K/D/A (3/1/7), "kd" the
# kills per death.
BASE = {"lol": ("kills", "deaths", "assists"), "valorant": ("kills", "deaths", "assists"), "rl": ("goals", "saves", "score")}
LAYOUT = {"lol": {"cols": ("kda", "cs", "dmg"), "rows": ("kda", "cs", "dmg", "gold")},
          "valorant": {"cols": ("kills", "deaths", "assists"), "rows": ("kills", "deaths", "kd", "assists")},
          "rl": {"cols": ("goals", "saves", "score"), "rows": ("goals", "saves", "assists", "score")}}
NAMES = {"kda": "K/D/A", "kd": "K/D", "cs": "CS", "vision": "VISION", "gold": "GOLD", "dmg": "DMG"}
TITLES = {g: tuple(k.upper() for k in keys) for g, keys in BASE.items()}
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
                            "icon": str(f.get(f"P{p} CHAMPION ICON") or ""),
                            "stats": [_int(k), _int(d), _int(a)], "extra": f.get(f"P{p} CS", ""),
                            "values": {"cs": _int(f.get(f"P{p} CS")), "vision": _int(f.get(f"P{p} VISION")),
                                       "gold": _int(f.get(f"P{p} GOLD RAW")),
                                       # (damage: only once the game is over, from the League client)
                                       "dmg": _int(f.get(f"P{p} DMG")) if str(f.get(f"P{p} DMG") or "") != "" else None}})
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
        # (the in-game name; "_name" can be one the HUD shows instead)
        players = [{"name": f.get(f"{side}_p{n}_ign") or f.get(f"{side}_p{n}_name") or "", "character": "",
                    "stats": [_int(f.get(f"{side}_p{n}_{x}")) for x in ("goals", "saves", "score")],
                    "extra": f.get(f"{side}_p{n}_assists", ""), "values": {"assists": _int(f.get(f"{side}_p{n}_assists"))}}
                   for n in range(1, 5)]
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


def _gold(g):
    return f"{g / 1000:.1f}K" if g else "0"


def _values(game, p):
    """A player's numbers by name: the three every game has, and the game's own."""
    v = dict(zip(BASE.get(game, ("kills", "deaths", "assists")), p["stats"]), **(p.get("values") or {}))
    if game == "lol" and "values" not in p:   # (kept by the version before: its CS was the "extra")
        v.update(cs=_int(p.get("extra")), dmg=None)
    k, d, a = p["stats"]
    v.update(kda=f"{k}/{d}/{a}", kd=_kd(k, d))
    return v


def _show(key, v):
    if v is None or (key == "dmg" and v == ""):
        return "–"     # (not reported: damage during the game, or stats kept from an older version)
    if not isinstance(v, int):
        return str(v)
    return _gold(v) if key == "gold" else f"{v:,}" if key == "dmg" else str(v)


def _total(key, players, game):
    vals = [_values(game, p) for p in players if p["name"]]
    if key == "kda":
        return "/".join(str(sum(p["stats"][i] for p in players)) for i in range(3))
    if key == "kd":
        return _kd(sum(p["stats"][0] for p in players), sum(p["stats"][1] for p in players))
    if vals and all(x.get(key) is None for x in vals):
        return _show(key, None)
    return _show(key, sum(int(x.get(key) or 0) for x in vals))


# A League champion's small square icon (Data Dragon) -> its big square art (380x380).
ICON = re.compile(r"^(https?://[^/]+)/cdn/[^/]+/img/champion/([^/.]+)\.png$")


def champion_art(icon):
    m = ICON.match(icon or "")
    return f"{m.group(1)}/cdn/img/champion/tiles/{m.group(2)}_0.jpg" if m else ""


def _title(key):
    return NAMES.get(key, key.upper())


def rows(stats, live, names=None, pick="auto", lookup=None, pictures=None):
    """The "Stats" table: label | value.

    The Team stats columns are "Stat 1"... 3 and the Player stats rows "Row 1"
    ... 4, each game's own (League: K/D/A, CS, DMG, GOLD). The MVP (the
    player the Player stats page shows) is the one with the most of the first
    stat (kills, goals), or the one picked ("left 3"). lookup(side, in-game
    name) -> that player in the team's roster (for their name, flag and
    headshot), or None. pictures: {"left": "headshot" or "champion", "right": ...},
    what the stats pages show for each team's players."""
    names = names or {}
    pictures = pictures or {}
    out = [["Field", "Value"]]
    if not stats:
        out += [["Status", ""], ["Game", ""]] + [[f"Stat {i} title", t] for i, t in enumerate(("KILLS", "DEATHS", "ASSISTS"), 1)]
        out += [[f"Row {i} title", t] for i, t in enumerate(("KILLS", "DEATHS", "K/D", "ASSISTS"), 1)]
        out += [["Left kills", "0"], ["Right kills", "0"]]
        # (no game yet: the design's own photo and flag)
        return out + [["MVP headshot shown", "1"], ["MVP flag shown", "1"]]
    game = stats["game"]
    lay = LAYOUT.get(game, LAYOUT["valorant"])
    out += [["Status", "LIVE" if live else "FINAL"], ["Game", GAMES.get(game, game)],
            ["From", stats.get("source", "")], ["Updated", time.strftime("%H:%M", time.localtime(stats.get("at", 0)))]]
    out += [[f"Stat {i + 1} title", _title(k)] for i, k in enumerate(lay["cols"])]
    out += [[f"Row {i + 1} title", _title(k)] for i, k in enumerate(lay["rows"])]
    best = picked = None
    for side in SIDES:
        S = side.title()
        team = stats[side]
        players = team["players"]
        out += [[f"{S} name", names.get(side, "")], [f"{S} score", str(team["score"])],
                # (the first stat: kills, goals)
                [f"{S} kills", str(sum(p["stats"][0] for p in players))]]
        out += [[f"{S} stat {i + 1}", _total(k, players, game)] for i, k in enumerate(lay["cols"])]
        for n, p in enumerate(players, 1):
            k = f"{S} player {n}"
            v = _values(game, p)
            # (linked to the roster by in-game ID: shown by their Player name)
            r = (lookup(side, p["name"]) if lookup and p["name"] else None) or {}
            out += [[k, r.get("name") or p["name"]], [f"{k} ID", p["name"]], [f"{k} character", p["character"]]]
            out += [[f"{k} stat {i + 1}", _show(c, v.get(c, "")) if p["name"] else ""] for i, c in enumerate(lay["cols"])]
            out.append([f"{k} K/D", v["kd"] if p["name"] else ""])
            # Their picture: their headshot (from the roster) or their champion, as Control says.
            champ = pictures.get(side) == "champion"
            out += [[f"{k} headshot", "" if champ else r.get("photo", "")], [f"{k} champion", p.get("icon", "") if champ and p["name"] else ""]]
            # Best: most of stat 1 (kills, goals), then stat 3, then fewest stat 2.
            rank = (p["stats"][0], p["stats"][2], -p["stats"][1])
            if p["name"] and (best is None or rank > best[0]):
                best = (rank, side, p)
            if p["name"] and pick == f"{side} {n}":
                picked = (rank, side, p)
    best = picked or best
    if best:
        _, side, p = best
        r = (lookup(side, p["name"]) if lookup else None) or {}
        v = _values(game, p)
        champ = champion_art(p.get("icon", "")) if pictures.get(side) == "champion" else ""
        out += [["MVP", p["name"]], ["MVP team", names.get(side, side.title())], ["MVP character", p["character"]],
                ["MVP picked", "manual" if picked else "auto"], ["MVP side", side],
                ["MVP name", r.get("name") or r.get("ign") or p["name"]], ["MVP ID", r.get("ign") or p["name"]],
                ["MVP country", r.get("country", "")], ["MVP flag", f"flags/{r['country']}.svg" if r.get("country") else ""],
                ["MVP headshot", "" if pictures.get(side) == "champion" else r.get("photo", "")], ["MVP champion", champ],
                # (a player not in the roster: no one else's photo or flag)
                ["MVP headshot shown", "1" if r.get("photo") and pictures.get(side) != "champion" else ""], ["MVP flag shown", "1" if r.get("country") else ""]]
        out += [[f"MVP stat {i + 1}", _show(c, v.get(c, ""))] for i, c in enumerate(lay["cols"])]
        out += [[f"MVP row {i + 1}", _show(c, v.get(c, ""))] for i, c in enumerate(lay["rows"])]
        out.append(["MVP K/D", v["kd"]])
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

    def rows(self, names=None, pick="auto", lookup=None, pictures=None):
        with self.lock:
            data = self.data
        return rows(data, self.live(), names, pick, lookup, pictures)
