"""The finishing touches on the SCC graphics (starter/), after their PSDs are
imported: what they take from the global configuration and the game's
stats, the background loop behind the full-screen boards, and the text the
importer can't place exactly.

    python tools/scc_pack.py        # applies them to starter/ as it is now

make_starter.py runs this too after importing the PSDs. Each time starter/
changes, the graphics' previous signatures go into "pack_history", so
workspaces that still have an untouched older copy get the new one (see
gfxengine/pack.py).
"""

import json
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gfxengine import export  # noqa: E402
from gfxengine.pack import signature  # noqa: E402
from gfxengine.project import new_id  # noqa: E402

STARTER = os.path.join(ROOT, "starter")

# Boards that fill the screen: the background loop plays over their backdrop.
LOOP_BOARDS = ("Schedule", "Team stats", "Player stats", "Group bracket", "Top 8 bracket", "Final four",
               *(f"Player graphic ({n})" for n in range(1, 6)))
# What each graphic is: one board and one lower third can be on air at a time.
KINDS = {"lower third": ("Caster lower third",),
         "overlay": ("Scorebug & footer", "Replay overlay")}
TICKER = ["WELCOME TO ST. CLAIR SAINTS ESPORTS", "FOLLOW @SCCSAINTS FOR HIGHLIGHTS", "THANKS FOR WATCHING!"]
# The upcoming matches a new workspace starts with (the design's own).
SCHEDULE = {"count": 3, "matches": [
    {"tournament": "NACE VARSITY", "game": "ROCKET LEAGUE", "type": "PLAYOFFS", "team1": "George Mason University",
     "team2": "St. Clair College", "date": "2026-11-11", "time": "19:30"},
    {"tournament": "NACE VARSITY", "game": "PREMIER LEAGUE OF LEGENDS", "type": "SEMI-FINALS", "team1": "Maryville University",
     "team2": "St. Clair College", "date": "2026-11-19", "time": "20:00"},
    {"tournament": "CANADIAN ESPORTS NATIONALS", "game": "VALORANT", "type": "", "team1": "Université de Montréal",
     "team2": "St. Clair College", "date": "2026-11-25", "time": "20:30"}]}
# The ticker's lines are kept apart by a bar in this colour.
DIVIDER = "#ffc52a"
BRACKETS = ("Group bracket", "Top 8 bracket", "Final four")
# The knockout bracket's own drawing replaces the design's 8 slots and lines.
TOP8_PARTS = ("Position ", "Vector Smart Object", "Line 3", "Rectangle 3", "Rectangle 4")
# Picture layers -> what they show from Global (the design's own stays as the
# picture shown while Global has none).
PICTURES = {
    "Scorebug & footer": {"TEAM LEFT": "{{Global!Left logo}}", "TEAM RIGHT": "{{Global!Right logo}}",
                          "SPONSOR REPLACE": "{{Sponsors}}"},
    "Schedule": {"REPLACE WITH SPONSORS": "{{Sponsors}}"},
    "Team stats": {"SCS_COLOUR": "{{Global!Left logo}}", "Triangle 1": "{{Global!Right logo}}"},
    "*": {"Replace With Tournament Logo": "{{Global!Tournament logo}}",
          "Tournament Logo Replace Me": "{{Global!Tournament logo}}", "Replace with Logo": "{{Global!Tournament logo}}",
          "Replace Me With Tourney": "{{Global!Tournament logo}}", "TOURNAMENT LOGO, REPLACE ME": "{{Global!Tournament logo}}"},
}
# The sponsors a new workspace starts with (in starter/assets/sponsors/), and
# which set they are: a workspace still on an older set gets this one.
SPONSORS = ["Alienware logo.png", "SCC Alumni logo.png", "Tim Hortons logo.png", "SRC logo.png", "Subway logo.png",
            "Intel logo.png", "Prefire logo.png", "Pulsar logo.png"]
