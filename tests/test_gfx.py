import io
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import unittest
import urllib.request
import zipfile

from PIL import Image

from gfxengine import data, fonts, media
from gfxengine.config import ROOT, Settings
from gfxengine.live import Live
from gfxengine.project import Workspace, blank_comp, blank_layer


class DataTests(unittest.TestCase):
    def test_google_links(self):
        base = "https://docs.google.com/spreadsheets/d/ABC123/edit#gid=42"
        self.assertEqual(data.gsheet_csv_url(base), "https://docs.google.com/spreadsheets/d/ABC123/export?format=csv&gid=42")
        self.assertIn("gviz/tq?tqx=out:csv&sheet=Scores%201", data.gsheet_csv_url(base, "Scores 1"))
        pub = "https://docs.google.com/spreadsheets/d/e/2PACX-xyz/pubhtml?gid=7"
        self.assertEqual(data.gsheet_csv_url(pub), "https://docs.google.com/spreadsheets/d/e/2PACX-xyz/pub?output=csv&gid=7")
        with self.assertRaises(ValueError):
            data.gsheet_csv_url("https://example.com/nope")

    def test_parsing_and_references(self):
        rows, _ = data.parse("x.csv", b"Team,Score\nSCC,3\nGMU,1\n")
        self.assertEqual(data.lookup(rows, "B2"), "3")
        self.assertEqual(data.lookup(rows, "Score#2"), "1")
        self.assertEqual(data.lookup(rows, "SCC"), "3")       # label | value
        self.assertEqual(data.lookup(rows, "Z9"), "")
        rows, _ = data.parse("x.json", json.dumps([{"a": 1, "b": "x"}, {"a": 2}]).encode())
        self.assertEqual(rows, [["a", "b"], ["1", "x"], ["2", ""]])
        rows, _ = data.parse("x.json", b'{"Score": 4, "Team": "SCC"}')
        self.assertEqual(data.lookup(rows, "Team"), "SCC")
        rows, _ = data.parse("x.txt", b"one\ntwo\n")
        self.assertEqual(data.lookup(rows, "A2"), "two")
        self.assertEqual(data.col_letters(27), "AB")
        self.assertEqual(data.col_index("AB"), 27)

    def test_excel(self):
        from openpyxl import Workbook
        wb = Workbook()
        wb.active.title = "First"
        wb.active.append(["Team", "Score"])
        wb.active.append(["SCC", 3.0])
        wb.create_sheet("Second").append(["x"])
        buf = io.BytesIO()
        wb.save(buf)
        rows, sheets = data.parse("t.xlsx", buf.getvalue())
        self.assertEqual(rows, [["Team", "Score"], ["SCC", "3"]])
        self.assertEqual(sheets, ["First", "Second"])
        rows, _ = data.parse("t.xlsx", buf.getvalue(), "Second")
        self.assertEqual(rows, [["x"]])


class FontTests(unittest.TestCase):
    def test_names(self):
        n = fonts.names(os.path.join(ROOT, "web", "fonts", "Inter.ttf"))
        self.assertTrue(n["postscript"].startswith("Inter"), n)
        self.assertEqual(n["family"], "Inter")
        self.assertEqual(fonts.names(os.path.join(ROOT, "web", "fonts", "Montserrat-700.woff2"))["postscript"], "Montserrat-700")


class LiveTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ws = Workspace(self.dir, starter="")
        self.a = self.ws.add_comp(blank_comp("A"))
        self.b = self.ws.add_comp(blank_comp("B"))
        self.live = Live(self.ws)

    def tearDown(self):
        self.ws.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_preview_take_program(self):
        live = self.live
        live.cue(self.b["id"])
        live.cue(self.a["id"])
        self.assertEqual(live.get()["preview"]["on"], [self.a["id"], self.b["id"]])   # project order
        live.set_values(self.a["id"], {"Name": "Owen"})
        t = live.take("fade")
        state = live.get()
        self.assertEqual(t["type"], "fade")
        self.assertEqual(state["program"]["on"], [self.a["id"], self.b["id"]])
        self.assertEqual(state["program"]["values"][self.a["id"]], {"Name": "Owen"})
        self.assertEqual(state["take"]["seq"], 1)
        self.assertEqual(state["preview"]["on"], [])          # taken: off Preview
        # New values on Preview stay off air until sent.
        live.set_values(self.a["id"], {"Name": "Sam"})
        self.assertEqual(live.get()["program"]["values"][self.a["id"]]["Name"], "Owen")
        live.send_values(self.a["id"])
        self.assertEqual(live.get()["program"]["values"][self.a["id"]]["Name"], "Sam")
        self.assertEqual(live.get()["take"]["seq"], 1)      # no transition for that
        live.program(self.b["id"], False)
        state = live.get()
        self.assertEqual(state["program"]["on"], [self.a["id"]])
        self.assertEqual(state["take"]["comps"], [self.b["id"]])
        live.take("cut")                                      # always there (nothing on Preview: nothing changes)
        self.assertEqual(live.get()["program"]["on"], [self.a["id"]])
        live.clear()
        self.assertEqual(live.get()["program"]["on"], [])
        with self.assertRaises(KeyError):
            live.take("nope")
        with self.assertRaises(KeyError):
            live.cue("nope")
        # Saved, and read back.
        live.cue(self.b["id"])
        self.assertEqual(Live(self.ws).get()["preview"]["on"], [self.b["id"]])

    def test_one_board_and_one_lower_third(self):
        live, ws = self.live, self.ws
        board2 = ws.add_comp(dict(blank_comp("Board 2"), kind="board"))
        lt1 = ws.add_comp(dict(blank_comp("LT 1"), kind="lower third"))
        lt2 = ws.add_comp(dict(blank_comp("LT 2"), kind="lower third"))
        for c in (self.a,):
            ws.put_comp(dict(ws.comp(c["id"]), kind="board"))
        # (b is an overlay)
        live.cue(self.a["id"]); live.cue(board2["id"])
        self.assertEqual(live.get()["preview"]["on"], [board2["id"]])        # the other board went
        live.cue(lt1["id"]); live.cue(self.b["id"])
        live.take("cut")
        self.assertEqual(set(live.get()["program"]["on"]), {board2["id"], lt1["id"], self.b["id"]})
        live.cue(lt2["id"])
        live.take("cut")                                      # replaces the lower third only
        self.assertEqual(set(live.get()["program"]["on"]), {board2["id"], lt2["id"], self.b["id"]})
        live.cue(self.a["id"])
        live.program(self.a["id"], True)                      # IN: the board swaps, and it's off Preview
        state = live.get()
        self.assertEqual(set(state["program"]["on"]), {self.a["id"], lt2["id"], self.b["id"]})
        self.assertEqual(state["preview"]["on"], [])

    def test_delete_takes_it_off(self):
        self.live.cue(self.a["id"])
        self.live.take("cut")
        self.ws.delete_comp(self.a["id"])
        self.live.forget(self.a["id"])
        self.assertEqual(self.live.get()["program"]["on"], [])


