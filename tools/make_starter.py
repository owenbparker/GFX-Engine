"""Builds starter/ (the example graphics a new engine starts with) from the
SCC broadcast PSDs and stingers.

    python tools/make_starter.py <folder with the PSDs> <folder with the stingers>

The PSD folder is the SCC graphics folder (the PSDs in GRAPHICS below, and
the SCREENS folder); the stinger folder has SCC_Main_Stinger.mov,
SCC_Replay.mov and SCCIntroStinger.webm. The St. Clair badge (the left
team's logo) comes from packaging/.
"""

import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gfxengine import media  # noqa: E402
from gfxengine.project import DEFAULT_TRANSITIONS, Workspace, new_id  # noqa: E402
from gfxengine.psdimport import import_psd  # noqa: E402
import scc_pack  # noqa: E402  (tools/)

SCREENS = "24-11 SCS_Stream Overlay Graphics/SCREENS/"
GRAPHICS = [
    ("ScheduleGraphic_Screen.psd", "Schedule"),
    ("LowerThirds-FOOTER.psd", "Scorebug & footer"),
    ("LOWER 3RD SGS.psd", "Caster lower third"),
    ("TEAM STAT PAGE.psd", "Team stats"),
    (SCREENS + "1-Title Graphic/TitleGraphic_Screen.psd", "Title screen"),
    (SCREENS + "3-Starting Soon_Intermission Screen/StartingSoonScreen.psd", "Starting soon"),
    ("Team Graphic.psd", "Team graphic"),
    ("1 Player Graphic.psd", "Player graphic (1)"),
    ("2 Player Graphic.psd", "Player graphic (2)"),
    ("3 Player Graphic.psd", "Player graphic (3)"),
    ("4 Player Graphic.psd", "Player graphic (4)"),
    ("5 Player Graphic.psd", "Player graphic (5)"),
    ("INDIVIDUAL STAT PAGE.psd", "Player stats"),
    ("GROUP BRACKET.psd", "Group bracket"),
    ("TOP 8.psd", "Top 8 bracket"),
    ("FINAL FOUR.psd", "Final four"),
    (SCREENS + "10-Replay Overlay/REPLAY-Overlay.psd", "Replay overlay"),
    ("SponsorLogos_Footer.psd", "Sponsor footer"),
]
# The teams, series and event every graphic can use ({{Global!Left name}}...).
GLOBAL = {"event": "NACE VARSITY", "stage": "PLAYOFFS", "best_of": 3, "game": "",
          "left": {"name": "St. Clair Saints", "short": "SCC", "logo": "", "color": "#0b6b3a", "score": 0},
          "right": {"name": "Opponent", "short": "OPP", "logo": "", "color": "#b8191c", "score": 0},
          "custom": [["Game title", "ROCKET LEAGUE | PLAYOFFS"]]}

MATCH_CSV = """Field,Value
Left,SCC
Right,GMU
Left score,1
Right score,0
Event,NACE VARSITY
Game,ROCKET LEAGUE | PLAYOFFS
Ticker,WELCOME TO ST. CLAIR SAINTS ESPORTS  |  FOLLOW @SCCSAINTS FOR HIGHLIGHTS  |  THANKS FOR WATCHING!
"""


