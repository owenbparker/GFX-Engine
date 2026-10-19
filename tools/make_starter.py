"""Builds starter/ (the example graphics a new engine starts with) from the
SCC broadcast PSDs and stingers.

    python tools/make_starter.py <folder with the PSDs> <folder with the stingers>

The PSD folder needs ScheduleGraphic_Screen.psd, LowerThirds-FOOTER.psd,
LOWER 3RD SGS.psd and TEAM STAT PAGE.psd; the stinger folder
SCC_Main_Stinger.mov, SCC_Replay.mov and SCCIntroStinger.webm.
"""

import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gfxengine import media  # noqa: E402
from gfxengine.project import DEFAULT_TRANSITIONS, Workspace, new_id  # noqa: E402
from gfxengine.psdimport import import_psd  # noqa: E402

GRAPHICS = [
    ("ScheduleGraphic_Screen.psd", "Schedule"),
    ("LowerThirds-FOOTER.psd", "Scorebug & footer"),
    ("LOWER 3RD SGS.psd", "Caster lower third"),
    ("TEAM STAT PAGE.psd", "Team stats"),
]

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
    tokens = {
        "Scorebug & footer": {"0 LEFT": "{{Match!Left score}}", "0 RIGHT": "{{Match!Right score}}",
                              "NACE VARSITYhhhhhhhhhh": "{{Match!Event}}",
                              "ROCKET LEAGUE | PLAYOFFSssssssss": "{{Match!Game}}",
                              "00:03:1411111": "{{countdown:19:30}}", "STARTING SOONnnnn": "STARTING SOON"},
        "Schedule": {"07:25 PM EST LOCAL TIME": "{{time}} EST\nLOCAL TIME", "SG": "{{Match!Left}}",
                     "GMU": "{{Match!Right}}"},
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
    ws.save()
    for leftover in ("live.json",):
        p = os.path.join(out, leftover)
        if os.path.exists(p):
            os.remove(p)
    shutil.rmtree(os.path.join(out, ".uploads"), ignore_errors=True)
    print("Wrote", out)


if __name__ == "__main__":
    main(*sys.argv[1:3])