class PsdTests(unittest.TestCase):
    def test_import(self):
        from psd_tools import PSDImage
        from gfxengine.psdimport import import_psd
        tmp = tempfile.mkdtemp()
        try:
            img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 0))
            img.paste((10, 120, 60, 255), (100, 800, 900, 980))
            psd = PSDImage.frompil(img)
            path = os.path.join(tmp, "Lower third.psd")
            psd.save(path)
            ws = Workspace(os.path.join(tmp, "ws"), starter="")
            comp, used_fonts = import_psd(path, ws)
            ws.close()
            self.assertEqual(comp["name"], "Lower third")
            self.assertGreaterEqual(len(comp["layers"]), 1)
            layer = comp["layers"][0]
            self.assertEqual(layer["type"], "image")
            self.assertTrue(os.path.isfile(ws.asset_path(layer["src"])))
            self.assertIn("in", layer["anim"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(media.ffmpeg_path(), "needs FFmpeg")
class MediaTests(unittest.TestCase):
    def test_png_sequence_to_see_through_video_and_stinger_cut(self):
        tmp = tempfile.mkdtemp()
        try:
            # 12 frames: see-through, then covering everything from frame 6.
            for i in range(12):
                im = Image.new("RGBA", (64, 36), (0, 0, 0, 0))
                if i >= 6:
                    im.paste((0, 100, 50, 255), (0, 0, 64, 36))
                else:
                    im.paste((250, 200, 20, 255), (0, 0, 10 * i + 1, 36))
                im.save(os.path.join(tmp, f"f{i:06d}.png"))
            out = media.convert(os.path.join(tmp, "f%06d.png"), os.path.join(tmp, "out"), alpha=True, fps=12, sequence=True)
            self.assertTrue(out.endswith(".webm"))
            info = media.probe(out)
            self.assertTrue(info["alpha"], info)
            self.assertTrue(media.playable(out, info))
            cut = media.stinger_cut(out, info)
            self.assertIsNotNone(cut)
            self.assertGreater(cut, 300)
            self.assertLess(cut, 700)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class StatsTests(unittest.TestCase):
    def test_games_to_one_table(self):
        from gfxengine import stats
        f = {"LEFT P1 NAME": "Owen", "LEFT P1 AGENT": "Jett", "LEFT P1 K": "12", "LEFT P1 D": "4", "LEFT P1 A": "3",
             "RIGHT P1 NAME": "Sam", "RIGHT P1 K": "5", "RIGHT P1 D": "9", "SCORE LEFT": "7"}
        t = dict(stats.rows(stats.read("valorant", f), True, {"left": "SCC"})[1:])
        self.assertEqual((t["Status"], t["Left score"], t["Left player 1"], t["Left player 1 stat 2"]), ("LIVE", "7", "Owen", "12"))
        self.assertEqual((t["MVP"], t["MVP team"], t["MVP K/D"], t["Stat 1 title"]), ("Owen", "SCC", "3.00", "ACS"))
        # VALORANT: ACS (estimated over the 7 rounds), kills, deaths; the big number is rounds won; agent icons.
        self.assertEqual((t["Left player 1 stat 1"], t["Row 4 title"], t["Left kills"], t["Left total kills"]), ("354", "ASSISTS", "7", "12"))
        pics = dict(stats.rows(stats.read("valorant", f), True, {}, "auto", None, {"team": {"left": "champion"}, "player": {"left": "headshot"}})[1:])
        self.assertEqual((pics["Left player 1 champion"], pics["MVP champion"]), ("agents/Jett.png", ""))
        lol = stats.read("lol", {"P1 NAME": "A", "P1 KDA": "3/1/7", "KILLS LEFT": 3})
        self.assertEqual((lol["left"]["players"][0]["stats"], lol["left"]["score"]), ([3, 1, 7], 3))
        rl = dict(stats.rows(stats.read("rl", {"left_p1_name": "B", "left_p1_goals": 2}), False)[1:])
        self.assertEqual((rl["Status"], rl["Stat 1 title"], rl["Left player 1 stat 1"]), ("FINAL", "GOALS", "2"))
        self.assertIsNone(stats.read("valorant", {"SCORE LEFT": 3}))      # no players: no game going
        self.assertIsNone(stats.read("cod", f))
        # League: K/D/A, CS, DMG (damage once the game is over), GOLD; each team's kills.
        lf = {"P1 NAME": "A", "P1 KDA": "3/1/7", "P1 CS": "210", "P1 GOLD RAW": "9800", "P6 NAME": "B", "P6 KDA": "1/3/0"}
        t = dict(stats.rows(stats.read("lol", lf), True)[1:])
        self.assertEqual((t["Stat 1 title"], t["Row 4 title"], t["Left player 1 stat 1"], t["Left player 1 stat 3"],
                          t["MVP row 4"], t["Left kills"], t["Right kills"]), ("K/D/A", "GOLD", "3/1/7", "–", "9.8K", "3", "1"))
        # (stats kept by the version before: no "values")
        old = stats.read("lol", lf)
        for side in ("left", "right"):
            for p in old[side]["players"]:
                p.pop("values")
        self.assertEqual(dict(stats.rows(old, False)[1:])["MVP row 3"], "–")
        lf["P1 DMG"] = "23456"
        self.assertEqual(dict(stats.rows(stats.read("lol", lf), False)[1:])["MVP row 3"], "23,456")

    def test_player_stats_pick_and_roster(self):
        from gfxengine import stats
        from gfxengine.teams import player_named
        team = {"players": [{"name": "Owen Parker", "ign": "Owen", "country": "ca", "photo": "library/teams/players/o.png"},
                            {"name": "Sam Lee", "ign": "Sammy", "country": "", "photo": ""}]}
        f = {"LEFT P1 NAME": "owen#NA1", "LEFT P1 K": "12", "LEFT P2 NAME": "Sammy", "LEFT P2 K": "20",
             "RIGHT P1 NAME": "Zed", "RIGHT P1 K": "15"}
        look = lambda side, name: player_named(team, name) if side == "left" else None
        auto = dict(stats.rows(stats.read("valorant", f), True, {}, "auto", look)[1:])
        self.assertEqual((auto["MVP"], auto["MVP name"], auto["MVP picked"], auto["MVP headshot shown"]), ("Sammy", "Sam Lee", "auto", ""))
        mine = dict(stats.rows(stats.read("valorant", f), True, {}, "left 1", look)[1:])
        self.assertEqual((mine["MVP name"], mine["MVP flag"], mine["MVP headshot"], mine["MVP stat 2"]),
                         ("Owen Parker", "flags/ca.svg", "library/teams/players/o.png", "12"))
        other = dict(stats.rows(stats.read("valorant", f), True, {}, "right 1", look)[1:])
        self.assertEqual((other["MVP name"], other["MVP flag shown"]), ("Zed", ""))
        self.assertEqual((mine["Left player 1"], mine["Left player 1 ID"], mine["Left player 2"]), ("Owen Parker", "owen#NA1", "Sam Lee"))
        self.assertIsNone(player_named(team, "Sam Lee"))              # (only the in-game ID links a player)
        gone = dict(stats.rows(stats.read("valorant", f), True, {}, "right 4", look)[1:])
        self.assertEqual(gone["MVP"], "Sammy")                        # (picked one not in the game: the top one)
        self.assertEqual(dict(stats.rows(None, False)[1:])["MVP headshot shown"], "1")

    def test_champion_or_headshot(self):
        from gfxengine import stats
        from gfxengine.teams import player_named
        team = {"players": [{"name": "Owen Parker", "ign": "Owen", "country": "ca", "photo": "library/teams/players/o.png"}]}
        icon = "https://ddragon.leagueoflegends.com/cdn/15.20.1/img/champion/Ahri.png"
        f = {"P1 NAME": "Owen", "P1 KDA": "5/1/2", "P1 CHAMPION ICON": icon, "P6 NAME": "Zed", "P6 KDA": "1/5/0"}
        look = lambda side, name: player_named(team, name) if side == "left" else None
        heads = dict(stats.rows(stats.read("lol", f), True, {}, "auto", look, {"left": "headshot"})[1:])
        self.assertEqual((heads["Left player 1 headshot"], heads["Left player 1 champion"], heads["MVP headshot shown"]),
                         ("library/teams/players/o.png", "", "1"))
        champs = dict(stats.rows(stats.read("lol", f), True, {}, "auto", look, {"left": "champion"})[1:])
        self.assertEqual((champs["Left player 1 headshot"], champs["Left player 1 champion"], champs["MVP headshot"]), ("", icon, ""))
        self.assertEqual(champs["MVP champion"], "https://ddragon.leagueoflegends.com/cdn/img/champion/tiles/Ahri_0.jpg")

    def test_kept_after_the_game(self):
        from gfxengine.stats import Stats
        tmp = tempfile.mkdtemp()
        try:
            s = Stats(tmp)
            self.assertTrue(s.update("VAL HUD", "valorant", {"LEFT P1 NAME": "Owen", "LEFT P1 K": 3}))
            self.assertFalse(s.update("VAL HUD", "valorant", {"LEFT P1 NAME": "Owen", "LEFT P1 K": 3}))
            self.assertFalse(s.update("VAL HUD", "valorant", {}))           # nothing: the stats stay
            again = Stats(tmp)                                               # (an engine restart)
            self.assertFalse(again.live())
            t = dict(again.rows()[1:])
            self.assertEqual((t["Status"], t["Left player 1"]), ("FINAL", "Owen"))
            again.clear()
            self.assertEqual(dict(Stats(tmp).rows()[1:])["Status"], "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RosterLinkTests(unittest.TestCase):
    def test_save_ign_to_player(self):
        from gfxengine.teams import Teams
        d = tempfile.mkdtemp()
        try:
            t = Teams(d)
            t.save([{"name": "Saints", "game": "League of Legends", "players": [
                {"name": "Topablo", "ign": "Old"}, {"name": "Matty", "ign": "Pablo"}]}])
            team = t.link("saints", "League of Legends", 0, "Pablo")
            self.assertEqual([p["ign"] for p in team["players"]], ["Pablo", ""])   # (one player per in-game ID)
            with self.assertRaises(ValueError):
                t.link("Saints", "", 5, "x")
        finally:
            shutil.rmtree(d)


class HeadshotTests(unittest.TestCase):
    def test_trimmed_to_the_player(self):
        from gfxengine.teams import trim_photo
        d = tempfile.mkdtemp()
        try:
            path = os.path.join(d, "p.png")
            im = Image.new("RGBA", (400, 600), (0, 0, 0, 0))
            im.paste((200, 50, 50, 255), (100, 200, 300, 600))
            im.save(path)
            self.assertTrue(trim_photo(path))
            self.assertEqual(Image.open(path).size, (204, 402))     # (the player, and 2px around)
            self.assertFalse(trim_photo(path))                       # (once is enough)
        finally:
            shutil.rmtree(d)


class PicturesTests(unittest.TestCase):
    def test_team_and_player_stats_each_have_their_own(self):
        from gfxengine import globalcfg
        old = globalcfg.clean({"pictures": {"left": "champion", "right": "headshot"}})["pictures"]   # (v1.0.20-23)
        self.assertEqual(old["team"], old["player"])
        self.assertEqual(old["player"], {"left": "champion", "right": "headshot"})


class UpdaterTests(unittest.TestCase):
    def test_update_leaves_the_users_files(self):
        from gfxengine.updater import Updater
        u = Updater()
        u.work_dir = tempfile.mkdtemp()
        try:
            with open(u._write_script(os.path.join(u.work_dir, "new")), encoding="utf-8") as f:
                text = f.read()
        finally:
            shutil.rmtree(u.work_dir)
        copy = [l for l in text.splitlines() if "/XD _internal" in l][0]
        for kept in ("workspaces", "workspace", "library", "settings.json"):
            self.assertIn(" " + kept, copy)


class GlobalTests(unittest.TestCase):
    def test_sponsors_rotate(self):
        from gfxengine import globalcfg
        g = globalcfg.clean({"sponsors": [{"logo": "a.png", "secs": 5}, {"logo": "b.png", "secs": 0}, {"secs": 3}],
                             "sponsor_epoch": 100})
        self.assertEqual([s["secs"] for s in g["sponsors"]], [5, 1])       # at least a second; no logo, no sponsor
        self.assertEqual(globalcfg.sponsor_now(g, 102), (0, 3))
        self.assertEqual(globalcfg.sponsor_now(g, 105.5)[0], 1)
        self.assertEqual(globalcfg.sponsor_now(g, 106)[0], 0)              # and round again
        new = globalcfg.sponsors_changed(g, globalcfg.clean(dict(g, sponsors=[{"logo": "b.png", "secs": 4}])))
        self.assertGreater(new["sponsor_epoch"], 100)
        rows = dict(globalcfg.rows(new)[1:])
        self.assertEqual((rows["Sponsor logo"], rows["Sponsors"]), ("b.png", "1"))
        self.assertEqual(rows["BG loop"], globalcfg.DEFAULT_LOOP)
        self.assertEqual(dict(globalcfg.rows(dict(new, bgloop={"on": False}))[1:])["BG loop"], "")


class TimerTests(unittest.TestCase):
    def test_start_pause_reset_and_count_down(self):
        from gfxengine import globalcfg as gc
        t = gc.clean({})["timer"]
        t = gc.timer_action(t, "start", now=100)
        self.assertEqual(gc.timer_now(t, 165), 65)
        t = gc.timer_action(t, "toggle", now=165)                          # pause
        self.assertEqual((t["started"], gc.timer_now(t, 999)), (0, 65))
        t = gc.timer_action(t, "reset", now=170)
        self.assertEqual(t["secs"], 0)
        t = gc.timer_action(t, "set", secs=gc.parse_secs("5:00"), down=True, now=200)
        t = gc.timer_action(t, "start", now=200)
        self.assertEqual(gc.timer_now(t, 230), 270)
        self.assertEqual(gc.timer_now(t, 900), 0)                          # stops at 0
        self.assertFalse(gc.timer_running(t, 900))
        t = gc.timer_action(t, "toggle", now=900)                           # ran out: starts again from 5:00
        self.assertEqual(gc.timer_now(t, 910), 290)
        self.assertEqual(gc.parse_secs("1:02:03"), 3723)
        rows = dict(gc.rows({"timer": t})[1:])
        self.assertEqual((rows["Timer down"], float(rows["Timer secs"])), ("1", 300))


class PackTests(unittest.TestCase):
    def test_untouched_graphics_are_brought_up_to_date(self):
        from gfxengine import pack
        tmp = tempfile.mkdtemp()
        try:
            starter = os.path.join(tmp, "starter")
            os.makedirs(os.path.join(starter, "assets"))
            Image.new("RGB", (4, 4)).save(os.path.join(starter, "assets", "new.png"))
            old = blank_comp("Board")
            old["layers"].append(blank_layer("text", text="v1"))
            kept = blank_comp("Mine")
            new = json.loads(json.dumps(old))
            new["layers"][0]["text"] = "v2"
            new["layers"].append(dict(blank_layer("image"), src="assets/new.png"))
            mine_new = dict(kept, w=10)
            with open(os.path.join(starter, "project.json"), "w") as f:
                json.dump({"compositions": [new, mine_new], "global": {"sponsors": [{"logo": "assets/new.png", "secs": 5}]},
                           "pack_history": {"Board": [pack.signature(old)], "Mine": [pack.signature(kept)]}}, f)
            ws = Workspace(os.path.join(tmp, "ws"))
            changed = json.loads(json.dumps(kept))
            changed["layers"].append(blank_layer("text"))                  # changed in Composer: left alone
            ws.data["compositions"] = [json.loads(json.dumps(old)), changed]
            self.assertEqual(pack.upgrade(ws, starter), ["Board"])
            board = ws.data["compositions"][0]
            self.assertEqual((board["id"], board["layers"][0]["text"]), (old["id"], "v2"))
            self.assertTrue(os.path.isfile(os.path.join(ws.folder, "assets", "new.png")))
            self.assertEqual(ws.data["compositions"][1], changed)
            self.assertEqual(ws.data["global"]["sponsors"][0]["logo"], "assets/new.png")
            self.assertEqual(pack.upgrade(ws, starter), [])
            ws.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_starter_is_linked(self):
        with open(os.path.join(ROOT, "starter", "project.json"), encoding="utf-8") as f:
            data = json.load(f)
        comps = {c["name"]: c for c in data["compositions"]}
        for name in ("Schedule", "Team stats", "Player stats"):
            self.assertTrue(any(l["name"] == "Background loop" for l in comps[name]["layers"]), name)
        srcs = {l.get("src") for l in comps["Scorebug & footer"]["layers"]}
        self.assertTrue({"{{Global!Left logo}}", "{{Global!Right logo}}", "{{Sponsors}}"} <= srcs)
        self.assertTrue(data["global"]["sponsors"])
        for sp in data["global"]["sponsors"]:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "starter", sp["logo"])), sp)
        self.assertTrue(data["pack_history"])
        kinds = {c["name"]: c.get("kind") for c in data["compositions"]}
        self.assertEqual((kinds["Schedule"], kinds["Caster lower third"], kinds["Scorebug & footer"]), ("board", "lower third", "overlay"))
        self.assertTrue(any(l["type"] == "bracket" for l in comps["Top 8 bracket"]["layers"]))
        self.assertTrue(any("{{Tournament!Group A 1st}}" == l.get("text") for l in comps["Group bracket"]["layers"]))
        self.assertTrue(data["global"]["ticker"])
        self.assertFalse({"Title screen", "Starting soon", "Team graphic", "Sponsor footer"} & set(comps))
        self.assertEqual(len(data["global"]["sponsors"]), 8)
        self.assertTrue(any(l.get("src") == "{{Sponsors all}}" for l in comps["Team stats"]["layers"]))
        sch = comps["Schedule"]["layers"]
        self.assertEqual(len([l for l in sch if l.get("show") == "{{Schedule!Match 3 show}}"]), 6)
        self.assertTrue(any(l.get("src") == "{{Global!Left logo}}" for l in sch))
        self.assertTrue(all(l.get("divider") for l in sch if l.get("scroll")))
        self.assertEqual(len(data["global"]["schedule"]["matches"]), 3)
        self.assertEqual([l["text"] for l in sch if l["name"].startswith("Clock")], ["{{clock}}", "{{Global!Clock label}}"])
        bug = comps["Timer bug"]
        self.assertEqual([l.get("text") for l in bug["layers"]], [None, "HIGHLIGHTS", "{{timer}}"])
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "starter", bug["layers"][0]["src"])))
        self.assertIn("Timer bug", data["pack_new"])


