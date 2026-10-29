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
BASE = {"lol": ("kills", "deaths", "assists"), "valorant": ("kills", "deaths", "assists"), "rl": ("goals", "saves", "score"),
        "overwatch": ("kills", "deaths", "assists"), "cod": ("kills", "deaths", "assists")}
LAYOUT = {"lol": {"cols": ("kda", "cs", "dmg"), "rows": ("kda", "cs", "dmg", "gold")},
          "valorant": {"cols": ("acs", "kills", "deaths"), "rows": ("acs", "kills", "deaths", "assists")},
          "rl": {"cols": ("goals", "saves", "score"), "rows": ("goals", "saves", "assists", "score")},
          "overwatch": {"cols": ("dmg", "kills", "deaths"), "rows": ("dmg", "kills", "deaths", "healing")},
          "cod": {"cols": ("kda", "dmg", "kd"), "rows": ("kills", "deaths", "assists", "dmg")}}
NAMES = {"acs": "ACS", "kda": "K/D/A", "kd": "K/D", "cs": "CS", "vision": "VISION", "gold": "GOLD", "dmg": "DMG", "healing": "HEALING",
         "ntk": "NON-TRADED KILLS", "streak": "HIGHEST STREAK"}
TITLES = {g: tuple(k.upper() for k in keys) for g, keys in BASE.items()}
GAMES = {"lol": "League of Legends", "valorant": "VALORANT", "rl": "Rocket League", "cod": "Call of Duty",
         "smash": "Super Smash Bros. Ultimate", "overwatch": "Overwatch"}
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


# VALORANT agents with an icon in web/agents (named as the VALORANT HUD names them).
AGENTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web", "agents")


def _agent_icon(agent):
    agent = str(agent or "").strip()
    return f"agents/{agent}.png" if agent and os.path.isfile(os.path.join(AGENTS_DIR, agent + ".png")) else ""


def acs_estimate(k, a, rounds):
    """Average combat score, estimated: the spectator screen the HUD reads has
    no damage or ACS, so a kill counts ~200 (its damage and kill bonus) and an
    assist 25, over the rounds played."""
    return round((200 * k + 25 * a) / rounds) if rounds else 0


def _valorant(f):
    teams = {}
    rounds = _int(f.get("SCORE LEFT")) + _int(f.get("SCORE RIGHT"))
    for side in SIDES:
        S = side.upper()
        players = []
        for n in range(1, 6):
            k, d, a = (_int(f.get(f"{S} P{n} {x}")) for x in ("K", "D", "A"))
            acs = f.get(f"{S} P{n} ACS")   # (the HUD's own, if it ever reads it)
            players.append({"name": f.get(f"{S} P{n} NAME") or "", "character": f.get(f"{S} P{n} AGENT") or "",
                            "icon": _agent_icon(f.get(f"{S} P{n} AGENT")), "stats": [k, d, a],
                            "extra": f.get(f"{S} P{n} CREDITS", ""),
                            "values": {"acs": _int(acs) if str(acs or "") != "" else acs_estimate(k, a, rounds)}})
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


def _overwatch(f):
    # (typed in by hand on the Overwatch HUD's Stats page; the hero's picture is
    # an address on the HUD)
    teams = {}
    for side in SIDES:
        players = [{"name": f.get(f"{side}_p{n}_name") or "", "character": f.get(f"{side}_p{n}_hero") or "",
                    "icon": str(f.get(f"{side}_p{n}_hero_icon") or ""),
                    "stats": [_int(f.get(f"{side}_p{n}_{x}")) for x in ("kills", "deaths", "assists")],
                    "extra": "", "values": {"dmg": _int(f.get(f"{side}_p{n}_damage")),
                                            "healing": _int(f.get(f"{side}_p{n}_healing"))}}
                   for n in range(1, 6)]
        teams[side] = {"score": _int(f.get(f"{side}_score")), "players": players}
    return teams


def _cod(f):
    # (read off the end-of-game scoreboard by the CoD HUD: none until then, as
    # its player names come all game long)
    teams = {}
    for side in SIDES:
        players = [{"name": (f.get(f"{side}_p{n}_ign") or f.get(f"{side}_p{n}_name") or "") if f.get("postgame") else "",
                    "character": "", "stats": [_int(f.get(f"{side}_p{n}_{x}")) for x in ("kills", "deaths", "assists")],
                    "extra": "", "values": {"dmg": _int(f.get(f"{side}_p{n}_damage")), "ntk": _int(f.get(f"{side}_p{n}_ntk")),
                                            "streak": _int(f.get(f"{side}_p{n}_streak"))}}
                   for n in range(1, 6)]
        teams[side] = {"score": _int(f.get(f"{side}_wins")), "players": players}
    return teams


READERS = {"lol": _lol, "valorant": _valorant, "rl": _rl, "overwatch": _overwatch, "cod": _cod}


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
    return _gold(v) if key == "gold" else f"{v:,}" if key in ("dmg", "healing") else str(v)


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
    headshot), or None. pictures: {"team": {"left": "headshot" or "champion",
    "right": ...}, "player": {...}}, what Team stats and Player stats show for
    each team's players."""
    names = names or {}
    pictures = pictures or {}
    if "left" in pictures or "right" in pictures:   # (one setting for both pages)
        pictures = {"team": pictures, "player": pictures}
    team_pics, player_pics = pictures.get("team") or {}, pictures.get("player") or {}
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
        kills = sum(p["stats"][0] for p in players)
        out += [[f"{S} name", names.get(side, "")], [f"{S} score", str(team["score"])],
                # The big number by the team on Team stats: rounds won (VALORANT), else
                # the first stat (kills, goals). "Total kills" is always the kills.
                [f"{S} kills", str(team["score"] if game == "valorant" else kills)], [f"{S} total kills", str(kills)]]
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
            champ = team_pics.get(side) == "champion"
            out += [[f"{k} headshot", "" if champ else r.get("photo", "")], [f"{k} champion", p.get("icon", "") if champ and p["name"] else ""]]
            # Best: most of stat 1 (kills, goals), then stat 3, then fewest stat 2.
            # (the first Player stats row when it's a number, like ACS)
            first = v.get(lay["rows"][0])
            rank = ((first if isinstance(first, int) else p["stats"][0]), p["stats"][0], p["stats"][2], -p["stats"][1])
            if p["name"] and (best is None or rank > best[0]):
                best = (rank, side, p)
            if p["name"] and pick == f"{side} {n}":
                picked = (rank, side, p)
    best = picked or best
    if best:
        _, side, p = best
        r = (lookup(side, p["name"]) if lookup else None) or {}
        v = _values(game, p)
        champ = (champion_art(p.get("icon", "")) or p.get("icon", "")) if player_pics.get(side) == "champion" else ""
        out += [["MVP", p["name"]], ["MVP team", names.get(side, side.title())], ["MVP character", p["character"]],
                ["MVP picked", "manual" if picked else "auto"], ["MVP side", side],
                ["MVP name", r.get("name") or r.get("ign") or p["name"]], ["MVP ID", r.get("ign") or p["name"]],
                ["MVP country", r.get("country", "")], ["MVP flag", f"flags/{r['country']}.svg" if r.get("country") else ""],
                ["MVP headshot", "" if player_pics.get(side) == "champion" else r.get("photo", "")], ["MVP champion", champ],
                # (a player not in the roster: no one else's photo or flag)
                ["MVP headshot shown", "1" if r.get("photo") and player_pics.get(side) != "champion" else ""], ["MVP flag shown", "1" if r.get("country") else ""]]
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
        if not (fields or {}).get("stats_final"):   # (stats read after the game: FINAL already)
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
