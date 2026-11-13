"""Graphics as one file to take to another GFX Engine (Composer's Export,
Outputs > Share graphics), and bringing them in (Composer's Import).

A .sccgfx file is a zip:

    scc-gfx.json        {"format": "scc-gfx", "version": 1, "engine",
                         "compositions", "sources", "files"}
    files/assets/...    the pictures, videos, Lottie animations and data
    files/library/...   files they use (with a Lottie animation's folder)
                        and the fonts their text uses

Importing adds the graphics (as new ones: nothing is replaced), the files
the engine doesn't have yet, and the data sources the graphics read that it
has no source of that name for. A file whose name is taken by a different
file is added under a new name and the graphics point at that.

Import also takes an "Export HTML" zip (its gfx-data.js has the graphics).
"""

import hashlib
import io
import json
import os
import re
import shutil
import urllib.error
import urllib.request
import zipfile

from . import export
from .log import log
from .project import new_id
from .version import VERSION

EXT = ".sccgfx"
MANIFEST = "scc-gfx.json"
FORMAT = "scc-gfx"


def _tables_read(comps):
    """The data tables the graphics read ({{Table!Field}}), lower case."""
    text = json.dumps(comps)
    used = {m.strip().lower() for m in re.findall(r"\{\{\s*([^!{}|]+)!", text)}
    if re.search(r"\{\{\s*sponsors", text, re.I):
        used.add("sponsors")
    return used


def _lottie_folder(rel, path, workspace):
    """A Lottie animation's own folder (its pictures are beside it), or None."""
    if not (rel.startswith("assets/") and rel.lower().endswith(".json")):
        return None
    folder = os.path.dirname(path)
    if os.path.normpath(folder) == os.path.normpath(workspace.assets_dir):
        return None
    return folder


def build(workspace, assets, comp_ids):
    """The .sccgfx file's bytes for these graphics (all if comp_ids is empty)."""
    project = workspace.get()
    comps = [c for c in project["compositions"] if c["id"] in comp_ids] if comp_ids else project["compositions"]
    if not comps:
        raise KeyError("No such graphic")
    used = set()
    export._walk_assets(comps, used)
    tables = _tables_read(comps)
    sources = [s for s in project.get("sources") or [] if s.get("name", "").lower() in tables]
    export._walk_assets(sources, used)
    families = {l.get("font") for c in comps for l in c.get("layers") or [] if l.get("type") == "text"}
    fonts = [f for f in assets.fonts() if families & set(f.get("aliases") or [f["postscript"]])]
    used.update(f["path"] for f in fonts)
    used = {r for r in used if r.startswith(("assets/", "library/"))}   # (loops/ come with every engine)
    buf = io.BytesIO()
    written, files = set(), []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        def put(full, rel):
            if rel in written:
                return
            written.add(rel)
            # (videos and pictures are compressed already)
            kind = zipfile.ZIP_STORED if rel.lower().endswith((".mp4", ".webm", ".mov", ".png", ".jpg", ".jpeg",
                                                                ".webp", ".gif", ".avif")) else zipfile.ZIP_DEFLATED
            z.write(full, "files/" + rel, compress_type=kind)

        for rel in sorted(used):
            path = assets.path_of(rel)
            if not path or not os.path.isfile(path):
                continue
            files.append(rel)
            folder = _lottie_folder(rel, path, workspace)
            if folder:
                for dirpath, _, names in os.walk(folder):
                    for n in names:
                        full = os.path.join(dirpath, n)
                        put(full, "assets/" + os.path.relpath(full, workspace.assets_dir).replace(os.sep, "/"))
            else:
                put(path, rel)
        z.writestr(MANIFEST, json.dumps({
            "format": FORMAT, "version": 1, "engine": VERSION, "name": project.get("name", ""),
            "compositions": comps, "sources": sources, "files": files}, ensure_ascii=False, indent=1))
    return buf.getvalue()