SPONSOR_SET = 2
# (a crest that's a filled circle: in its colours in the rows, not a white disc)
IN_COLOUR = ("SCC Alumni logo.png",)
# Graphics taken out of the pack (a workspace's untouched copies go too).
REMOVED = ("Title screen", "Starting soon", "Team graphic", "Sponsor footer")
# The design's row of sponsor logos at the foot of a graphic: one "every
# sponsor" layer takes its place.
STRIP_PARTS = ("Vector Smart Object", "Alienware-Logo-700x394")
# Text placed by hand from the PSDs' renders, where the importer's guess was off:
# (graphic, layer name, nth with that name) -> x, w, size, align, baseline (from the top of the canvas).
PLACED = {
    ("Team stats", "SsssssssssG", 0): dict(x=297, w=520, size=80, align="left", base=390),
    ("Team stats", "XssssssssX", 0): dict(x=1110, w=520, size=80, align="right", base=390),
    ("Team stats", "0", 0): dict(x=837, w=120, size=86, align="center", base=392),
    ("Team stats", "0", 1): dict(x=965, w=120, size=86, align="center", base=392),
    ("Schedule", "0", 0): dict(x=676, w=120, size=90, align="center", base=943),
    ("Schedule", "0", 1): dict(x=810, w=120, size=90, align="center", base=943),
}


def _text(comp, name, nth=0):
    found = [l for l in comp["layers"] if l["type"] == "text" and l["name"] == name]
    found.sort(key=lambda l: l["x"])
    return found[nth] if nth < len(found) else None


def _rows(layers, xs):
    """Text layers in a table: [row][column], by position."""
    rows = {}
    for l in layers:
        rows.setdefault(round(l["y"] / 20), []).append(l)
    out = []
    for key in sorted(rows):
        out.append(sorted(rows[key], key=lambda l: l["x"]))
    return out


# Each schedule card's lines: (size, baseline from the card's top), for the
# big first card and the two smaller ones.
CARD_TEXT = {True: {"tournament": (24, 36), "game": (15, 58), "teams": (20, 86), "when": (19, 114)},
             False: {"tournament": (20, 30), "game": (13, 49), "teams": (17, 72), "when": (16, 96)}}


def players(pg, n):
    """A player graphic with n players: from the team the player graphics show
    (the roster in the team list), each one's headshot standing over their
    name, with their flag before it. While the roster has no headshots the
    design's own photo shows."""
    names = sorted([l for l in pg["layers"] if l["type"] == "text" and l["name"] != "GAME NAME"], key=lambda l: l["x"])
    for i, l in enumerate(names, 1):
        l["text"] = f"{{{{Roster!Player {i}}}}}"
        l["icon"] = f"{{{{Roster!Player {i} flag}}}}"
    photo = max((l for l in pg["layers"] if l["type"] == "image" and l["y"] < 900 and l.get("show") in (None, "{{Roster!No headshots}}")
                 and not l["src"].startswith("{{") and l["w"] > 1000), key=lambda l: l["w"] * l["h"], default=None)
    if not photo or any(l["name"].startswith("Headshot") for l in pg["layers"]):
        return
    photo["show"] = "{{Roster!No headshots}}"
    col = 1920 / n
    w, h = (1100, 840) if n == 1 else (min(col * 1.3, 900), 760 if n < 5 else 700)
    at = pg["layers"].index(photo) + 1
    for i in range(n, 0, -1):
        cx = col * (i - 0.5)
        pg["layers"].insert(at, {
            "id": new_id("l"), "name": f"Headshot {i}", "type": "image", "x": round(cx - w / 2), "y": 919 - h, "w": round(w), "h": h,
            "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
            "anim": json.loads(json.dumps(photo.get("anim") or {})),
            "src": f"{{{{Roster!Player {i} headshot}}}}", "fit": "contain", "position": "bottom", "loop": True,
            "show": f"{{{{Roster!Player {i} headshot}}}}"})


