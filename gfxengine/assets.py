"""The asset files: listing them, and taking in new ones.

Adding a file does what that kind of file needs:

    .psd .psb             becomes a new graphic (see psdimport)
    .mov .avi .mkv ...    converted to WebM (see-through) or MP4 (see media)
    .zip                  unpacked: a PNG sequence becomes one video, fonts and
                          images are added, a Lottie animation keeps its images
    .ttf .otf .woff(2)    a font, usable by its name in text layers
    .json                 a Lottie animation (After Effects, exported with Bodymovin)
    .csv .xlsx .txt       added, and made a data source
    .aep .ai .prproj      refused, saying how to export them instead
"""

import os
import re
import shutil
import tempfile
import zipfile

from . import fonts as fontnames
from . import media
from .log import log

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp")
REFUSED = {
    ".aep": "After Effects projects can't be played directly. Export the animation as Lottie (.json, with the "
            "Bodymovin / LottieFiles plugin), or render it as QuickTime (Animation or ProRes 4444 with alpha) "
            "and add the .mov: it's converted to see-through video.",
    ".aet": "After Effects templates can't be played directly: export Lottie (.json) or render a .mov.",
    ".ai": "Illustrator files can't be used directly: export them as SVG or PNG.",
    ".prproj": "Premiere projects can't be used directly: export the video (.mp4 or .mov) instead.",
}


def kind_of(name):
    low = name.lower()
    if low.endswith(IMAGE_EXTS):
        return "image"
    if low.endswith(media.VIDEO_EXTS):
        return "video"
    if low.endswith(media.AUDIO_EXTS):
        return "audio"
    if fontnames.is_font(low):
        return "font"
    if low.endswith(".json"):
        return "lottie"
    if low.endswith((".csv", ".tsv", ".txt", ".xlsx", ".xlsm")):
        return "data"
    if low.endswith((".psd", ".psb")):
        return "psd"
    return "other"


