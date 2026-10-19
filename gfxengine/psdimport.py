"""Photoshop files to compositions.

Each layer becomes a layer of the graphic: text layers stay text (same
font, size, colour, tracking and alignment, editable from Control), every
other layer becomes a PNG of its pixels (with its layer effects) at its
place on the canvas. Groups are flattened, keeping their visibility and
opacity. Layers named like "Layer 3" or "Rectangle 5 copy" are fixed;
others ("TEAM LEFT", "SPONSOR") are fields that can be changed from Control.
"""

import os
import re

from .log import log
from .project import ANIM_NONE, blank_comp, new_id

GENERIC = re.compile(r"^(layer|rectangle|ellipse|line|shape|group|polygon|path|vector|background|bg|color fill|"
                     r"gradient fill|pattern fill|brightness|levels|curves|hue|vibrance|exposure|copy)\b", re.I)

BLENDS = {"multiply": "multiply", "screen": "screen", "overlay": "overlay", "darken": "darken",
          "lighten": "lighten", "color_dodge": "color-dodge", "color_burn": "color-burn",
          "hard_light": "hard-light", "soft_light": "soft-light", "difference": "difference",
          "exclusion": "exclusion", "hue": "hue", "saturation": "saturation", "color": "color",
          "luminosity": "luminosity", "linear_dodge": "plus-lighter"}


def _hex(values):
    """Photoshop colour [a, r, g, b] (0..1) -> "#rrggbb"."""
    if not values:
        return "#ffffff"
    rgb = values[1:4] if len(values) == 4 else values[:3]
    return "#" + "".join(f"{max(0, min(255, round(v * 255))):02x}" for v in rgb)


def _field_name(name, taken):
    base = re.sub(r"\s+", " ", name).strip()[:40] or "Field"
    out, n = base, 2
    while out.lower() in taken:
        out, n = f"{base} {n}", n + 1
    taken.add(out.lower())
    return out


def _text_layer(layer, fonts, taken):
    engine = layer.engine_dict
    resources = layer.resource_dict
    run = engine["StyleRun"]["RunArray"][0]["StyleSheet"]["StyleSheetData"]
    para = engine["ParagraphRun"]["RunArray"][0]["ParagraphSheet"]["Properties"]
    font_set = resources.get("FontSet", [])
    font = "Inter"
    if "Font" in run and run["Font"] < len(font_set):
        raw = font_set[run["Font"]]["Name"]
        font = str(getattr(raw, "value", raw)).strip("\x00'\" ")
    xx, xy, yx, yy, tx, ty = layer.transform
    scale = (xx * xx + xy * xy) ** 0.5 or 1
    size = float(run.get("FontSize", 24)) * scale
    leading = float(run.get("Leading", 0)) * scale if not run.get("AutoLeading", True) else 0
    line_height = round(leading / size, 3) if leading and size else 1.2
    text = layer.text.replace("\r", "\n").rstrip("\n")
    color = _hex(run.get("FillColor", {}).get("Values"))
    align = {0: "left", 1: "right", 2: "center"}.get(int(para.get("Justification", 0)), "left")
    caps = int(run.get("FontCaps", 0)) == 2
    tracking = float(run.get("Tracking", 0))   # 1/1000 em
    left, top, right, bottom = layer.bbox
    lines = max(1, text.count("\n") + 1)
    # Point text sits on its baseline at (tx, ty); the box starts one
    # ascent above the first baseline.
    box_h = size * line_height * lines
    y = ty - size * 0.86
    width = max(right - left, 10)
    if align == "left":
        x = min(left, tx)
        w = width * 1.3 + size
    elif align == "right":
        w = width * 1.3 + size
        x = max(right, tx) - w
    else:
        w = width * 1.3 + size
        x = (left + right) / 2 - w / 2
    fonts.add(font)
    is_field = True
    return {
        "id": new_id("l"), "name": layer.name, "type": "text",
        "x": round(x), "y": round(y), "w": round(w), "h": round(box_h + size * 0.2),
        "opacity": 1, "rotation": 0, "visible": True, "blend": "normal",
        "field": _field_name(layer.name, taken) if is_field else "",
        "anim": {"in": dict(ANIM_NONE), "out": dict(ANIM_NONE)},
        "text": text, "font": font, "size": round(size, 2), "color": color, "align": align, "valign": "top",
        "tracking": tracking, "caps": caps, "lineHeight": line_height, "fit": "shrink",
        "weight": 400, "italic": False, "scroll": 0,
    }