def casters(comps):
    """The caster lower third: 1 to 4 boxes (Global's "Caster boxes"), side by
    side along the bottom, each with its caster's name and handle, in Global's
    primary (box) and secondary (text, edge and shadow) colours."""
    c = comps.get("Caster lower third")
    if not c or any(l.get("move") for l in c["layers"]):
        return
    x, y = 619, 451     # (the design's box: globalcfg.CASTER_BOX)
    names = {"Layer 1": ("Box", "primary"), "Layer 2": ("Box edge", "secondary"), "Layer 3": ("Box shadow", "secondary")}
    group = []
    for l in c["layers"]:
        if l["type"] == "image" and l["name"] in names:
            l["name"], tone = names[l["name"]]
            l["recolor"] = f"{{{{Global!Caster {tone}}}}}"
        elif l["type"] == "text":
            big = l["size"] > 40
            l.update(name="Caster" if big else "Caster handle", field="Caster" if big else "Caster handle",
                     text="CASTER NAME" if big else "@HANDLE", color="{{Global!Caster secondary}}")
        group.append(l)
    # (Control lists fields top layer first: Caster 1, its handle, then Caster 2...)
    group.sort(key=lambda l: {"Caster": 4, "Caster handle": 3}.get(l["name"], 0))
    layers = []
    for i in range(4, 0, -1):
        for l in group:
            n = json.loads(json.dumps(l))
            if i > 1:
                n["id"] = new_id("l")
            n["name"] = l["name"].replace("Caster", f"Caster {i}").replace("Box", f"Box {i}")
            if n.get("field"):
                n["field"] = n["name"]
            n.update(origin=[x, y], move=f"{{{{Global!Caster {i} move}}}}", show=f"{{{{Global!Caster {i} shown}}}}")
            layers.append(n)
    c["layers"] = layers


def pictures(comps):
    """Each player's picture on the stats pages, as Control picks for each team:
    their headshot (Team stats: its top third, the face) or their champion."""
    ts = comps.get("Team stats")
    if ts and not any(l["name"].startswith("Player 1 picture") for l in ts["layers"]):
        at = next(i for i, l in enumerate(ts["layers"]) if l["type"] == "text")
        new = []
        for side, x in (("Left", 113), ("Right", 1013)):
            for n in range(1, 6):
                y = 533 + 85 * (n - 1)   # (the design's rows)
                for kind in ("headshot", "champion"):
                    src = f"{{{{Stats!{side} player {n} {kind}}}}}"
                    new.append({"id": new_id("l"), "name": f"Player {n} {'picture' if kind == 'headshot' else 'champion'} - {side[0]}",
                                "type": "image", "x": x, "y": y, "w": 144, "h": 85, "opacity": 1, "rotation": 0, "visible": True,
                                "blend": "normal", "field": "", "anim": {"in": {"type": "fade", "dur": 400, "delay": 150 + 40 * n},
                                                                          "out": {"type": "fade", "dur": 250, "delay": 0}},
                                "src": src, "show": src, "fit": "cover", "loop": True, **({"topThird": True} if kind == "headshot" else {})})
        ts["layers"][at:at] = new
    ps = comps.get("Player stats")
    if ps and not any(l["name"] == "Champion Image" for l in ps["layers"]):
        photo = next((l for l in ps["layers"] if l["name"] == "Player Image"), None)
        if photo:
            ps["layers"].insert(ps["layers"].index(photo) + 1, {
                "id": new_id("l"), "name": "Champion Image", "type": "image", "x": 165, "y": 301, "w": 582, "h": 582,
                "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
                "anim": json.loads(json.dumps(photo.get("anim") or {})), "src": "{{Stats!MVP champion}}",
                "show": "{{Stats!MVP champion}}", "fit": "cover", "position": "top", "loop": True})