def main(psd_dir, stinger_dir):
    out = os.path.join(ROOT, "starter")
    try:   # (what the workspaces may still have, so they can be brought up to date)
        with open(os.path.join(out, "project.json"), encoding="utf-8") as f:
            previous = json.load(f)
    except (OSError, ValueError):
        previous = {}
    shutil.rmtree(out, ignore_errors=True)
    ws = Workspace(out, starter=None)
    ws.data["name"] = "SCC Broadcast"
    for fname, title in GRAPHICS:
        comp, fonts = import_psd(os.path.join(psd_dir, fname), ws, title)
        print(title, len(comp["layers"]), "layers, fonts:", ", ".join(fonts))
        ws.add_comp(comp)

    # The match data, as a CSV the graphics read from.
    rel, path = ws.unique_asset("Match.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write(MATCH_CSV)
    ws.data["sources"] = [{"id": new_id("s"), "name": "Match", "type": "file", "path": rel, "refresh": 2}]
    # The badge as the left team's logo.
    rel, path = ws.unique_asset("St Clair Saints.png", "logos")
    shutil.copy(os.path.join(ROOT, "web", "assets-ui", "badge.png"), path)
    ws.data["global"] = dict(GLOBAL, left=dict(GLOBAL["left"], logo=rel))
    # The home screen's picture for workspaces made from it.
    shutil.copy(os.path.join(ROOT, "web", "assets-ui", "badge.png"), os.path.join(out, "cover.png"))
    ws.data["picture"] = "cover.png"
    tokens = {
        "Scorebug & footer": {"0 LEFT": "{{Global!Left score}}", "0 RIGHT": "{{Global!Right score}}",
                              "NACE VARSITYhhhhhhhhhh": "{{Global!Event}}",
                              "ROCKET LEAGUE | PLAYOFFSssssssss": "{{Global!Game title}}",
                              "00:03:1411111": "{{countdown:19:30}}", "STARTING SOONnnnn": "STARTING SOON"},
        "Schedule": {"07:25 PM EST LOCAL TIME": "{{time}} EST\nLOCAL TIME", "SG": "{{Global!Left short}}",
                     "GMU": "{{Global!Right short}}"},
        "Replay overlay": {"ST. CLAIR SAINTS": "{{Global!Left name}}"},
    }
    for comp in ws.data["compositions"]:
        for layer in comp["layers"]:
            text = tokens.get(comp["name"], {}).get(layer["name"])
            if text is not None and layer["type"] == "text":
                layer["text"] = text
            if layer["type"] == "text" and layer["name"].startswith("ANNOUNCEMENT TEXT"):
                layer["text"] = "{{Match!Ticker}}"
        # Score digits and tricodes centred on where they were.
        for layer in comp["layers"]:
            if layer["type"] == "text" and layer["name"] in ("0 LEFT", "0 RIGHT", "0"):
                cx = layer["x"] + layer["w"] / 2
                layer["w"] = max(layer["w"], 120)
                layer["x"] = round(cx - layer["w"] / 2)
                layer["align"] = "center"
    # The scrolling announcement: one layer across the bar, not two copies.
    for comp in ws.data["compositions"]:
        ticks = [l for l in comp["layers"] if l["type"] == "text" and l["name"].startswith("ANNOUNCEMENT TEXT")]
        for extra in ticks[1:]:
            comp["layers"].remove(extra)
        if ticks:
            t = ticks[0]
            t.update({"x": 0, "w": 1920, "scroll": 90, "fit": "none", "field": "Ticker"})
            # (the divider between the two copies of the old, still ticker)
            comp["layers"] = [l for l in comp["layers"] if l["name"] != "Rectangle 6"]
        if comp["name"] == "Scorebug & footer":
            # The full-screen tint is for mock-ups over a still: the overlay goes over the game.
            for l in comp["layers"]:
                if l["name"] == "Layer 1" and l["w"] >= 1920:
                    l["visible"] = False

    # The stingers.
    stingers = []
    for src, name, label in (("SCC_Main_Stinger.mov", "SCC_Main_Stinger", "SCC stinger"),
                             ("SCC_Replay.mov", "SCC_Replay", "Replay stinger"),
                             ("SCCIntroStinger.webm", "SCCIntroStinger", "Intro stinger")):
        path = os.path.join(stinger_dir, src)
        rel, dest = ws.unique_asset(name + ".webm", "stingers")
        if src.endswith(".webm"):
            shutil.copy(path, dest)
        else:
            media.convert(path, os.path.splitext(dest)[0], alpha=True)
        cut = media.stinger_cut(dest)
        stingers.append({"id": new_id("t"), "name": label, "type": "stinger", "src": rel, "cut": cut,
                         "audio": True, "volume": 1, "enabled": True})
        print(label, rel, "cut at", cut, "ms")
    ws.data["transitions"] = [dict(t) for t in DEFAULT_TRANSITIONS] + stingers
    ws.data["default_transition"] = stingers[0]["id"]
    scc_pack.remember(previous, scc_pack.link(ws.data, out))
    ws.save()
    for leftover in ("live.json",):
        p = os.path.join(out, leftover)
        if os.path.exists(p):
            os.remove(p)
    shutil.rmtree(os.path.join(out, ".uploads"), ignore_errors=True)
    print("Wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:3])