def _leaves(group, opacity=1.0, visible=True):
    """(layer, opacity, visible) for every non-group layer, bottom to top."""
    for layer in group:
        op = opacity * (layer.opacity / 255)
        vis = visible and layer.visible
        if layer.is_group():
            yield from _leaves(layer, op, vis)
        else:
            yield layer, op, vis


def import_psd(path, workspace, name=None):
    """Makes a composition from a PSD (and PNGs for its layers in
    assets/<name>/). Returns (composition, [fonts it uses])."""
    from psd_tools import PSDImage

    psd = PSDImage.open(path)
    name = name or os.path.splitext(os.path.basename(path))[0]
    width, height = psd.size
    comp = blank_comp(name)
    comp["width"], comp["height"] = width, height
    folder_rel, folder = workspace.unique_asset(name)
    os.makedirs(folder, exist_ok=True)
    sub = folder_rel[len("assets/"):]
    fonts, taken, used_names = set(), set(), set()
    for layer, opacity, visible in _leaves(psd):
        kind = layer.kind
        if kind in ("adjustment", "brightnesscontrast", "curves", "levels", "huesaturation"):
            continue
        if getattr(layer, "clipping", False):
            continue   # composited into the layer it clips to, below
        try:
            if kind == "type":
                item = _text_layer(layer, fonts, taken)
                item["opacity"] = round(opacity, 3)
                item["visible"] = visible
                comp["layers"].append(item)
                continue
            left, top, right, bottom = layer.bbox
            if right - left <= 0 or bottom - top <= 0:
                continue
            try:
                image = layer.composite()   # with layer effects and clipped layers
            except Exception:
                image = None
            if image is None:
                image = layer.topil()
            if image is None:
                continue
            base = re.sub(r"[^\w\- ]+", "_", layer.name).strip() or "layer"
            fname, n = base, 2
            while fname.lower() in used_names:
                fname, n = f"{base}-{n}", n + 1
            used_names.add(fname.lower())
            image.save(os.path.join(folder, fname + ".png"), optimize=True)
            generic = bool(GENERIC.match(layer.name.strip()))
            comp["layers"].append({
                "id": new_id("l"), "name": layer.name, "type": "image",
                "x": left, "y": top, "w": image.size[0], "h": image.size[1],
                "opacity": round(opacity, 3), "rotation": 0, "visible": visible,
                "blend": BLENDS.get(str(getattr(layer.blend_mode, "name", layer.blend_mode)).lower(), "normal"),
                "field": "" if generic else _field_name(layer.name, taken),
                "anim": {"in": dict(ANIM_NONE), "out": dict(ANIM_NONE)},
                "src": f"assets/{sub}/{fname}.png", "fit": "fill", "loop": True,
            })
        except Exception as e:
            log(f"{name}: skipped layer {layer.name!r} ({e})", "warn")
    if not comp["layers"]:
        # A flat file (no layers): the whole picture as one.
        image = psd.composite()
        if image is not None:
            image.save(os.path.join(folder, "Image.png"), optimize=True)
            comp["layers"].append({
                "id": new_id("l"), "name": "Image", "type": "image", "x": 0, "y": 0, "w": width, "h": height,
                "opacity": 1, "rotation": 0, "visible": True, "blend": "normal", "field": "",
                "anim": {"in": dict(ANIM_NONE), "out": dict(ANIM_NONE)}, "src": f"assets/{sub}/Image.png", "fit": "fill", "loop": True})
    auto_animate(comp["layers"], width, height)
    log(f"Imported {name}: {len(comp['layers'])} layers")
    return comp, sorted(fonts)


def auto_animate(layers, width=1920, height=1080):
    """A starting animation: backgrounds fade, bars wipe on, text and
    pictures slide up, one after another from the left; all fade out."""
    order = sorted(range(len(layers)), key=lambda i: (layers[i]["x"] // 120, layers[i]["y"]))
    for n, i in enumerate(order):
        layer = layers[i]
        w, h = layer["w"], layer["h"]
        if w >= width * 0.9 and h >= height * 0.9:
            kind, delay = "fade", 0
        elif layer["type"] == "text":
            kind, delay = "slide-up", 150
        elif w > h * 3:
            kind, delay = "wipe-right", 0
        else:
            kind, delay = "scale" if w < 400 and h < 400 else "fade", 80
        layer["anim"] = {"in": {"type": kind, "dur": 450, "delay": min(700, delay + n * 12)},
                         "out": {"type": "fade", "dur": 250, "delay": 0}}
