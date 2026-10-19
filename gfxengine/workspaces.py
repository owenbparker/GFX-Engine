"""The workspaces: one per event or show, each with its own graphics, files,
data, transitions and global settings (and a name and picture for the home
screen). They live in workspaces/<id>/ next to the app; the engine has one
open at a time, and the outputs show that one.

    workspaces/<id>/project.json   (with "name", "picture": "cover.png")
    workspaces/<id>/assets/...
    workspaces/<id>/cover.png
"""

import json
import os
import re
import shutil
import time

from .log import log
from .project import blank_project

PICTURE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


class Workspaces:
    def __init__(self, root, starter=None, legacy=None):
        self.root = root
        self.starter = starter
        os.makedirs(root, exist_ok=True)
        if legacy and os.path.isfile(os.path.join(legacy, "project.json")):
            # The single workspace of v1.0.1: moved in as the first of many.
            dest = os.path.join(root, self._new_id(self._read(legacy).get("name") or "workspace"))
            shutil.move(legacy, dest)
            log(f"Moved the workspace into {dest}")

    @staticmethod
    def _read(folder):
        try:
            with open(os.path.join(folder, "project.json"), encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {}

    def _new_id(self, name):
        slug = re.sub(r"[^a-z0-9]+", "-", (name or "workspace").lower()).strip("-")[:40] or "workspace"
        wid, n = slug, 2
        while os.path.exists(os.path.join(self.root, wid)):
            wid, n = f"{slug}-{n}", n + 1
        return wid

    def path(self, wid):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", wid or ""):
            return None
        folder = os.path.join(self.root, wid)
        return folder if os.path.isfile(os.path.join(folder, "project.json")) else None

    def list(self):
        out = []
        for wid in sorted(os.listdir(self.root)):
            folder = self.path(wid)
            if not folder:
                continue
            data = self._read(folder)
            pic = data.get("picture") or ""
            out.append({"id": wid, "name": data.get("name") or wid,
                        "picture": bool(pic and os.path.isfile(os.path.join(folder, pic))),
                        "graphics": len(data.get("compositions") or []),
                        "updated": os.path.getmtime(os.path.join(folder, "project.json"))})
        out.sort(key=lambda w: -w["updated"])
        return out

    def create(self, name, template="scc"):
        """A new workspace, from the SCC graphics ("scc") or empty. Returns its id."""
        name = (name or "").strip()[:80] or "New workspace"
        wid = self._new_id(name)
        folder = os.path.join(self.root, wid)
        if template == "scc" and self.starter and os.path.isfile(os.path.join(self.starter, "project.json")):
            shutil.copytree(self.starter, folder)
            data = self._read(folder)
        else:
            os.makedirs(os.path.join(folder, "assets"))
            data = blank_project()
        data["name"] = name
        self._write(folder, data)
        log(f"Created the workspace {name}")
        return wid

    @staticmethod
    def _write(folder, data):
        tmp = os.path.join(folder, "project.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, os.path.join(folder, "project.json"))

    def starter_project(self):
        return self._read(self.starter) if self.starter else {}

    def set_field(self, wid, key, value):
        """Changes project.json of a workspace that isn't open."""
        folder = self.path(wid)
        if not folder:
            raise KeyError("No such workspace")
        data = self._read(folder)
        data[key] = value
        self._write(folder, data)

    def rename(self, wid, name):
        self.set_field(wid, "name", (name or "").strip()[:80] or "Workspace")

    def set_picture(self, wid, filename, blob):
        """The workspace's picture for the home screen (stored beside project.json)."""
        folder = self.path(wid)
        if not folder:
            raise KeyError("No such workspace")
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in PICTURE_EXTS:
            raise ValueError("The picture must be a PNG, JPG, WEBP or GIF")
        for old in os.listdir(folder):
            if old.startswith("cover."):
                os.remove(os.path.join(folder, old))
        name = f"cover{ext}"
        with open(os.path.join(folder, name), "wb") as f:
            f.write(blob)
        return name

    def picture(self, wid):
        folder = self.path(wid)
        if not folder:
            return None
        pic = self._read(folder).get("picture")
        path = os.path.join(folder, pic) if pic else None
        return path if path and os.path.isfile(path) else None

    def delete(self, wid):
        folder = self.path(wid)
        if not folder:
            raise KeyError("No such workspace")
        # Kept for a while in workspaces/.deleted, in case it was a mistake.
        trash = os.path.join(self.root, ".deleted")
        os.makedirs(trash, exist_ok=True)
        shutil.move(folder, os.path.join(trash, f"{wid}-{int(time.time())}"))
        log(f"Deleted the workspace {wid} (kept in workspaces/.deleted)")