class PackUpgradeTests(unittest.TestCase):
    def test_removed_graphics_and_new_sponsors(self):
        from gfxengine import pack
        tmp = tempfile.mkdtemp()
        try:
            old = dict(blank_comp("Title screen"), id="c1")
            edited = dict(blank_comp("Starting soon"), id="c2", width=1280)
            kept = dict(blank_comp("Schedule"), id="c3")
            starter = os.path.join(tmp, "starter")
            os.makedirs(os.path.join(starter, "assets", "sponsors"))
            with open(os.path.join(starter, "assets", "sponsors", "Intel logo.png"), "wb") as f:
                f.write(b"png")
            with open(os.path.join(starter, "project.json"), "w") as f:
                json.dump({"compositions": [kept], "pack_removed": ["Title screen", "Starting soon"],
                           "pack_history": {"Title screen": [pack.signature(old)], "Starting soon": [pack.signature(blank_comp("Starting soon"))]},
                           "global": {"sponsor_set": 2, "sponsors": [{"logo": "assets/sponsors/Intel logo.png", "secs": 10}]}}, f)
            ws = Workspace(os.path.join(tmp, "ws"), starter="")
            ws.data["compositions"] = [old, edited, kept]
            ws.data["global"] = {"sponsors": [{"logo": "assets/sponsors/Subway.png", "secs": 10}]}
            pack.upgrade(ws, starter)
            # The untouched graphic goes, the edited one stays; the old sponsors are replaced.
            self.assertEqual([c["name"] for c in ws.data["compositions"]], ["Starting soon", "Schedule"])
            self.assertEqual([sp["logo"] for sp in ws.data["global"]["sponsors"]], ["assets/sponsors/Intel logo.png"])
            self.assertTrue(os.path.isfile(os.path.join(tmp, "ws", "assets", "sponsors", "Intel logo.png")))
            # Sponsors someone chose themselves stay.
            ws.data["global"]["sponsors"] = [{"logo": "assets/sponsors/Mine.png", "secs": 5}]
            pack.upgrade(ws, starter)
            self.assertEqual(ws.data["global"]["sponsors"][0]["logo"], "assets/sponsors/Mine.png")
            # A graphic new to the pack: added once, and stays deleted if deleted.
            with open(os.path.join(starter, "project.json")) as f:
                project = json.load(f)
            project["compositions"].append(dict(blank_comp("Timer bug"), id="c9"))
            project["pack_new"] = ["Timer bug"]
            with open(os.path.join(starter, "project.json"), "w") as f:
                json.dump(project, f)
            self.assertEqual(pack.upgrade(ws, starter), ["Timer bug"])
            ws.data["compositions"] = [c for c in ws.data["compositions"] if c["name"] != "Timer bug"]
            self.assertEqual(pack.upgrade(ws, starter), [])
            self.assertNotIn("Timer bug", [c["name"] for c in ws.data["compositions"]])
            ws.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ScheduleTests(unittest.TestCase):
    def test_rows(self):
        from gfxengine import schedule
        s = {"count": 2, "matches": [{"tournament": "NACE", "game": "ROCKET LEAGUE", "type": "PLAYOFFS", "team1": "A", "team2": "B",
                                      "date": "2026-11-11", "time": "09:05"}, {"game": "VALORANT", "date": "bad"},
                                     {"tournament": "Third"}]}
        r = dict(schedule.rows(s)[1:])
        self.assertEqual((r["Count"], r["Match 1 game"], r["Match 1 teams"], r["Match 1 when"]), ("2", "ROCKET LEAGUE | PLAYOFFS", "A vs. B", "WED 11/11  |  9:05 AM"))
        self.assertEqual((r["Match 2 show"], r["Match 2 when"], r["Match 3 show"]), ("1", "", ""))
        self.assertEqual(schedule.clean({"count": 7})["count"], 3)
        self.assertEqual(dict(schedule.rows({})[1:])["Match 1 show"], "")