def schedule(comps):
    """The Schedule: its three match cards from the Upcoming Schedule (shown as
    many as it's set to), and the teams' logos in front of their names."""
    sch = comps.get("Schedule")
    if not sch:
        return
    cards = ((195, 328), (328, 438), (438, 560))
    tops = (199, 330, 440)
    fields = {"tournament": ("NACE VARSITY", "CANADIAN ESPORTS NATIONALS"),
              "game": ("ROCKET LEAGUE | PLAYOFFS", "Premier League of Legends | Semi-Finals", "VALORANT"),
              "teams": ("vs.",), "when": ("|",)}
    for n, (lo, bottom) in enumerate(cards, 1):
        top = tops[n - 1]
        for l in sch["layers"]:
            if l["x"] < 1400 or not (lo <= l["y"] < bottom) or l["name"] == "SCHEDULE":
                continue
            l["show"] = f"{{{{Schedule!Match {n} show}}}}"
            if l["type"] != "text":
                continue
            linked = re.match(r"^\{\{Schedule!Match \d (\w+)\}\}$", l["text"])
            if linked:
                key = linked.group(1)
            elif l["text"] in fields["game"]:
                key = "game"
            elif l["text"] in fields["tournament"]:
                key = "tournament"
            elif " vs. " in l["text"]:
                key = "teams"
            elif "|" in l["text"]:
                key = "when"
            else:
                continue
            l["text"] = f"{{{{Schedule!Match {n} {key}}}}}"
            l["fit"] = "shrink"
            l["field"] = ""
            # Sized to read: the teams and the date and time bigger than the design's.
            size, base = CARD_TEXT[n == 1][key]
            card_w = {1: 420, 2: 378, 3: 356}[n]
            l.update(x=1437, w=card_w, size=size, baseline=round(size * 0.86, 1), y=round(top + base - size * 0.86),
                     h=round(size * 1.3), valign="top", lineHeight=1.15, fit="squeeze" if key in ("teams", "when") else "shrink")
    # The clock: the time (or a countdown) and under it, in yellow, what it is.
    clock = next((l for l in sch["layers"] if l["type"] == "text" and "{{time}}" in l.get("text", "")), None)
    if clock:
        label = json.loads(json.dumps(clock))
        clock.update(name="Clock", text="{{clock}}", field="", y=879, h=40, size=28, baseline=24.1, lineHeight=1.15)
        label.update(id=new_id("l"), name="Clock label", text="{{Global!Clock label}}", field="", color=DIVIDER,
                     y=917, h=34, w=220, size=22, baseline=round(22 * 0.86, 1), lineHeight=1.15, fit="shrink")
        sch["layers"].insert(sch["layers"].index(clock) + 1, label)
    # The teams' logos in the score bar, in front of their short names.
    left, right = _text(sch, "SG"), _text(sch, "GMU")
    if left and right and not any(l["name"] == "Left logo" for l in sch["layers"]):
        left.update(x=422, w=200)
        right.update(x=930, w=240, align="right")
        at = sch["layers"].index(left)
        for name, x, side in (("Left logo", 326, "Left"), ("Right logo", 1192, "Right")):
            sch["layers"].insert(at, {
                "id": new_id("l"), "name": name, "type": "image", "x": x, "y": 869, "w": 80, "h": 80,
                "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
                "anim": json.loads(json.dumps(left.get("anim") or {})),
                "src": f"{{{{Global!{side} logo}}}}", "fit": "contain", "loop": True})