def send(blob, url, name):
    """Hands the file to another engine's Import (its address: http://PC:port). Returns its answer."""
    url = url.rstrip("/")
    if not re.match(r"https?://[^/]+$", url):
        raise ValueError("That isn't an engine's address")
    req = urllib.request.Request(url + "/api/upload?graphic=1", data=blob, method="POST",
                                 headers={"X-Filename": urllib.request.quote(name + EXT),
                                          "Content-Type": "application/octet-stream"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read()).get("error")
        except ValueError:
            msg = None
        raise ValueError(f"The other engine said: {msg or e.code}") from None
    except (urllib.error.URLError, OSError) as e:
        raise ValueError(f"Couldn't reach the engine at {url} ({getattr(e, 'reason', e)})") from None


def is_package(path):
    """A .sccgfx (or an Export HTML zip) Import can bring graphics in from."""
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False
    return MANIFEST in names or "gfx-data.js" in names


def _read(z):
    """(manifest, the folder in the zip its files are in)."""
    names = set(z.namelist())
    if MANIFEST in names:
        data = json.loads(z.read(MANIFEST).decode("utf-8"))
        if data.get("format") != FORMAT:
            raise ValueError("That isn't a GFX Engine graphics file")
        if int(data.get("version") or 1) > 1:
            raise ValueError("That file was made by a newer GFX Engine: update this one first")
        return data, "files/"
    text = z.read("gfx-data.js").decode("utf-8")
    m = re.search(r"window\.GFX_EXPORT\s*=\s*(\{.*\})\s*;?\s*$", text, re.S)
    if not m:
        raise ValueError("That export has no graphics in it")
    data = json.loads(m.group(1))
    used = set()
    export._walk_assets(data.get("compositions") or [], used)
    data["files"] = sorted(r for r in used if r.startswith("assets/")) + [f["path"] for f in data.get("fonts") or []]
    data["sources"] = []
    return data, ""


def _digest(blob):
    return hashlib.sha1(blob).hexdigest()


def _same(z, member, path):
    if not os.path.isfile(path) or os.path.getsize(path) != z.getinfo(member).file_size:
        return False
    with open(path, "rb") as f:
        return _digest(f.read()) == _digest(z.read(member))


def _twin(z, member, rel, workspace):
    """The same file already beside rel under a numbered name (logo-2.png), or None."""
    base, ext = os.path.splitext(rel)
    for n in range(2, 100):
        cand = f"{base}-{n}{ext.lower()}"
        path = workspace.asset_path(cand)
        if not path or not os.path.exists(path):
            continue
        if _same(z, member, path):
            return cand
    return None


def _extract(z, member, dest):
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with z.open(member) as src, open(dest + ".part", "wb") as out:
        shutil.copyfileobj(src, out, 1 << 20)
    os.replace(dest + ".part", dest)


def _replace(value, mapping):
    if isinstance(value, dict):
        return {k: _replace(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_replace(v, mapping) for v in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def import_package(path, workspace, assets):
    """Adds the graphics in a .sccgfx (or Export HTML zip). Returns
    {"assets", "comps", "sources", "job": None, "imported": True}."""
    with zipfile.ZipFile(path) as z:
        data, root = _read(z)
        comps = [c for c in data.get("compositions") or [] if isinstance(c, dict) and isinstance(c.get("layers"), list)]
        if not comps:
            raise ValueError("That file has no graphics in it")
        mapping, added = _bring_files(z, root, data.get("files") or [], workspace, assets)

    # The graphics, as new ones (a name that's taken gets a number).
    names = {c["name"].lower() for c in workspace.get()["compositions"]}
    made = []
    for comp in comps:
        comp = _replace(comp, mapping)
        comp["id"] = new_id("c")
        base, n = str(comp.get("name") or "Graphic"), 2
        comp["name"] = base
        while comp["name"].lower() in names:
            comp["name"], n = f"{base} {n}", n + 1
        names.add(comp["name"].lower())
        made.append(workspace.add_comp(comp))

    # The data sources they read that this engine has none of that name for.
    have = {s.get("name", "").lower() for s in workspace.get().get("sources") or []}
    sources = []
    for s in data.get("sources") or []:
        if isinstance(s, dict) and s.get("name", "").lower() not in have:
            s = _replace({k: v for k, v in s.items() if k != "id"}, mapping)
            sources.append(s)

    log(f"Imported {len(made)} graphic(s) with {len(added)} new file(s)")
    return {"assets": added, "comps": made, "sources": sources, "job": None, "imported": True}


def _bring_files(z, root, files, workspace, assets):
    """Puts the files (in the zip under root) into the workspace, the ones it
    doesn't have yet. Returns ({old path: new path}, [the files added])."""
    members = {n[len(root):]: n for n in z.namelist() if n.startswith(root) and not n.endswith("/")}
    mapping, added = {}, []
    for rel in files:
        rel = str(rel).replace("\\", "/")
        if rel.startswith("library/"):
            # A font: every workspace shares them; one of that name is kept as it is.
            if rel not in members:
                continue
            dest = assets.path_of(rel)
            if not dest:     # (no shared library: into the workspace's fonts)
                new_rel, dest = workspace.unique_asset(os.path.basename(rel), "fonts")
                mapping[rel] = new_rel
            if not os.path.exists(dest):
                _extract(z, members[rel], dest)
                added.append(mapping.get(rel, rel))
            continue
        dest = workspace.asset_path(rel)
        if not dest:
            continue
        folder = os.path.dirname(rel)
        if rel.lower().endswith(".json") and folder != "assets":
            # A Lottie animation: its folder goes together (it finds its pictures by path).
            group = sorted(m for m in members if m.startswith(folder + "/"))
            if not group:
                continue
            if all(_same(z, members[m], workspace.asset_path(m)) for m in group):
                continue     # (already here)
            twin = next((f"{folder}-{n}" for n in range(2, 100)
                         if os.path.isdir(workspace.asset_path(f"{folder}-{n}") or "")
                         and all(_same(z, members[m], workspace.asset_path(f"{folder}-{n}" + m[len(folder):]))
                                 for m in group)), None)
            if twin:
                mapping[rel] = twin + rel[len(folder):]
                continue
            new_folder = folder
            if os.path.exists(workspace.asset_path(folder)):
                parent = os.path.dirname(folder)[len("assets"):].lstrip("/")
                new_folder, _ = workspace.unique_asset(os.path.basename(folder), parent)
            for m in group:
                target = new_folder + m[len(folder):]
                _extract(z, members[m], workspace.asset_path(target))
            mapping[rel] = new_folder + rel[len(folder):]
            added.append(mapping[rel])
            continue
        if rel not in members:
            continue
        if os.path.exists(dest):
            if _same(z, members[rel], dest):
                continue
            twin = _twin(z, members[rel], rel, workspace)
            if twin:     # (imported before, under a new name)
                mapping[rel] = twin
                continue
            sub = os.path.dirname(rel)[len("assets"):].lstrip("/")
            new_rel, dest = workspace.unique_asset(os.path.basename(rel), sub)
            mapping[rel] = new_rel
        _extract(z, members[rel], dest)
        added.append(mapping.get(rel, rel))
    return mapping, added


class _Folder:
    """Another workspace's folder, enough to find its files."""

    def __init__(self, folder):
        self.folder = folder
        self.assets_dir = os.path.join(folder, "assets")

    def asset_path(self, rel):
        rel = rel.replace("\\", "/")
        if not rel.startswith("assets/"):
            return None
        path = os.path.normpath(os.path.join(self.folder, rel))
        return path if path.startswith(os.path.normpath(self.assets_dir) + os.sep) else None


def bring_layers(src_folder, workspace, assets, layers):
    """Composer's paste from a graphic in another workspace: the files the
    layers use come over too (the same rules as Import: a file that's here
    already is used, a different file with a taken name gets a new name).
    Returns (the layers, pointing at the files here, [the files added])."""
    src = _Folder(src_folder)
    used = set()
    export._walk_assets(layers, used)
    buf = io.BytesIO()
    files = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:
        written = set()
        for rel in sorted(r for r in used if r.startswith("assets/")):
            path = src.asset_path(rel)
            if not path or not os.path.isfile(path):
                continue
            files.append(rel)
            folder = _lottie_folder(rel, path, src)
            group = [os.path.join(d, n) for d, _, ns in os.walk(folder) for n in ns] if folder else [path]
            for full in group:
                member = "files/assets/" + os.path.relpath(full, src.assets_dir).replace(os.sep, "/")
                if member not in written:
                    written.add(member)
                    z.write(full, member)
    with zipfile.ZipFile(buf) as z:
        mapping, added = _bring_files(z, "files/", files, workspace, assets)
    if added:
        log(f"Pasted layers brought {len(added)} file(s) from another workspace")
    return _replace(layers, mapping), added