class TournamentTests(unittest.TestCase):
    def test_knockout_winners_go_through(self):
        from gfxengine import tournament
        t = tournament.clean({"top": {"size": 8, "teams": ["A", "B", "C", "D", "E", "", "G", "H"],
                                      "scores": {"R1 M1": [2, 0], "R1 M2": ["1", "2"], "R1 M4": ["3", "3"], "R2 M1": ["2", "1"]}}})
        rows = dict(tournament.rows(t, lambda n: {"short": n.lower(), "logo": f"library/teams/{n}.png"} if n == "A" else None)[1:])
        self.assertEqual(rows["Top teams"], "8")
        self.assertEqual((rows["Top R2 M1 team 1"], rows["Top R2 M1 team 2"]), ("A", "D"))
        self.assertEqual(rows["Top R2 M2 team 1"], "E")                  # nobody against it: through
        self.assertEqual(rows["Top R2 M2 team 2"], "")                   # a draw: not decided
        self.assertEqual((rows["Top R3 M1 team 1"], rows["Top R3 M1 team 1 logo"], rows["Top R3 M1 team 1 short"]),
                         ("A", "library/teams/A.png", "a"))
        self.assertEqual((rows["Top semi 1"], rows["Top semi 1 score"], rows["Top final 1"]), ("A", "2", "A"))
        self.assertEqual(rows["Top champion"], "")
        t["top"]["size"] = 16
        rows16 = dict(tournament.rows(t)[1:])
        self.assertIn("Top R4 M1 team 1", rows16)
        self.assertEqual(rows16["Top R2 M3 team 1"], "")                 # (16: the 9th team on is empty)
        self.assertEqual(tournament.clean({"top": {"size": 12}})["top"]["size"], 8)

    def test_groups(self):
        from gfxengine import tournament
        g = {"name": "GROUP A", "teams": ["A", "B", "C", "D"],
             "scores": {"Opening 1": ["2", "1"], "Opening 2": ["0", "2"], "Winners": ["1", "2"], "Elimination": ["2", "0"], "Decider": ["0", "2"]}}
        rows = dict(tournament.rows({"groups": [g]})[1:])
        self.assertEqual((rows["Group A Winners team 1"], rows["Group A Winners team 2"]), ("A", "D"))
        self.assertEqual((rows["Group A Elimination team 1"], rows["Group A Elimination team 2"]), ("B", "C"))
        self.assertEqual((rows["Group A Decider team 1"], rows["Group A Decider team 2"]), ("A", "B"))
        self.assertEqual((rows["Group A 1st"], rows["Group A 2nd"]), ("D", "B"))
        self.assertEqual(rows["Group B name"], "GROUP B")


