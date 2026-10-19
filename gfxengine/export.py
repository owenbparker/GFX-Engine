"""HTML export: graphics as a folder of plain web files (zipped) that play
without the engine - in OBS, vMix, CasparCG, SPX or any browser.

    index.html          the graphics (1920x1080, see-through)
    gfx-data.js         the graphics, their values and the data, as exported
    runtime.js, vendor/ the player
    assets/, fonts/     the files they use

index.html shows the graphics straight away. Its address can change that:
    ?autoplay=0         wait for play() (CasparCG and SPX call it)
    ?live=http://PC:8782  follow that engine's Program instead
    ?Field%20Name=Text  set a field
and the page has play(), stop(), next(), update(data) and remove() for
CasparCG / SPX templates.
"""

import io
import json
import os
import zipfile

from .config import WEB_DIR


def _walk_assets(value, found):
    if isinstance(value, dict):
        for v in value.values():
            _walk_assets(v, found)
    elif isinstance(value, list):
        for v in value:
            _walk_assets(v, found)
    elif isinstance(value, str) and value.startswith(("assets/", "library/")):
        found.add(value)


def build(workspace, assets, comp_ids, values=None, tables=None):
    """The export zip's bytes for these graphics."""
    project = workspace.get()
    comps = [c for c in project["compositions"] if c["id"] in comp_ids] or project["compositions"]
    values = {c["id"]: (values or {}).get(c["id"], {}) for c in comps}
    used = set()
    _walk_assets(comps, used)
    _walk_assets(values, used)
    _walk_assets(tables, used)     # (pictures a field takes from the data, e.g. {{Global!Left logo}})
    # The fonts the text uses (by PostScript name), from the assets.
    families = {l.get("font") for c in comps for l in c["layers"] if l.get("type") == "text"}
    fonts = [f for f in assets.fonts() if families & set(f.get("aliases") or [f["postscript"]])]
    used.update(f["path"] for f in fonts)
    data = {"name": project["name"], "compositions": comps, "values": values,
            "fonts": fonts, "tables": tables or {}, "standalone": True}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        with open(os.path.join(WEB_DIR, "output.html"), encoding="utf-8") as f:
            page = f.read()
        page = page.replace("<!--export-->", '<script src="gfx-data.js"></script>')
        z.writestr("index.html", page)
        z.writestr("gfx-data.js", "window.GFX_EXPORT = " + json.dumps(data, ensure_ascii=False) + ";\n")
        for rel in ("runtime.js", "vendor/lottie.min.js", "vendor/LICENSE-lottie.md"):
            z.write(os.path.join(WEB_DIR, rel), rel)
        for name in os.listdir(os.path.join(WEB_DIR, "fonts")):
            z.write(os.path.join(WEB_DIR, "fonts", name), "fonts/" + name)
        for rel in sorted(used):
            path = assets.path_of(rel)
            if not path or not os.path.isfile(path):
                continue
            if rel.endswith(".json") and rel.startswith("assets/"):
                # A Lottie animation: its images are beside it.
                folder = os.path.dirname(path)
                if os.path.normpath(folder) != os.path.normpath(workspace.assets_dir):
                    for dirpath, _, names in os.walk(folder):
                        for n in names:
                            full = os.path.join(dirpath, n)
                            z.write(full, "assets/" + os.path.relpath(full, workspace.assets_dir).replace(os.sep, "/"))
                    continue
            z.write(path, rel)
        z.writestr("README.txt", __doc__.strip() + "\n")
    return buf.getvalue()