class Assets:
    """A workspace's files, and the font library every workspace shares
    (library/fonts, served as library/...)."""

    def __init__(self, workspace, jobs, library_dir=None):
        self.ws = workspace
        self.jobs = jobs
        self.library_dir = library_dir
        self.meta = media.load_meta(workspace.assets_dir)
        self.library_meta = media.load_meta(library_dir) if library_dir else {}
        if library_dir:
            os.makedirs(os.path.join(library_dir, "fonts"), exist_ok=True)
            self._share_fonts()

    def _share_fonts(self):
        """Fonts added to a workspace before the library existed go into it too."""
        lib = os.path.join(self.library_dir, "fonts")
        have = {f.lower() for f in os.listdir(lib)}
        for folder, _, files in os.walk(self.ws.assets_dir):
            for f in files:
                if fontnames.is_font(f) and f.lower() not in have:
                    shutil.copy(os.path.join(folder, f), os.path.join(lib, f))
                    have.add(f.lower())

    def path_of(self, rel):
        """A file on disk for "assets/..." (this workspace) or "library/..." (shared)."""
        rel = (rel or "").replace("\\", "/")
        if rel.startswith("library/") and self.library_dir:
            path = os.path.normpath(os.path.join(self.library_dir, rel[len("library/"):]))
            return path if path.startswith(os.path.normpath(self.library_dir) + os.sep) else None
        return self.ws.asset_path(rel)

    def _meta(self, rel, path):
        """Cached facts about a file (font names, video length...), by size and time."""
        st = os.stat(path)
        key = f"{st.st_size}:{int(st.st_mtime)}"
        store = self.library_meta if rel.startswith("library/") else self.meta
        cached = store.get(rel)
        if cached and cached.get("key") == key:
            return cached
        kind = kind_of(rel)
        entry = {"key": key}
        if kind == "font":
            entry.update(fontnames.names(path))
        elif kind == "video":
            info = media.probe(path)
            entry.update(info)
            entry["playable"] = media.playable(path, info)
        elif kind == "image" and not rel.lower().endswith(".svg"):
            try:
                from PIL import Image
                with Image.open(path) as im:
                    entry["width"], entry["height"] = im.size
            except Exception:
                pass
        store[rel] = entry
        media.save_meta(self.library_dir if store is self.library_meta else self.ws.assets_dir, store)
        return entry

    def list(self):
        out = []
        roots = [(self.ws.assets_dir, "assets")]
        if self.library_dir:
            roots.append((self.library_dir, "library"))
        for root, prefix in roots:
            for folder, dirs, files in os.walk(root):
                dirs[:] = sorted(d for d in dirs if not d.startswith("."))
                for f in sorted(files):
                    if f.startswith(".") or f.endswith(".part"):
                        continue
                    if prefix == "assets" and fontnames.is_font(f) and self.library_dir:
                        continue   # (fonts are in the library)
                    path = os.path.join(folder, f)
                    rel = prefix + "/" + os.path.relpath(path, root).replace(os.sep, "/")
                    folder_name = os.path.dirname(rel)[len(prefix):].lstrip("/")
                    entry = {"path": rel, "name": f, "kind": kind_of(f), "size": os.path.getsize(path),
                             "folder": "fonts (every workspace)" if prefix == "library" else folder_name,
                             "shared": prefix == "library"}
                    try:
                        meta = self._meta(rel, path)
                        entry.update({k: v for k, v in meta.items() if k != "key"})
                    except OSError:
                        continue
                    out.append(entry)
        return out

    def fonts(self):
        """[{"postscript", "family", "style", "path", "aliases"}] for every font."""
        return [{"postscript": a.get("postscript"), "family": a.get("family"), "style": a.get("style"),
                 "path": a["path"], "aliases": a.get("aliases") or [a.get("postscript")]}
                for a in self.list() if a["kind"] == "font"]

    # --- adding --------------------------------------------------------

    def add(self, name, src_path, fps=None, graphic=False):
        """Takes in an uploaded file (already saved at src_path, which this
        moves or removes). graphic: make a new graphic of it (Composer's
        Import: design files and pictures, see docimport). Returns {"assets":
        [paths], "comps": [comps], "sources": [sources], "job": job id or None}."""
        ext = os.path.splitext(name.lower())[1]
        if ext in REFUSED and not graphic:
            os.remove(src_path)
            raise ValueError(REFUSED[ext])
        kind = kind_of(name)
        result = {"assets": [], "comps": [], "sources": [], "job": None}
        if kind == "psd" or graphic:
            from .docimport import import_file
            try:
                comp, used_fonts = import_file(src_path, self.ws, os.path.basename(name))
            finally:
                if os.path.exists(src_path):
                    os.remove(src_path)
            self.ws.add_comp(comp)
            result["comps"].append(comp)
            have = {f["postscript"] for f in self.fonts()}
            missing = [f for f in used_fonts if f not in have]
            if missing:
                log(f"{comp['name']} uses fonts that aren't added yet: {', '.join(missing)}", "warn")
            result["missing_fonts"] = missing
            return result
        if ext == ".zip":
            return self._zip(name, src_path, fps)
        if kind == "video":
            info = media.probe(src_path)
            if not media.playable(src_path, info):
                return self._convert(name, src_path, info)
        if kind == "font" and self.library_dir:
            rel, dest = self._library_file(name)
        else:
            rel, dest = self.ws.unique_asset(name, "fonts" if kind == "font" else "")
        shutil.move(src_path, dest)
        result["assets"].append(rel)
        if kind == "data":
            result["sources"].append({"name": os.path.splitext(os.path.basename(name))[0], "type": "file", "path": rel})
        return result

    def _library_file(self, name):
        """library/fonts/<name> (replacing a font of the same name)."""
        base = "".join(ch if ch.isalnum() or ch in " -_.()" else "_" for ch in os.path.basename(name)).strip() or "font"
        return "library/fonts/" + base, os.path.join(self.library_dir, "fonts", base)

    def delete(self, rel):
        path = self.path_of(rel)
        if not path or not os.path.exists(path):
            raise KeyError("No such file")
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    def _convert(self, name, src_path, info):
        base = os.path.splitext(os.path.basename(name))[0]
        rel, dest = self.ws.unique_asset(base + (".webm" if info["alpha"] else ".mp4"))
        dest_base = os.path.splitext(dest)[0]

        def run(progress):
            try:
                out = media.convert(src_path, dest_base, alpha=info["alpha"], progress=progress)
            finally:
                os.remove(src_path)
            self.ws.touch_assets()
            log(f"Converted {name} to {os.path.basename(out)}")
            return {"assets": [rel]}
        log(f"Converting {name} ({'see-through' if info['alpha'] else 'video'}, {info['codec']}) ...")
        return {"assets": [], "comps": [], "sources": [], "job": self.jobs.start(f"Converting {name}", run)}

    def _zip(self, name, src_path, fps):
        result = {"assets": [], "comps": [], "sources": [], "job": None}
        tmp = tempfile.mkdtemp(prefix="gfx-zip-")
        try:
            with zipfile.ZipFile(src_path) as z:
                for member in z.namelist():
                    target = os.path.normpath(os.path.join(tmp, member))
                    if not target.startswith(os.path.normpath(tmp) + os.sep):
                        raise ValueError(f"Unexpected file in the zip: {member}")
                z.extractall(tmp)
        finally:
            os.remove(src_path)
        files = []
        for folder, dirs, names in os.walk(tmp):
            dirs[:] = [d for d in dirs if not d.startswith(("__MACOSX", "."))]
            files += [os.path.join(folder, n) for n in names if not n.startswith(("._", "."))]
        # A PNG sequence (frame_00001.png ...) becomes one see-through video.
        seqs = {}
        for f in files:
            m = re.fullmatch(r"(.*?)(\d{3,})\.(png|tga|tif|tiff)", os.path.basename(f), re.I)
            if m:
                seqs.setdefault((os.path.dirname(f), m.group(1), len(m.group(2)), m.group(3)), []).append(f)
        seqs = {k: v for k, v in seqs.items() if len(v) >= 10}
        in_seq = {f for v in seqs.values() for f in v}
        lottie = next((f for f in files if f.lower().endswith(".json") and _is_lottie(f)), None)
        if lottie:
            # Keep the animation's folder together: it refers to its images by path.
            base = os.path.splitext(os.path.basename(name))[0]
            rel_dir, dest_dir = self.ws.unique_asset(base)
            shutil.copytree(os.path.dirname(lottie), dest_dir)
            rel = rel_dir + "/" + os.path.basename(lottie)
            result["assets"].append(rel)
            in_seq |= {f for f in files if f.startswith(os.path.dirname(lottie) + os.sep)}
        for (folder, prefix, digits, ext), frames in seqs.items():
            frames.sort()
            label = (prefix.strip(" _-") or os.path.splitext(os.path.basename(name))[0])
            rel, dest = self.ws.unique_asset(label + ".webm")
            seq_tmp = tempfile.mkdtemp(prefix="gfx-seq-")
            # Number the frames from 0 with no gaps, as FFmpeg reads them.
            for i, f in enumerate(frames):
                shutil.copy(f, os.path.join(seq_tmp, f"f{i:06d}.{ext}"))

            def run(progress, seq_tmp=seq_tmp, dest=dest, rel=rel, count=len(frames)):
                try:
                    media.convert(os.path.join(seq_tmp, f"f%06d.{ext}"), os.path.splitext(dest)[0], alpha=True,
                                  fps=fps or 30, sequence=True, progress=progress)
                finally:
                    shutil.rmtree(seq_tmp, ignore_errors=True)
                self.ws.touch_assets()
                log(f"Made {rel} from {count} frames")
                return {"assets": [rel]}
            result["job"] = self.jobs.start(f"Making video from {len(frames)} frames", run)
        for f in files:
            if f in in_seq:
                continue
            kind = kind_of(f)
            if kind in ("image", "font", "video", "audio", "lottie", "data"):
                if kind == "font" and self.library_dir:
                    rel, dest = self._library_file(os.path.basename(f))
                else:
                    rel, dest = self.ws.unique_asset(os.path.basename(f), "fonts" if kind == "font" else "")
                shutil.copy(f, dest)
                result["assets"].append(rel)
        shutil.rmtree(tmp, ignore_errors=True)
        return result


def _is_lottie(path):
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4096)
        return '"layers"' in head or ('"v"' in head and '"fr"' in head)
    except (OSError, UnicodeDecodeError):
        return False