class TeamsTests(unittest.TestCase):
    def test_csv(self):
        from gfxengine.teams import Teams, roster_rows
        tmp = tempfile.mkdtemp()
        try:
            teams = Teams(tmp)
            n = teams.import_csv("Team,Abbreviation,Logo,Color\nSt. Clair Saints,SCC,saints.png,0b6b3a\nGeorge Mason,GMU,https://x/gmu.png,#123456\n,,,\n")
            self.assertEqual(n, 2)
            self.assertEqual(teams.find("scc"), {"name": "St. Clair Saints", "short": "SCC", "logo": "library/teams/saints.png", "color": "#0b6b3a",
                                                  "game": "", "players": []})
            self.assertEqual(teams.find("george mason")["logo"], "https://x/gmu.png")
            teams.import_csv("Name,Short name\nSt. Clair Saints,SAINTS\n")      # updates, keeps the rest
            again = Teams(tmp)                                                   # (read back from the CSV)
            self.assertEqual((len(again.list()), again.find("St. Clair Saints")["short"], again.find("St. Clair Saints")["color"]),
                             (2, "SAINTS", "#0b6b3a"))
            logo = again.save_logo("Humber Hawks", "hawks.png", b"png")
            self.assertEqual(logo, "library/teams/Humber Hawks.png")
            self.assertTrue(os.path.isfile(os.path.join(tmp, "teams", "Humber Hawks.png")))
            self.assertEqual(again.find("Humber Hawks")["logo"], logo)
            with self.assertRaises(ValueError):
                again.import_csv("Name,Short name\n")
            # The same school in two games, with rosters.
            again.import_csv("Name,Game,Player 1,Player 1 ID,Player 1 country,Player 1 headshot,Player 2 ID,Player 2 country\n"
                             "St. Clair Saints,Rocket League,Jason,Jazii,Germany,jazii.png,Pzy,at\n"
                             "St. Clair Saints,Valorant,,Ace,ca,,,\n")
            rl = again.find("St. Clair Saints", "rocket league")
            self.assertEqual(rl["players"][0], {"name": "Jason", "ign": "Jazii", "country": "de", "photo": "library/teams/jazii.png"})
            self.assertEqual(rl["players"][1]["country"], "at")
            self.assertEqual(again.find("St. Clair Saints", "Valorant")["players"][0]["ign"], "Ace")
            self.assertEqual(len(again.list()), 5)
            back = Teams(tmp).find("St. Clair Saints", "Rocket League")
            self.assertEqual((back["short"], back["players"][1]["ign"]), ("", "Pzy"))
            self.assertIn("Player 5 headshot", again.csv_text().splitlines()[0])
            r = dict(roster_rows(rl, "left", ["", "", "Stats3"])[1:])
            self.assertEqual((r["Player 1"], r["Player 1 flag"], r["Player 2"], r["Player 3"], r["No headshots"]),
                             ("Jason", "flags/de.svg", "Pzy", "Stats3", ""))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ServerTests(unittest.TestCase):
    def test_engine(self):
        from gfxengine.app import Engine, start
        tmp = tempfile.mkdtemp()
        settings = Settings(os.path.join(tmp, "settings.json"))
        settings.update({"http_port": 8796})
        engine = Engine(settings, os.path.join(tmp, "workspaces"), starter=os.path.join(ROOT, "starter"),
                        library_dir=os.path.join(tmp, "library"), legacy_dir=os.path.join(tmp, "none"))
        engine.updater.check_in_background = lambda: None
        start(engine)
        base = "http://127.0.0.1:8796"

        def get(path):
            with urllib.request.urlopen(base + path, timeout=10) as r:
                return r.read()

        def post(path, body, headers=None):
            req = urllib.request.Request(base + path, json.dumps(body).encode() if not isinstance(body, bytes) else body,
                                         headers or {"Content-Type": "application/json"})
            return json.loads(urllib.request.urlopen(req, timeout=30).read())
        try:
            for path in ("/control", "/output", "/runtime.js", "/control.js", "/composer.js", "/pages.js",
                         "/control.css", "/vendor/lottie.min.js", "/fonts/Inter.ttf", "/assets-ui/icon.png", "/home.js",
                         "/assets-ui/logo.png", "/assets-ui/badge.png"):
                self.assertTrue(get(path), path)
            state = json.loads(get("/api/state"))
            self.assertGreaterEqual(len(state["project"]["compositions"]), 4)   # the starter graphics
            self.assertEqual(json.loads(get("/api/hello"))["app"], "scc-gfx-engine")
            # A new graphic with a text field, cued and taken.
            comp = blank_comp("Test")
            layer = blank_layer("text", field="Name", text="{{Match!Left}}")
            comp["layers"].append(layer)
            cid = post("/api/comp/new", {"comp": comp})["comp"]["id"]
            post("/api/cue", {"id": cid})
            post("/api/values", {"id": cid, "values": {"Name": "Owen"}})
            post("/api/take", {"transition": "cut"})
            live = json.loads(get("/api/state"))["live"]
            self.assertIn(cid, live["program"]["on"])
            self.assertIn("now", json.loads(get("/api/state"))["data"])
            # The stream: everything first, then only what changed (a cue: not the project).
            with urllib.request.urlopen(base + "/api/stream", timeout=10) as r:
                def message():
                    while True:
                        line = r.readline().decode()
                        if line.startswith("data: "):
                            return json.loads(line[6:])
                first = message()
                self.assertTrue({"project", "live", "data"} <= set(first))
                post("/api/cue", {"id": cid, "on": False})
                after = message()
                self.assertIn("live", after)
                self.assertNotIn("project", after)
            self.assertEqual(live["program"]["values"][cid]["Name"], "Owen")
            # Bitfocus Companion: Preview, Program, Take and the quick functions.
            comp_state = json.loads(get("/api/companion"))
            mine = next(g for g in comp_state["graphics"] if g["id"] == cid)
            self.assertEqual((mine["name"], mine["program"]), ("Test", True))
            r = post("/api/companion", {"action": "program", "id": "test", "mode": "toggle"})   # (by name)
            self.assertFalse(next(g for g in r["graphics"] if g["id"] == cid)["program"])
            r = post("/api/companion", {"action": "preview", "id": cid, "mode": "on"})
            self.assertEqual((r["variables"]["preview"], r["states"]["preview_any"]), ("Test", True))
            r = post("/api/companion", {"action": "take", "transition": "cut"})
            self.assertIn("Test", r["variables"]["program"])
            for quick in ("score_left_up", "score_left_up", "score_right_up", "score_left_down", "clock_brb", "caster_3"):
                r = post("/api/companion", {"action": "run", "id": quick})
            self.assertEqual((r["variables"]["left_score"], r["variables"]["right_score"]), ("1", "1"))
            self.assertTrue(r["states"]["clock_brb"] and r["states"]["caster_3"])
            r = post("/api/companion", {"action": "clear", "bus": "both"})
            self.assertFalse(r["states"]["program_any"] or r["states"]["preview_any"])
            post("/api/companion", {"action": "run", "id": "score_reset"})
            with self.assertRaises(urllib.error.HTTPError):
                post("/api/companion", {"action": "preview", "id": "no such graphic"})
            post("/api/cue", {"id": cid})
            post("/api/take", {"transition": "cut"})
            # Files: a picture, and a CSV (which becomes a data source).
            buf = io.BytesIO()
            Image.new("RGB", (40, 20), "red").save(buf, "PNG")
            r = post("/api/upload", buf.getvalue(), {"X-Filename": "logo%20one.png"})
            self.assertEqual(r["assets"], ["assets/logo one.png"])
            self.assertEqual(get("/assets/logo%20one.png"), buf.getvalue())
            r = post("/api/upload", b"Team,Score\nSCC,5\n", {"X-Filename": "scores.csv"})
            self.assertEqual(r["sources"][0]["path"], "assets/scores.csv")
            deadline = time.time() + 10
            while time.time() < deadline and json.loads(get("/api/state"))["data"]["tables"].get("scores") != [["Team", "Score"], ["SCC", "5"]]:
                time.sleep(0.2)
            self.assertEqual(json.loads(get("/api/state"))["data"]["tables"]["scores"], [["Team", "Score"], ["SCC", "5"]])
            # Refused files say what to do instead.
            with self.assertRaises(urllib.error.HTTPError) as err:
                post("/api/upload", b"x", {"X-Filename": "intro.aep"})
            self.assertIn("Lottie", json.loads(err.exception.read())["error"])
            # Video in parts (the outputs seek in it).
            stinger = next(t for t in state["project"]["transitions"] if t["type"] == "stinger")
            req = urllib.request.Request(base + "/" + stinger["src"], headers={"Range": "bytes=0-99"})
            with urllib.request.urlopen(req, timeout=10) as r:
                self.assertEqual(r.status, 206)
                self.assertEqual(len(r.read()), 100)
            # HTML export: the page, the player and the graphic's files.
            first = state["project"]["compositions"][0]
            z = zipfile.ZipFile(io.BytesIO(get("/api/export?comps=" + first["id"])))
            names = set(z.namelist())
            self.assertTrue({"index.html", "gfx-data.js", "runtime.js", "vendor/lottie.min.js"} <= names)
            srcs = {l["src"] for l in first["layers"] if l.get("src") and "{{" not in l["src"]}
            self.assertTrue(srcs and srcs <= names, srcs - names)
            if any(l.get("src") == "{{Global!BG loop}}" for l in first["layers"]):
                self.assertIn("loops/scc-bg-loop.webm", names)     # (from the data)
            self.assertIn('src="gfx-data.js"', z.read("index.html").decode())
            # Transitions are checked.
            with self.assertRaises(urllib.error.HTTPError):
                post("/api/transitions", {"transitions": [{"type": "spin"}]})
            # Fonts go in the library every workspace shares, and are known by their other names.
            with open(os.path.join(ROOT, "web", "fonts", "Inter.ttf"), "rb") as f:
                font = f.read()
            r = post("/api/upload", font, {"X-Filename": "MyFont.ttf"})
            self.assertEqual(r["assets"], ["library/fonts/MyFont.ttf"])
            self.assertEqual(get("/library/fonts/MyFont.ttf"), font)
            fonts = json.loads(get("/api/state"))["fonts"]
            mine = next(f for f in fonts if f["path"] == "library/fonts/MyFont.ttf")
            self.assertIn("MyFont", mine["aliases"])
            # Global configuration: set, a logo, and what HUDs read.
            g = post("/api/global", {"global": {"left": {"name": "St. Clair Saints", "short": "SCC"}, "best_of": 5}})["global"]
            self.assertEqual((g["left"]["short"], g["best_of"]), ("SCC", 5))
            g = post("/api/global/logo?side=right&name=gmu.png", buf.getvalue(), {"X-Filename": "gmu.png"})["global"]
            self.assertTrue(g["right"]["logo"].startswith("assets/logos/"))
            hud_view = json.loads(get("/api/global"))["global"]
            self.assertEqual(hud_view["right"]["logo_url"], base + "/" + g["right"]["logo"])
            tables = json.loads(get("/api/state"))["data"]["tables"]
            self.assertIn(["Left short", "SCC"], tables["Global"])
            # The tournament logo, sponsors and background loop.
            g = post("/api/global/logo?side=tournament&name=t.png", buf.getvalue(), {"X-Filename": "t.png"})["global"]
            self.assertTrue(g["tournament_logo"].startswith("assets/logos/"))
            g = post("/api/global/logo?side=sponsor&name=s.png", buf.getvalue(), {"X-Filename": "s.png"})["global"]
            self.assertEqual(g["sponsors"][-1]["logo"].split("/")[-1][-4:], ".png")
            with self.assertRaises(urllib.error.HTTPError):
                post("/api/global/logo?side=bgloop&name=x.png", buf.getvalue(), {"X-Filename": "x.png"})
            g = post("/api/global", {"global": {"bgloop": {"color": "#ff0000"}}})["global"]
            self.assertEqual((g["bgloop"]["color"], g["bgloop"]["on"]), ("#ff0000", True))
            tables = json.loads(get("/api/state"))["data"]["tables"]
            self.assertIn(["BG loop colour", "#ff0000"], tables["Global"])
            self.assertEqual(tables["Sponsors"][-1][0], g["sponsors"][-1]["logo"])
            # The ticker, the team list and the tournament.
            post("/api/global", {"global": {"ticker": ["Welcome", " ", "Follow us"]}})
            self.assertIn(["Ticker", "Welcome  |  Follow us  |  "], json.loads(get("/api/state"))["data"]["tables"]["Global"])
            r = post("/api/teams/import", b"Name,Short name\nHumber Hawks,HUM\nDurham Lords,DUR\n", {"X-Filename": "teams.csv"})
            self.assertEqual(r["added"], 2)
            r = post("/api/teams/logo?team=Humber%20Hawks&name=h.png", buf.getvalue(), {"X-Filename": "h.png"})
            self.assertEqual(get("/" + urllib.parse.quote(r["logo"])), buf.getvalue())
            self.assertIn("Humber Hawks,HUM", get("/library/teams.csv").decode())
            post("/api/global", {"global": {"tournament": {"top": {"size": 8, "teams": ["Humber Hawks", "Durham Lords"],
                                                                   "scores": {"R1 M1": ["3", "1"]}}}}})
            s2 = json.loads(get("/api/state"))
            tn = dict(s2["data"]["tables"]["Tournament"][1:])
            self.assertEqual((tn["Top R2 M1 team 1"], tn["Top R2 M1 team 1 short"], tn["Top R2 M1 team 1 logo"]), ("Humber Hawks", "HUM", r["logo"]))
            self.assertEqual(len(s2["teams"]), 2)
            post("/api/teams", {"teams": s2["teams"][:1]})
            self.assertEqual([t["name"] for t in json.loads(get("/api/state"))["teams"]], ["Humber Hawks"])
            # The clock: a countdown for Starting Soon.
            post("/api/global", {"global": {"clock": {"mode": "soon", "until": "19:30"}}})
            gl = dict(json.loads(get("/api/state"))["data"]["tables"]["Global"][1:])
            self.assertEqual((gl["Clock mode"], gl["Clock until"], gl["Clock label"], gl["Clock zone"]), ("soon", "19:30", "STARTING SOON", "EST"))
            post("/api/global", {"global": {"clock": {"mode": "nope", "until": "later"}}})
            self.assertEqual(json.loads(get("/api/state"))["global"]["clock"]["mode"], "time")
            # The upcoming schedule.
            post("/api/global", {"global": {"schedule": {"count": 1, "matches": [
                {"tournament": "NACE", "game": "VALORANT", "team1": "Humber Hawks", "team2": "SCC", "date": "2026-10-20", "time": "19:30"},
                {"tournament": "CRL"}]}}})
            sc = dict(json.loads(get("/api/state"))["data"]["tables"]["Schedule"][1:])
            self.assertEqual((sc["Count"], sc["Match 1 when"], sc["Match 1 team 1 logo"], sc["Match 1 show"], sc["Match 2 show"]),
                             ("1", "TUE 10/20  |  7:30 PM", r["logo"], "1", ""))
            # A game HUD's data: its own table, and the series score into Global.
            post("/api/ingest", {"source": "League HUD", "game": "lol", "fields": {"Blue kills": 7, "Game time": "12:34"},
                                 "series": {"left": {"score": 2}, "right": {"score": 1}, "best_of": 5}})
            state2 = json.loads(get("/api/state"))
            self.assertIn(["Blue kills", "7"], state2["data"]["tables"]["League HUD"])
            self.assertEqual((state2["global"]["left"]["score"], state2["global"]["right"]["score"]), (2, 1))
            self.assertIn(["Game", "4"], state2["data"]["tables"]["Global"])
            self.assertIn("League HUD", state2["data"]["feeds"])
            post("/api/ingest", {"source": "League HUD", "game": "lol", "fields": {"P1 NAME": "Faker", "P1 KDA": "5/0/2"}})
            stats = dict(json.loads(get("/api/state"))["data"]["tables"]["Stats"][1:])
            self.assertEqual((stats["Status"], stats["MVP"], stats["MVP team"]), ("LIVE", "Faker", "St. Clair Saints"))
            post("/api/stats/clear", {})
            self.assertEqual(dict(json.loads(get("/api/state"))["data"]["tables"]["Stats"][1:])["Status"], "")
            # Workspaces: a new empty one with a picture, opened; the SCC pack added to it; back again.
            first_id = state2["workspace"]["id"]
            wid = post("/api/workspaces/create", {"name": "NACE Spring", "template": "empty", "open": False})["id"]
            post(f"/api/workspaces/picture?id={wid}&name=cover.png", buf.getvalue(), {"X-Filename": "cover.png"})
            listed = {w["id"]: w for w in json.loads(get("/api/workspaces"))["workspaces"]}
            self.assertTrue(listed[wid]["picture"])
            self.assertEqual(get(f"/api/workspace-picture/{wid}"), buf.getvalue())
            post("/api/workspaces/open", {"id": wid})
            s3 = json.loads(get("/api/state"))
            self.assertEqual((s3["workspace"]["id"], len(s3["project"]["compositions"])), (wid, 0))
            self.assertEqual(s3["global"]["left"]["name"], "")          # its own global configuration
            self.assertTrue(any(f["path"] == "library/fonts/MyFont.ttf" for f in s3["fonts"]))   # the same fonts
            pack = json.loads(get("/api/pack"))["graphics"]
            added = post("/api/pack/import", {})["added"]
            self.assertEqual(len(added), len(pack))
            s3 = json.loads(get("/api/state"))
            comp0 = s3["project"]["compositions"][0]
            src = next(l["src"] for l in comp0["layers"] if l.get("src"))
            self.assertTrue(get("/" + urllib.parse.quote(src)))
            with self.assertRaises(urllib.error.HTTPError):
                post("/api/workspaces/delete", {"id": wid})                # (it's open)
            post("/api/workspaces/open", {"id": first_id})
            post("/api/workspaces/delete", {"id": wid})
            self.assertNotIn(wid, [w["id"] for w in json.loads(get("/api/workspaces"))["workspaces"]])
            self.assertEqual(settings.get()["workspace"], first_id)
            # The stream sends the whole state.
            stream = urllib.request.urlopen(base + "/api/stream", timeout=5)
            line = b""
            while not line.startswith(b"data:"):
                line = stream.readline()
            self.assertIn("live", json.loads(line[5:]))
            stream.close()
        finally:
            engine.stop()
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()


