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
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gfxengine.pack import signature  # noqa: E402
from gfxengine.project import new_id  # noqa: E402

STARTER = os.path.join(ROOT, "starter")

# Boards that fill the screen: the background loop plays over their backdrop.
LOOP_BOARDS = ("Schedule", "Team stats", "Player stats", "Group bracket", "Top 8 bracket", "Final four")
# What each graphic is: one board and one lower third can be on air at a time.
KINDS = {"lower third": ("Caster lower third",),
         "overlay": ("Scorebug & footer", "Replay overlay")}
TICKER = ["WELCOME TO ST. CLAIR SAINTS ESPORTS", "FOLLOW @SCCSAINTS FOR HIGHLIGHTS", "THANKS FOR WATCHING!"]
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
# The sponsors a new workspace starts with: the pictures in the sponsor spots.
SPONSORS = [("assets/Scorebug _ footer/SPONSOR REPLACE.png", "Subway.png"),
            ("assets/Schedule/REPLACE WITH SPONSORS.png", "NAC Esports.png")]
# Text placed by hand from the PSDs' renders, where the importer's guess was off:
# (graphic, layer name, nth with that name) -> x, w, size, align, baseline (from the top of the canvas).
PLACED = {
    ("Team stats", "SsssssssssG", 0): dict(x=297, w=560, size=80, align="left", base=372),
    ("Team stats", "XssssssssX", 0): dict(x=1070, w=560, size=80, align="right", base=372),
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

    def text(cname, lname, value, nth=0):
        l = _text(comps[cname], lname, nth)
        if l:
            l["text"] = value

    # Scores, event and teams from Global.
    if "Team stats" in comps:
        text("Team stats", "SsssssssssG", "{{Global!Left name}}")
        text("Team stats", "XssssssssX", "{{Global!Right name}}")
        text("Team stats", "0", "{{Global!Left score}}", 0)
        text("Team stats", "0", "{{Global!Right score}}", 1)
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
        text("Player stats", "PLAYER NAME", "{{Stats!MVP}}")
        text("Player stats", "TEAM NAME", "{{Stats!MVP team}}")
        text("Player stats", "GAME", "{{Global!Game title}}")
        for label, value, (lt, vt) in (("RATING (2.0)", "2.0", ("{{Stats!Stat 1 title}}", "{{Stats!MVP stat 1}}")),
                                       ("ADR", "85", ("{{Stats!Stat 2 title}}", "{{Stats!MVP stat 2}}")),
                                       ("K/D", "1.25", ("K/D", "{{Stats!MVP K/D}}")),
                                       ("MULTIKILL (%)", "20", ("{{Stats!Stat 3 title}}", "{{Stats!MVP stat 3}}"))):
            text("Player stats", label, lt)
            text("Player stats", value, vt)
    for n in range(1, 6):
        cname = f"Player graphic ({n})"
        if cname not in comps:
            continue
        pg = comps[cname]
        names = sorted([l for l in pg["layers"] if l["type"] == "text" and l["name"] != "GAME NAME"], key=lambda l: l["x"])
        for i, l in enumerate(names, 1):
            l["text"] = f"{{{{Stats!Left player {i}}}}}"
        text(cname, "GAME NAME", "{{Global!Game title}}")
    if "Team graphic" in comps:
        text("Team graphic", "GAME NAME", "{{Global!Game title}}")

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

    tournament(comps)

    # The sponsors a new workspace starts with.
    g = data.setdefault("global", {})
    if not g.get("sponsors"):
        g["sponsors"] = []
        for src, name in SPONSORS:
            dest = os.path.join(starter, "assets", "sponsors", name)
            if os.path.isfile(os.path.join(starter, src)):
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.copy(os.path.join(starter, src), dest)
                g["sponsors"].append({"logo": f"assets/sponsors/{name}", "secs": 10})
    return data


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
