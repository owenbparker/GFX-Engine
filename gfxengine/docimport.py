"""Design files to new graphics (Composer's Import button).

    .psd .psb        Photoshop: layers, text kept as text (see psdimport)
    .ora             OpenRaster (Krita, MyPaint, Pinta...): its layers as pictures
    .png .jpg ...    one picture, as a graphic of its own
    .afdesign .afphoto .afpub .af, .kra, .xcf, .procreate, .clip ...
                     refused, saying how to save a .psd from that app (their
                     own formats aren't published, so they can't be read)
"""

import os
import re
import xml.etree.ElementTree as ET
import zipfile

from .log import log
from .project import ANIM_NONE, blank_comp, new_id
from .psdimport import auto_animate, guess_kind, import_psd

AFFINITY = ("To bring in an Affinity file, save it as a Photoshop file first: in Affinity, File > Export > PSD, "
            "pick the \"PSD (Preserve Editability)\" preset, then import that .psd. Its layers and text come "
            "across, and text stays editable.")
SAVE_AS_PSD = {
    ".afdesign": AFFINITY, ".afphoto": AFFINITY, ".afpub": AFFINITY, ".af": AFFINITY,
    ".kra": "Krita files can't be read directly: in Krita, File > Save As and pick Photoshop (.psd) "
            "or OpenRaster (.ora), then import that.",
    ".xcf": "GIMP files can't be read directly: in GIMP, File > Export As and name it .psd, then import that.",
    ".procreate": "Procreate files can't be read directly: in Procreate, Share > PSD, then import that.",
    ".clip": "Clip Studio files can't be read directly: in Clip Studio Paint, File > Save As and pick .psd, "
             "then import that.",
    ".ptg": "ArtRage files can't be read directly: in ArtRage, File > Export Layers to PSD, then import that.",
    ".ai": "Illustrator files can't be read directly: File > Export > Export As > Photoshop (.psd) "
           "with \"Write Layers\" on, then import that.",
    ".sketch": "Sketch files can't be read directly: export the artboard as PNG or SVG, then import that.",
    ".fig": "Figma files can't be read directly: export the frame as PNG or SVG, then import that.",
}
LAYERED = (".psd", ".psb", ".ora")
PICTURES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".avif", ".bmp")
ACCEPT = LAYERED + PICTURES + tuple(SAVE_AS_PSD)

BLENDS = {"svg:multiply": "multiply", "svg:screen": "screen", "svg:overlay": "overlay", "svg:darken": "darken",
          "svg:lighten": "lighten", "svg:color-dodge": "color-dodge", "svg:color-burn": "color-burn",
          "svg:hard-light": "hard-light", "svg:soft-light": "soft-light", "svg:difference": "difference",
          "svg:exclusion": "exclusion", "svg:hue": "hue", "svg:saturation": "saturation", "svg:color": "color",
          "svg:luminosity": "luminosity", "svg:plus": "plus-lighter"}


def importable(name):
    return name.lower().endswith(ACCEPT)


def import_file(path, workspace, name):
    """Makes a graphic from a design file. Returns (composition, [fonts it uses])."""
    ext = os.path.splitext(name.lower())[1]
    title = os.path.splitext(os.path.basename(name))[0]
    if ext in SAVE_AS_PSD:
        raise ValueError(SAVE_AS_PSD[ext])
    if ext in (".psd", ".psb"):
        return import_psd(path, workspace, title)
    if ext == ".ora":
        return import_ora(path, workspace, title), []
    if ext in PICTURES:
        return import_picture(path, workspace, title, ext), []
    raise ValueError(f"{os.path.basename(name)} can't be imported as a graphic: use a .psd (Photoshop, "
                     "or saved as Photoshop from Affinity, Krita, GIMP, Procreate ...), .ora or a picture.")


def _layer(name, x, y, w, h, src, opacity=1, visible=True, blend="normal"):
    return {"id": new_id("l"), "name": name, "type": "image", "x": round(x), "y": round(y), "w": round(w), "h": round(h),
            "opacity": round(opacity, 3), "rotation": 0, "visible": visible, "blend": blend, "field": "",
            "anim": {"in": dict(ANIM_NONE), "out": dict(ANIM_NONE)}, "src": src, "fit": "fill", "loop": True}


def _safe(name, used):
    base = re.sub(r"[^\w\- ]+", "_", name).strip() or "layer"
    out, n = base, 2
    while out.lower() in used:
        out, n = f"{base}-{n}", n + 1
    used.add(out.lower())
    return out


def import_ora(path, workspace, name):
    """OpenRaster: a zip of PNGs placed by stack.xml (top layer first)."""
    from PIL import Image

    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("stack.xml"))
        width, height = int(root.get("w", 1920)), int(root.get("h", 1080))
        comp = blank_comp(name)
        comp["width"], comp["height"] = width, height
        folder_rel, folder = workspace.unique_asset(name)
        os.makedirs(folder, exist_ok=True)
        sub = folder_rel[len("assets/"):]
        used = set()

        def walk(stack, ox=0, oy=0, opacity=1.0, visible=True):
            # Bottom to top, as the graphic stacks them.
            for el in reversed(list(stack)):
                op = opacity * float(el.get("opacity", 1))
                vis = visible and el.get("visibility", "visible") != "hidden"
                x, y = ox + int(float(el.get("x", 0))), oy + int(float(el.get("y", 0)))
                if el.tag == "stack":
                    yield from walk(el, x, y, op, vis)
                elif el.tag == "layer" and el.get("src", "").lower().endswith(".png"):
                    yield el, x, y, op, vis

        for el, x, y, op, vis in walk(root):
            label = el.get("name") or os.path.splitext(os.path.basename(el.get("src")))[0]
            try:
                with z.open(el.get("src")) as f:
                    image = Image.open(f)
                    image.load()
                box = image.getbbox() if image.mode in ("RGBA", "LA", "PA") else (0, 0) + image.size
                if not box:
                    continue   # empty
                image = image.crop(box)
                fname = _safe(label, used)
                image.save(os.path.join(folder, fname + ".png"), optimize=True)
                comp["layers"].append(_layer(label, x + box[0], y + box[1], image.size[0], image.size[1],
                                             f"assets/{sub}/{fname}.png", op, vis,
                                             BLENDS.get(el.get("composite-op", ""), "normal")))
            except Exception as e:
                log(f"{name}: skipped layer {label!r} ({e})", "warn")
    if not comp["layers"]:
        raise ValueError(f"{name} has no layers with pictures in it")
    auto_animate(comp["layers"], width, height)
    comp["kind"] = guess_kind(comp["layers"])
    log(f"Imported {name}: {len(comp['layers'])} layers")
    return comp


def import_picture(path, workspace, name, ext):
    """One picture as a graphic: full screen if it's screen sized, otherwise
    centred at its own size (shrunk to fit)."""
    rel, dest = workspace.unique_asset(name + ext)
    w = h = None
    if ext != ".svg":
        from PIL import Image
        with Image.open(path) as image:
            w, h = image.size
    os.replace(path, dest)
    comp = blank_comp(name)
    if not w or not h:
        w, h = 1920, 1080
    scale = min(1, 1920 / w, 1080 / h)
    w, h = w * scale, h * scale
    comp["layers"].append(_layer(name, (1920 - w) / 2, (1080 - h) / 2, w, h, rel))
    comp["layers"][0]["fit"] = "contain"
    auto_animate(comp["layers"])
    comp["kind"] = guess_kind(comp["layers"])
    log(f"Imported {name} as a graphic")
    return comp
