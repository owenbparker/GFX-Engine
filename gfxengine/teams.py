"""The team database every workspace shares: each team's name, short name,
logo, colour and game, and its roster (each player's name, in-game ID,
country and headshot), to fill a side of the global configuration, the
brackets and the player graphics from a list instead of typing it.

A school can have a team in several games: a team is its name and its game.

It's a CSV file (library/teams.csv: Name, Short name, Logo, Colour, Game,
then Player 1, Player 1 ID, Player 1 country, Player 1 headshot, Player 2...)
that can be edited in a spreadsheet too. Logos and headshots added in the
engine go in library/teams/; in the CSV, a picture can also be a web address
or the name of a file in that folder. A country is its two-letter code (de)
or its name (Germany); the flags come with the engine (web/flags/).
"""

import csv
import io
import json
import os
import re
import threading

from .config import WEB_DIR

COLUMNS = ("Name", "Short name", "Logo", "Colour", "Game")
PLAYER_COLUMNS = ("Player {n}", "Player {n} ID", "Player {n} country", "Player {n} headshot")
PLAYER_KEYS = ("name", "ign", "country", "photo")
MAX_PLAYERS = 10
# Column titles other spreadsheets use.
ALIASES = {"name": ("name", "team", "team name", "school"),
           "short": ("short name", "short", "abbreviation", "abbr", "tag", "code"),
           "logo": ("logo", "logo path", "image", "picture", "logo url"),
           "color": ("colour", "color", "team colour", "team color"),
           "game": ("game", "title", "esport", "division")}
PLAYER_ALIASES = {"name": ("", " name"), "ign": (" id", " ign", " in-game id", " gamertag", " tag"),
                  "country": (" country", " flag", " region", " country/region"),
                  "photo": (" headshot", " photo", " picture", " avatar")}
MAX = 1000
PICTURE = re.compile(r"^(https?:|assets/|library/|flags/)")


