"""After Effects projects (.aep) to video, with After Effects' own renderer.

A browser can't play an .aep, and nothing but After Effects can draw one, so
when After Effects is installed on this PC the engine asks its command line
renderer (aerender) to render a composition as QuickTime with alpha, then
converts that to see-through WebM like any other .mov (see media).

The composition names are read from the project file itself (an .aep is a
big-endian RIFF file: each item is a LIST "Item" with an "idta" chunk whose
first two bytes are the item's type, 4 = composition, and a "Utf8" chunk with
its name). When that can't be read, aerender renders the project's Render
Queue as it was saved.

Footage the project uses is found where After Effects saved it (full paths),
so the project should be added on the PC it was made on, or after File >
Dependencies > Collect Files with the footage where the project points.
"""

import glob
import os
import re
import shutil
import struct
import subprocess
import sys

from .log import log

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
# Output module templates that keep transparency, newest After Effects first.
TEMPLATES = ("High Quality with Alpha", "Lossless with Alpha")
NOT_INSTALLED = (
    "After Effects projects (.aep) are rendered with After Effects, which isn't installed on this PC. "
    "Either add the .aep on a PC with After Effects, export the animation as Lottie (.json, with the "
    "Bodymovin / LottieFiles plugin), or render it in After Effects as QuickTime (Composition > Add to "
    "Render Queue, Output Module: \"High Quality with Alpha\", Channels RGB + Alpha) and add the .mov: "
    "it's converted to see-through video.")


def aerender_path():
    """aerender(.exe) from the newest After Effects installed, or None.
    GFX_AERENDER can point at one."""
    env = os.environ.get("GFX_AERENDER")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("aerender")
    if found:
        return found
    if sys.platform == "win32":
        roots = [os.environ.get(v) for v in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        patterns = [os.path.join(r, "Adobe", "Adobe After Effects*", "Support Files", "aerender.exe") for r in roots if r]
    elif sys.platform == "darwin":
        patterns = ["/Applications/Adobe After Effects*/aerender"]
    else:
        patterns = []
    hits = [p for pat in patterns for p in glob.glob(pat)]
    return sorted(hits, key=_version_key)[-1] if hits else None


def _version_key(path):
    # "Adobe After Effects 2025", "Adobe After Effects CC 2019", "... (Beta)"
    m = re.search(r"After Effects[^\\/]*?(\d{2,4})", path)
    return (int(m[1]) if m else 0, "beta" not in path.lower(), path)


def comps(path):
    """The names of the compositions in an .aep, in the project's order ([] if
    they can't be read)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    if data[:4] != b"RIFX":
        return []
    names = []
    try:
        _walk(data, 12, len(data), names, depth=0)
    except (struct.error, IndexError, ValueError):
        pass
    out = []
    for n in names:
        if n and n not in out:
            out.append(n)
    return out


def _walk(data, start, end, names, depth):
    pos = start
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = pos + 8
        if body + size > end:
            break
        if cid == b"LIST" and depth < 64:
            kind = data[body:body + 4]
            if kind == b"Item":
                _item(data, body + 4, body + size, names)
            # Items sit inside folders ("Fold") and the project's own lists.
            if kind != b"btdk":
                _walk(data, body + 4, body + size, names, depth + 1)
        pos = body + size + (size & 1)


def _item(data, start, end, names):
    """One project item: a composition's name goes in names."""
    pos, kind, name = start, None, None
    while pos + 8 <= end:
        cid = data[pos:pos + 4]
        size = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        body = data[pos + 8:pos + 8 + size]
        if cid == b"idta" and len(body) >= 2 and kind is None:
            kind = struct.unpack(">H", body[:2])[0]
        elif cid == b"Utf8" and name is None:
            name = body.decode("utf-8", "replace").strip("\0").strip()
        elif cid == b"LIST":
            break   # (the item's layers etc. come after its name)
        pos += 8 + size + (size & 1)
    if kind == 4 and name:
        names.append(name)


def _frames(timecode, fps):
    """aerender's "0:00:05:12" (h:m:s:frames) in frames."""
    parts = [int(p) for p in re.findall(r"\d+", timecode)]
    if len(parts) != 4:
        return 0
    h, m, s, f = parts
    return int(((h * 60 + m) * 60 + s) * fps + f)


def render(aep, out_dir, comp=None, progress=lambda p: None):
    """Renders comp (or the project's Render Queue) as QuickTime with alpha
    into out_dir. Returns the file written."""
    exe = aerender_path()
    if not exe:
        raise RuntimeError(NOT_INSTALLED)
    os.makedirs(out_dir, exist_ok=True)
    errors = []
    for template in TEMPLATES:
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))
        out = os.path.join(out_dir, re.sub(r"[^\w\- ]+", "_", comp or "render").strip() + ".mov")
        args = [exe, "-project", os.path.abspath(aep), "-output", out, "-OMtemplate", template, "-continueOnMissingFootage"]
        if comp:
            args[1:1] = ["-comp", comp]
        log(f"After Effects: rendering {comp or 'the Render Queue'} ({template})")
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
                                creationflags=_NO_WINDOW)
        fps, total, lines = 30.0, 0, []
        for line in proc.stdout:
            lines.append(line.rstrip())
            m = re.search(r"Frame Rate:\s*([\d.]+)", line)
            if m:
                fps = float(m[1]) or fps
            m = re.search(r"PROGRESS:\s+Duration:\s*([\d:;]+)", line)
            if m:
                total = _frames(m[1], fps)
            m = re.search(r"PROGRESS:\s+[\d:;]+\s+\((\d+)\)", line)
            if m and total:
                progress(min(99, int(m[1]) / total * 100))
        code = proc.wait()
        written = [os.path.join(out_dir, f) for f in os.listdir(out_dir)
                   if not f.startswith(".") and os.path.getsize(os.path.join(out_dir, f)) > 0]
        if code == 0 and written:
            return max(written, key=os.path.getsize)
        said = [ln for ln in lines if re.search(r"error|unable|not found|no comp|can't|cannot", ln, re.I)]
        errors = said[-3:] or lines[-3:]
        if not any(re.search(r"output module|template", ln, re.I) for ln in errors):
            break   # (another template won't help)
    raise RuntimeError("After Effects couldn't render it: " + (" ".join(errors).strip() or "no video was written"))