class HudBoardTests(unittest.TestCase):
    def test_hud_board_gets_the_backdrop_and_loop(self):
        from gfxengine.app import Engine
        tmp = tempfile.mkdtemp()
        try:
            engine = Engine(Settings(os.path.join(tmp, "settings.json")), os.path.join(tmp, "workspaces"),
                            starter=os.path.join(ROOT, "starter"), library_dir=os.path.join(tmp, "library"),
                            legacy_dir=os.path.join(tmp, "none"))
            if not engine.ws:
                engine.create_workspace("Test")
            hud = lambda bd: {"port": 8778, "graphics": [
                {"id": "agent-select", "name": "Agent select", "path": "/agent-select", "kind": "board"},
                {"id": "map-bans-bo3", "name": "Map bans Bo3", "path": "/map-bans?bo=3", "kind": "board", "backdrop": bd}]}
            engine.ingest({"source": "VALORANT HUD", "game": "valorant", "hud": hud(False)}, "127.0.0.1")
            comps = {c.get("hud"): c for c in engine.ws.data["compositions"] if c.get("hud")}
            self.assertEqual([l["type"] for l in comps["VALORANT HUD/map-bans-bo3"]["layers"]], ["web"])
            # A HUD that asks for the backdrop later: added to the graphic it made before.
            engine.ingest({"source": "VALORANT HUD", "game": "valorant", "hud": hud(True)}, "127.0.0.1")
            comps = {c.get("hud"): c for c in engine.ws.data["compositions"] if c.get("hud")}
            names = [l["name"] for l in comps["VALORANT HUD/map-bans-bo3"]["layers"]]
            self.assertEqual(names, ["Layer 1", "Background loop", "Map bans Bo3"])
            self.assertEqual(comps["VALORANT HUD/map-bans-bo3"]["layers"][1]["src"], "{{Global!BG loop}}")
            self.assertEqual([l["type"] for l in comps["VALORANT HUD/agent-select"]["layers"]], ["web"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