def countries():
    """[{"code", "name"}] of the flags that come with the engine."""
    try:
        with open(os.path.join(WEB_DIR, "flags", "countries.json"), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


_COUNTRIES = None


def country_code(v):
    """"de", "DE" or "Germany" -> "de" ("" if it isn't one)."""
    global _COUNTRIES
    if _COUNTRIES is None:
        _COUNTRIES = {}
        for c in countries():
            _COUNTRIES[c["code"]] = c["code"]
            _COUNTRIES[c["name"].lower()] = c["code"]
        _COUNTRIES.update({"usa": "us", "uk": "gb", "united states": "us", "england": "gb-eng",
                           "scotland": "gb-sct", "wales": "gb-wls", "korea": "kr", "south korea": "kr"})
    v = str(v or "").strip().lower()
    return _COUNTRIES.get(v, "")


def flag(code):
    return f"flags/{code}.svg" if code else ""


def _picture(p):
    p = str(p or "").strip()[:300]
    return p if not p or PICTURE.match(p) else "library/teams/" + os.path.basename(p)


def _player(p):
    p = p if isinstance(p, dict) else {}
    return {"name": str(p.get("name") or "").strip()[:80], "ign": str(p.get("ign") or "").strip()[:80],
            "country": country_code(p.get("country")), "photo": _picture(p.get("photo"))}


def game_name(g):
    """A game as the HUDs name it ("valorant", "LoL", "rl"... -> VALORANT, League of
    Legends, Rocket League); another game is kept as it's written."""
    from .stats import GAMES
    g = str(g or "").strip()[:60]
    low = g.lower()
    for code, name in GAMES.items():
        if low in (code, name.lower()):
            return name
    return {"league": GAMES["lol"], "cod": GAMES["cod"], "callofduty": GAMES["cod"], "rocketleague": GAMES["rl"],
            "val": GAMES["valorant"]}.get(low.replace(" ", ""), g)


def _clean(t):
    color = str(t.get("color") or "").strip()
    if color and not re.match(r"^#[0-9a-fA-F]{6}$", color):
        color = "#" + color if re.match(r"^[0-9a-fA-F]{6}$", color) else ""
    players = [_player(p) for p in (t.get("players") or [])][:MAX_PLAYERS]
    return {"name": str(t.get("name") or "").strip()[:120], "short": str(t.get("short") or "").strip()[:12],
            "logo": str(t.get("logo") or "").strip()[:300], "color": color,
            "game": game_name(t.get("game")),
            "players": [p for p in players if any(p.values())]}


def key(t):
    return (t["name"].lower(), t.get("game", "").lower())


class Teams:
    def __init__(self, library_dir):
        self.folder = os.path.join(library_dir, "teams")
        self.path = os.path.join(library_dir, "teams.csv")
        self.lock = threading.Lock()
        self.rev = 0
        self.teams = self._read()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8-sig", newline="") as f:
                return self.parse(f.read())
        except OSError:
            return []

    def parse(self, text):
        """CSV text -> teams (the columns found by their titles)."""
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        if not rows:
            return []
        head = [c.strip().lower() for c in rows[0]]
        cols = {k: next((head.index(a) for a in names if a in head), None) for k, names in ALIASES.items()}
        if cols["name"] is None:      # no titles: Name, Short name, Logo, Colour, Game
            cols = {"name": 0, "short": 1, "logo": 2, "color": 3, "game": 4}
            pcols = []
        else:
            rows = rows[1:]
            pcols = []
            for n in range(1, MAX_PLAYERS + 1):
                found = {k: next((head.index(f"player {n}{a}") for a in names if f"player {n}{a}" in head), None)
                         for k, names in PLAYER_ALIASES.items()}
                if any(i is not None for i in found.values()):
                    pcols.append(found)
        cell = lambda r, i: r[i] if i is not None and i < len(r) else ""
        out = []
        for r in rows:
            t = {k: cell(r, i) for k, i in cols.items()}
            t["players"] = [{k: cell(r, i) for k, i in pc.items()} for pc in pcols]
            t = _clean(t)
            if not t["name"]:
                continue
            t["logo"] = _picture(t["logo"])
            out.append(t)
        return out[:MAX]

    def csv_text(self, teams=None):
        teams = teams if teams is not None else self.teams
        n = max([5] + [len(t["players"]) for t in teams])
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(list(COLUMNS) + [c.format(n=i) for i in range(1, n + 1) for c in PLAYER_COLUMNS])
        for t in teams:
            row = [t["name"], t["short"], t["logo"], t["color"], t["game"]]
            for i in range(n):
                p = t["players"][i] if i < len(t["players"]) else {}
                row += [p.get(k, "") for k in PLAYER_KEYS]
            w.writerow(row)
        return buf.getvalue()

    def list(self):
        with self.lock:
            return [json.loads(json.dumps(t)) for t in self.teams]

    def save(self, teams):
        """The whole list (as edited in the Teams tab)."""
        clean = [_clean(t) for t in teams or [] if isinstance(t, dict)]
        clean = [t for t in clean if t["name"]][:MAX]
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(self.csv_text(clean))
            os.replace(tmp, self.path)
            self.teams = clean
            self.rev += 1
        return self.list()

    def merge(self, teams):
        """Adds teams, or updates the ones with the same name (and game). Returns how many."""
        current = self.list()
        index = {key(t): i for i, t in enumerate(current)}
        for t in teams:
            t = _clean(t)
            i = index.get(key(t))
            if i is None:
                index[key(t)] = len(current)
                current.append(t)
            else:
                current[i].update({k: v for k, v in t.items() if v})
        self.save(current)
        return len(teams)

    def import_csv(self, text):
        teams = self.parse(text)
        if not teams:
            raise ValueError("No teams in that file: it needs a Name column (and Short name, Logo, Colour, Game, Player 1...)")
        return self.merge(teams)

    def _store(self, base, filename, blob, kinds=(".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"), sub=""):
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in kinds:
            raise ValueError("The picture must be a PNG, JPG, WEBP, SVG or GIF")
        base = re.sub(r"[^\w\- ]+", "_", base).strip() or "team"
        folder = os.path.join(self.folder, sub) if sub else self.folder
        os.makedirs(folder, exist_ok=True)
        n, file = 2, base + ext
        while os.path.exists(os.path.join(folder, file)):
            file = f"{base} {n}{ext}"
            n += 1
        with open(os.path.join(folder, file), "wb") as f:
            f.write(blob)
        return "library/teams/" + (sub + "/" if sub else "") + file

    def save_logo(self, name, filename, blob, game=""):
        """A logo for a team (added to the list if it isn't there)."""
        name = str(name or "").strip()
        logo = self._store(name or os.path.splitext(os.path.basename(filename or ""))[0], filename, blob)
        if name:
            self.merge([{"name": name, "game": game, "logo": logo}])
        return logo

    def save_photo(self, name, filename, blob):
        """A player's headshot: where it's kept (the roster is saved with it by the Teams tab)."""
        return self._store(str(name or "").strip() or os.path.splitext(os.path.basename(filename or ""))[0],
                           filename, blob, sub="players")

    def find(self, name, game=None):
        """A team by its name (or short name), the one in that game first; or None."""
        n = str(name or "").strip().lower()
        if not n:
            return None
        g = str(game or "").strip().lower()
        with self.lock:
            named = [t for t in self.teams if t["name"].lower() == n] or \
                [t for t in self.teams if t["short"] and t["short"].lower() == n]
            hit = next((t for t in named if g and t["game"].lower() == g), None) or (named[0] if named else None)
            return json.loads(json.dumps(hit)) if hit else None

    def link(self, name, game, index, ign):
        """Saves an in-game ID to a team's player (the index in its roster); no
        other player in the team keeps it. Returns the team."""
        k = (str(name or "").strip().lower(), str(game or "").strip().lower())
        teams = self.list()
        team = next((t for t in teams if key(t) == k), None) or next((t for t in teams if key(t)[0] == k[0]), None)
        if not team or not 0 <= index < len(team["players"]):
            raise ValueError("That player isn't in the team's roster in GFX Engine")
        for i, p in enumerate(team["players"]):
            if i != index and ign_key(p["ign"]) == ign_key(ign):
                p["ign"] = ""
        team["players"][index]["ign"] = str(ign or "").strip()[:60]
        self.save(teams)
        return self.find(team["name"], team["game"])

    def games(self):
        return sorted({t["game"] for t in self.list() if t["game"]}, key=str.lower)

    def rows(self):
        """The "Teams" data table."""
        return [list(COLUMNS) + ["Players"]] + [[t["name"], t["short"], t["logo"], t["color"], t["game"], str(len(t["players"]))]
                                                for t in self.list()]


def ign_key(v):
    """An in-game ID as it's matched: any Riot tag ("Name#NA1") and case aside."""
    return str(v or "").split("#")[0].strip().lower()


def player_named(team, name):
    """The player in a team's roster whose In-game ID is the name the game
    reports, or None. (Their Player name is only how graphics show them.)"""
    n = ign_key(name)
    if not n:
        return None
    return next((p for p in (team or {}).get("players") or [] if ign_key(p["ign"]) == n), None)


def roster_rows(team, side, stats_names=None, slots=5):
    """The "Roster" data table: the team the player graphics show (a side's team
    from Global), each player's name (or in-game ID), ID, flag and headshot.
    A player missing from the roster takes their name from the game's stats."""
    team = team or {}
    players = team.get("players") or []
    stats_names = stats_names or []
    out = [["Field", "Value"], ["Side", side], ["Team", team.get("name", "")], ["Team short", team.get("short", "")],
           ["Team logo", team.get("logo", "")], ["Game", team.get("game", "")], ["Players", str(len(players))],
           ["No headshots", "" if any(p["photo"] for p in players) else "1"]]
    for i in range(max(slots, len(players))):
        p = players[i] if i < len(players) else {"name": "", "ign": "", "country": "", "photo": ""}
        shown = p["name"] or p["ign"] or (stats_names[i] if i < len(stats_names) else "")
        n = i + 1
        out += [[f"Player {n}", shown], [f"Player {n} name", p["name"]], [f"Player {n} ID", p["ign"]],
                [f"Player {n} country", p["country"]], [f"Player {n} flag", flag(p["country"])],
                [f"Player {n} headshot", p["photo"]]]
    return out