def link(data, starter=STARTER):
    comps = {c["name"]: c for c in data["compositions"]}

    # Text sits on the baseline the PSD gave it (the importer puts the top of
    # the box 0.86 of the size above it), whatever the font.
    for comp in data["compositions"]:
        for l in comp["layers"]:
            if l["type"] == "text" and not l.get("scroll") and "baseline" not in l:
                l["baseline"] = round(l["size"] * 0.86, 1)
    for (cname, lname, nth), p in PLACED.items():
        l = _text(comps[cname], lname, nth) if cname in comps else None
        if l:
            l.update(x=p["x"], w=p["w"], size=p["size"], align=p["align"], baseline=round(p["size"] * 0.86, 1),
                     y=round(p["base"] - p["size"] * 0.86), h=round(p["size"] * 1.4), fit="shrink")

    # Column titles centred over their columns (the stats' titles vary by game).
    if "Team stats" in comps:
        ts = comps["Team stats"]
        cells = [l for l in ts["layers"] if l["type"] == "text" and l["name"] == "000"]
        for l in ts["layers"]:
            if l["type"] == "text" and l["name"] in ("KILLS", "DEATHS", "ADR") and l["align"] == "left":
                col = min(cells, key=lambda c: abs(c["x"] + c["w"] / 2 - (l["x"] + l["w"] / 2)))
                cx = col["x"] + col["w"] / 2
                l.update(x=round(cx - 80), w=160, align="center")
    # The player's team, from a tiny box at the edge (a text box the importer
    # misread) to under the player's name.
    if "Player stats" in comps:
        l = _text(comps["Player stats"], "TEAM NAME")
        name = _text(comps["Player stats"], "PLAYER NAME")
        if l and name and l["w"] < 100:
            l.update(x=name["x"], w=560, align="left", y=name["y"] + round(name["size"] * 1.15), h=42)
    # The scorebug's clock, like the Schedule's: the time of day, or a countdown
    # for Starting Soon or Be Right Back (Global's), in the design's place.
    if "Scorebug & footer" in comps:
        for lname, value in (("00:03:1411111", "{{clock}}"), ("STARTING SOONnnnn", "{{Global!Clock label}}")):
            l = _text(comps["Scorebug & footer"], lname)
            if l:
                l.update(text=value, field="")
    if "Replay overlay" in comps:
        l = _text(comps["Replay overlay"], "ST. CLAIR SAINTS")
        if l and l["w"] < 100:
            l["visible"] = False

    # Pictures from Global.
    for comp in data["compositions"]:
        links = dict(PICTURES["*"], **PICTURES.get(comp["name"], {}))
        for l in comp["layers"]:
            if l["type"] == "image" and l["name"] in links and not l["src"].startswith("{{"):
                l["placeholder"] = l["src"]
                l["src"] = links[l["name"]]
                l["fit"] = "contain"

    # The team logos in Team stats: centred in their boxes, as big as they fit.
    if "Team stats" in comps:
        for l in comps["Team stats"]["layers"]:
            if l["type"] == "image" and l["src"] in ("{{Global!Left logo}}", "{{Global!Right logo}}"):
                l.update(x=124 if "Left" in l["src"] else 1667, y=304, w=131, h=111)

    def text(cname, lname, value, nth=0):
        l = _text(comps[cname], lname, nth)
        if l:
            l["text"] = value

    # Scores, event and teams from Global.
    if "Team stats" in comps:
        text("Team stats", "SsssssssssG", "{{Global!Left name}}")
        text("Team stats", "XssssssssX", "{{Global!Right name}}")
        # (each team's kills in the game: goals in Rocket League)
        text("Team stats", "0", "{{Stats!Left kills}}", 0)
        text("Team stats", "0", "{{Stats!Right kills}}", 1)
        for nth in (0, 1):   # (two digits, not spaced out like the design's one)
            if _text(comps["Team stats"], "0", nth):
                _text(comps["Team stats"], "0", nth)["tracking"] = 0
        text("Team stats", "NACE VARSITY", "{{Global!Event}}")
        text("Team stats", "OVERWATCH | PLAYOFFS", "{{Global!Game title}}")
        ts = comps["Team stats"]
        for side, (lo, hi) in (("Left", (0, 960)), ("Right", (960, 1920))):
            heads = sorted([l for l in ts["layers"] if l["type"] == "text" and l["name"] in ("KILLS", "DEATHS", "ADR")
                            and lo <= l["x"] < hi], key=lambda l: l["x"])
            for i, l in enumerate(heads, 1):
                l["text"] = f"{{{{Stats!Stat {i} title}}}}"
            for n in range(1, 6):
                l = _text(ts, f"Player {n} - {side[0]}")
                if l:
                    l["text"] = f"{{{{Stats!{side} player {n}}}}}"
            cells = [l for l in ts["layers"] if l["type"] == "text" and l["name"] == "000" and lo <= l["x"] < hi]
            for n, row in enumerate(_rows(cells, None), 1):
                for i, l in enumerate(row, 1):
                    l["text"] = f"{{{{Stats!{side} player {n} stat {i}}}}}"
                    if i == 1 and l["w"] < 120:   # (room for League's K/D/A: 12/3/15)
                        l.update(x=round(l["x"] + l["w"] / 2 - 60), w=120)
    if "Schedule" in comps:
        text("Schedule", "0", "{{Global!Left score}}", 0)
        text("Schedule", "0", "{{Global!Right score}}", 1)
        sch = comps["Schedule"]
        bottom = [l for l in sch["layers"] if l["type"] == "text" and l["y"] > 840]
        for l in bottom:
            if l["name"] == "NACE VARSITY":
                l["text"] = "{{Global!Event}}"
            elif l["name"] == "ROCKET LEAGUE | PLAYOFFS":
                l["text"] = "{{Global!Game title}}"
    if "Player stats" in comps:
        ps = comps["Player stats"]
        text("Player stats", "PLAYER NAME", "{{Stats!MVP name}}")
        # The player's headshot and flag from their team's roster (the design's
        # own until a game is played; none for a player missing from the roster).
        for l in ps["layers"]:
            if l["type"] == "image" and l["name"] in ("Player Image", "FLAG") and not l["src"].startswith("{{"):
                head = l["name"] == "Player Image"
                l.update(placeholder=l["src"], src="{{Stats!MVP headshot}}" if head else "{{Stats!MVP flag}}",
                         show="{{Stats!MVP headshot shown}}" if head else "{{Stats!MVP flag shown}}",
                         fit="contain", position="bottom" if head else "left")
        text("Player stats", "TEAM NAME", "{{Stats!MVP team}}")
        text("Player stats", "GAME", "{{Global!Game title}}")
        # Its four rows: the game's own (League: K/D/A, CS, DMG, GOLD).
        for i, (label, value) in enumerate((("RATING (2.0)", "2.0"), ("ADR", "85"), ("K/D", "1.25"), ("MULTIKILL (%)", "20")), 1):
            text("Player stats", label, f"{{{{Stats!Row {i} title}}}}")
            text("Player stats", value, f"{{{{Stats!MVP row {i}}}}}")
            v = _text(ps, value)
            if v:   # (room for 12/3/15)
                v.update(x=v["x"] + v["w"] - 320, w=320, align="right")
    for n in range(1, 6):
        if f"Player graphic ({n})" in comps:
            players(comps[f"Player graphic ({n})"], n)
            text(f"Player graphic ({n})", "GAME NAME", "{{Global!Game title}}")
    if "Team graphic" in comps:
        text("Team graphic", "GAME NAME", "{{Global!Game title}}")

    # The player graphics: the boards' backdrop behind the players.
    backdrop = next((l for l in (comps.get("Player stats") or {"layers": []})["layers"] if l["name"] == "Layer 1"), None)
    for n in range(1, 6):
        comp = comps.get(f"Player graphic ({n})")
        if comp and backdrop and not any(l["name"] == "Backdrop" for l in comp["layers"]):
            comp["layers"].insert(0, dict(json.loads(json.dumps(backdrop)), id=new_id("l"), name="Backdrop"))

    # The background loop over the boards' backdrop.
    for cname in LOOP_BOARDS:
        comp = comps.get(cname)
        if not comp or any(l.get("name") == "Background loop" for l in comp["layers"]):
            continue
        comp["layers"].insert(1, {
            "id": new_id("l"), "name": "Background loop", "type": "video", "x": 0, "y": 0, "w": 1920, "h": 1080,
            "opacity": 1, "rotation": 0, "visible": True, "blend": "screen", "field": "",
            "anim": {"in": {"type": "fade", "dur": 600, "delay": 0}, "out": {"type": "fade", "dur": 250, "delay": 0}},
            "src": "{{Global!BG loop}}", "fit": "cover", "loop": True, "audio": False,
            "tint": "{{Global!BG loop colour}}", "brightness": "{{Global!BG loop brightness}}", "speed": "{{Global!BG loop speed}}"})

    # Boards, lower thirds and overlays.
    for comp in data["compositions"]:
        comp["kind"] = next((k for k, names in KINDS.items() if comp["name"] in names), "board")

    # The ticker's lines from Global.
    for comp in data["compositions"]:
        for l in comp["layers"]:
            if l["type"] == "text" and l.get("scroll") and "{{Match!Ticker}}" in l["text"]:
                l["text"] = "{{Global!Ticker}}"
    data.setdefault("global", {}).setdefault("ticker", list(TICKER))

    for comp in data["compositions"]:
        for l in comp["layers"]:
            if l["type"] == "text" and l.get("scroll") and l["text"] == "{{Global!Ticker}}":
                l.update(divider=DIVIDER, dividerWidth=5)

    schedule(comps)
    casters(comps)
    pictures(comps)
    data["global"].setdefault("schedule", json.loads(json.dumps(SCHEDULE)))
    tournament(comps)

    # The sponsors a new workspace starts with.
    g = data.setdefault("global", {})
    if g.get("sponsor_set", 1) < SPONSOR_SET:
        g["sponsors"] = [{"logo": f"assets/sponsors/{name}", "secs": 10, "white": name not in IN_COLOUR} for name in SPONSORS
                         if os.path.isfile(os.path.join(starter, "assets", "sponsors", name))]
        g["sponsor_set"] = SPONSOR_SET

    # The rows of sponsor logos: every sponsor from Global.
    for comp in data["compositions"]:
        strip(comp)

    # Graphics no longer in the pack, and the files only they used.
    gone = [c for c in data["compositions"] if c["name"] in REMOVED]
    if gone:
        data["compositions"] = [c for c in data["compositions"] if c["name"] not in REMOVED]
        data["pack_removed"] = sorted(set(data.get("pack_removed") or []) | {c["name"] for c in gone})
        used = set()
        export._walk_assets(data, used)
        for comp in gone:
            mine = set()
            export._walk_assets(comp, mine)
            for rel in mine - used:
                path = os.path.join(starter, rel)
                if os.path.isfile(path):
                    os.remove(path)
            for rel in {os.path.dirname(r) for r in mine}:
                folder = os.path.join(starter, rel)
                if os.path.isdir(folder) and not os.listdir(folder):
                    os.rmdir(folder)
    return data


