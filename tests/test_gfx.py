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
        live.take("cut")                                      # always there
        live.clear()
        self.assertEqual(live.get()["program"]["on"], [])
        with self.assertRaises(KeyError):
            live.take("nope")
        with self.assertRaises(KeyError):
            live.cue("nope")
        # Saved, and read back.
        self.assertEqual(Live(self.ws).get()["preview"]["on"], [self.a["id"], self.b["id"]])

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
            self.assertEqual(live["program"]["values"][cid]["Name"], "Owen")
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
            srcs = {l["src"] for l in first["layers"] if l.get("src")}
            self.assertTrue(srcs and srcs <= names, srcs - names)
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
            # A game HUD's data: its own table, and the series score into Global.
            post("/api/ingest", {"source": "League HUD", "game": "lol", "fields": {"Blue kills": 7, "Game time": "12:34"},
                                 "series": {"left": {"score": 2}, "right": {"score": 1}, "best_of": 5}})
            state2 = json.loads(get("/api/state"))
            self.assertIn(["Blue kills", "7"], state2["data"]["tables"]["League HUD"])
            self.assertEqual((state2["global"]["left"]["score"], state2["global"]["right"]["score"]), (2, 1))
            self.assertIn(["Game", "4"], state2["data"]["tables"]["Global"])
            self.assertIn("League HUD", state2["data"]["feeds"])
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