def strip(comp):
    parts = [l for l in comp["layers"] if l["type"] == "image" and l["y"] >= 980 and l["name"] in STRIP_PARTS]
    if len(parts) < 3:
        return
    top = min(l["y"] for l in parts)
    bottom = max(l["y"] + l["h"] for l in parts)
    at = comp["layers"].index(parts[0])
    comp["layers"] = [l for l in comp["layers"] if l not in parts]
    comp["layers"].insert(at, {
        "id": new_id("l"), "name": "Sponsors", "type": "image", "x": 360, "y": top + 4, "w": 1200, "h": bottom - top - 8,
        "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
        "anim": json.loads(json.dumps(parts[0].get("anim") or {})),
        "src": "{{Sponsors all}}", "fit": "contain", "loop": True, "mono": True})


def _label(like, **kw):
    """A new text layer in the style of another (a long name gets narrower)."""
    l = json.loads(json.dumps(like))
    l.update(id=new_id("l"), field="", fit="squeeze", **kw)
    l["baseline"] = round(l["size"] * 0.86, 1)
    l["y"] = round(l["y"])
    return l


def tournament(comps):
    """The bracket graphics, filled in from Global's tournament."""
    for cname in BRACKETS:
        comp = comps.get(cname)
        if not comp:
            continue
        for l in comp["layers"]:
            if l["type"] == "text" and l["name"] == "HEADING TITLE TEXT":
                l["text"] = "{{Global!Event}}"
            elif l["type"] == "text" and l["name"] == "FOOTER TITLE TEXT":
                l["text"] = "{{Global!Stage}}"

    # The knockout bracket: drawn for 8 or 16 teams.
    top = comps.get("Top 8 bracket")
    if top and not any(l["type"] == "bracket" for l in top["layers"]):
        last = 0
        for i, l in enumerate(top["layers"]):
            if l["type"] == "image" and l["name"].startswith(TOP8_PARTS):
                l.update(visible=False, field="")
                last = i
        title = _text(top, "8 COMPETITOR BRACKET")
        if title:
            title["text"] = "{{Tournament!Top teams}} COMPETITOR BRACKET"
        top["layers"].insert(last + 1, {
            "id": new_id("l"), "name": "Bracket", "type": "bracket", "x": 144, "y": 196, "w": 1566, "h": 748,
            "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
            "anim": {"in": {"type": "fade", "dur": 500, "delay": 150}, "out": {"type": "fade", "dur": 250, "delay": 0}},
            "font": title["font"] if title else "Redzone-Standard", "color": "#ffffff",
            "gold": "#b28a1d", "dark": "#000b05", "line": "#b28a1d", "champ": "#ffc52a"})

    # The groups: names and scores on the design's slots.
    groups = comps.get("Group bracket")
    if groups and not any("{{Tournament!" in str(l.get("text")) for l in groups["layers"]):
        head = _text(groups, "GROUP A")
        slots = {}
        for l in groups["layers"]:
            if l["type"] == "image" and (l["name"].startswith("Position ") or l["name"] in ("Rectangle 3", "Rectangle 3 copy")):
                g = ("A" if l["y"] < 560 else "B") if l["x"] < 900 else ("C" if l["y"] < 560 else "D")
                col = 0 if l["x"] % 1010 < 200 else 1 if l["name"].startswith("Position") else 2
                slots.setdefault((g, col), []).append(l)
        names = {0: [("Opening 1", 1), ("Opening 1", 2), ("Opening 2", 1), ("Opening 2", 2), ("Elimination", 1), ("Elimination", 2)],
                 1: [("Winners", 1), ("Winners", 2), ("Decider", 1), ("Decider", 2)]}
        new = []
        for (g, col), boxes in slots.items():
            boxes.sort(key=lambda l: l["y"])
            for i, box in enumerate(boxes):
                if col == 2:
                    key = f"Group {g} {'1st' if i == 0 else '2nd'}"
                    new.append((box, _label(head, name=key, text=f"{{{{Tournament!{key}}}}}", x=box["x"] + 10, w=box["w"] - 20,
                                            size=30, align="center", y=box["y"] + (box["h"] - 30 * 1.2) / 2, h=round(30 * 1.4))))
                    continue
                match, side = names[col][i]
                key = f"Group {g} {match} team {side}"
                size = 22
                sq = round(box["h"] * 0.67)
                top_y = box["y"] + (box["h"] - size * 1.15) / 2
                new.append((box, _label(head, name=key, text=f"{{{{Tournament!{key}}}}}", x=box["x"] + 7, w=box["w"] - sq - 12,
                                        size=size, align="left", y=top_y, h=round(size * 1.4))))
                new.append((box, _label(head, name=key + " score", text=f"{{{{Tournament!{key} score}}}}",
                                        x=box["x"] + box["w"] - sq, w=sq, size=size, align="center", y=top_y, h=round(size * 1.4))))
        for box, label in new:
            groups["layers"].insert(groups["layers"].index(box) + 1, label)
        for g in "ABCD":
            l = _text(groups, f"GROUP {g}")
            if l:
                l["text"] = f"{{{{Tournament!Group {g} name}}}}"

    # The final four: the knockout bracket's last two rounds.
    ff = comps.get("Final four")
    if ff:
        for n in range(1, 5):
            l = _text(ff, f"Semi{n}")
            if l:
                l["text"] = f"{{{{Tournament!Top semi {n}}}}}"
        for n in range(1, 3):
            l = _text(ff, f"GF{n}")
            if l:
                l["text"] = f"{{{{Tournament!Top final {n}}}}}"
        l = _text(ff, "WINNING TEAM")
        if l:
            l["text"] = "{{Tournament!Top champion}}"
        scores = sorted([l for l in ff["layers"] if l["type"] == "text" and l["name"] == "0"], key=lambda l: (l["x"], l["y"]))
        keys = [f"Top semi {n} score" for n in range(1, 5)] + [f"Top final {n} score" for n in range(1, 3)]
        for l, key in zip(scores, keys):
            l["text"] = f"{{{{Tournament!{key}}}}}"


def remember(old, new):
    """Adds the old graphics' signatures to the new project's pack_history."""
    history = dict(old.get("pack_history") or {})
    for comp in old.get("compositions", []):
        sigs = history.setdefault(comp["name"], [])
        if signature(comp) not in sigs:
            sigs.append(signature(comp))
    new["pack_history"] = history
    return new


def main():
    path = os.path.join(STARTER, "project.json")
    with open(path, encoding="utf-8") as f:
        old = json.load(f)
    new = remember(old, link(json.loads(json.dumps(old))))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(new, f, indent=1)
    print("Updated", path)


if __name__ == "__main__":
    main()
