"""Video files: what they are (length, see-through or not) and turning them
into video the outputs can play, with FFmpeg.

The outputs are web pages, which play MP4 (H.264) and WebM (VP8/VP9). Other
video - QuickTime .mov from After Effects (Animation or ProRes 4444, with
transparency), .avi, .mkv, PNG sequences - is converted when it's added:
see-through video to WebM VP9 with alpha, the rest to MP4.

The desktop build carries its own FFmpeg (from the imageio-ffmpeg package);
from source, the one on PATH is used.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading

from .log import log

PLAYABLE_CODECS = {"h264", "vp8", "vp9", "av1"}
VIDEO_EXTS = (".mp4", ".webm", ".m4v", ".mov", ".avi", ".mkv", ".mxf", ".gif", ".wmv", ".flv", ".mpg", ".mpeg")
AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac")
_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def ffmpeg_path():
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _run(args, timeout=None):
    return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=timeout,
                          creationflags=_NO_WINDOW)


def probe(path):
    """{"duration" (s), "width", "height", "fps", "codec", "alpha", "audio"} for a video,
    read from FFmpeg's description of it (FFmpeg's own builds have no ffprobe)."""
    exe = ffmpeg_path()
    info = {"duration": 0.0, "width": 0, "height": 0, "fps": 30.0, "codec": "", "alpha": False, "audio": False}
    if not exe:
        return info
    err = _run([exe, "-hide_banner", "-i", path], timeout=30).stderr
    m = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    for line in err.splitlines():
        if "Video:" in line and not info["codec"]:
            m = re.search(r"Video: (\w+)", line)
            info["codec"] = m[1] if m else ""
            m = re.search(r", (\d{2,5})x(\d{2,5})", line)
            if m:
                info["width"], info["height"] = int(m[1]), int(m[2])
            m = re.search(r"([\d.]+) fps", line) or re.search(r"([\d.]+) tbr", line)
            if m:
                info["fps"] = float(m[1])
            fmt = line.split(info["codec"], 1)[-1]
            info["alpha"] = bool(re.search(r"\b(yuva\w*|argb|rgba|bgra|abgr|ya8|ya16\w*|rgba64\w*|gbrap\w*|pal8)\b", fmt))
        if "Audio:" in line:
            info["audio"] = True
        if re.search(r"alpha_mode\s*:\s*1", line):
            info["alpha"] = True
    return info


def playable(path, info=None):
    info = info or probe(path)
    return path.lower().endswith((".mp4", ".webm", ".m4v")) and info["codec"] in PLAYABLE_CODECS


def stinger_cut(path, info=None):
    """When a stinger covers the whole picture (ms): the first frame with no
    see-through pixel. Video without transparency covers it all along, so
    halfway through is used. None if it never covers the whole picture."""
    info = info or probe(path)
    if not info["alpha"]:
        return int(info["duration"] * 500)
    exe = ffmpeg_path()
    decoder = ["-c:v", "libvpx-vp9"] if info["codec"] == "vp9" else ["-c:v", "libvpx"] if info["codec"] == "vp8" else []
    out = _run([exe, "-hide_banner", *decoder, "-i", path, "-vf",
                "alphaextract,scale=96:54,signalstats,metadata=print:key=lavfi.signalstats.YMIN",
                "-an", "-f", "null", "-"], timeout=300).stderr
    times = re.findall(r"pts_time:([\d.]+)", out)
    mins = re.findall(r"YMIN=(\d+)", out)
    for t, v in zip(times, mins):
        if int(v) >= 250:
            return int(float(t) * 1000) + 20
    return None


class Jobs:
    """Conversions running in the background, for the Assets page to show."""

    def __init__(self):
        self.jobs = {}
        self.lock = threading.Lock()
        self.listeners = []

    def list(self):
        with self.lock:
            return [dict(j) for j in self.jobs.values()]

    def _set(self, jid, **changes):
        with self.lock:
            self.jobs[jid].update(changes)
        for fn in list(self.listeners):
            fn()

    def start(self, name, fn, *args):
        jid = f"j{len(self.jobs) + 1}"
        with self.lock:
            self.jobs[jid] = {"id": jid, "name": name, "status": "running", "progress": 0, "error": None, "result": None}

        def run():
            try:
                result = fn(*args, progress=lambda p: self._set(jid, progress=int(p)))
                self._set(jid, status="done", progress=100, result=result)
            except Exception as e:
                log(f"{name}: {e}", "error")
                self._set(jid, status="error", error=str(e))
        threading.Thread(target=run, daemon=True).start()
        return jid


def convert(src, dest_base, alpha=None, fps=None, progress=lambda p: None, sequence=False):
    """Converts src to dest_base + ".webm" (see-through) or ".mp4". src may be
    a PNG sequence pattern ("frame_%05d.png") with sequence=True.
    Returns the file written."""
    exe = ffmpeg_path()
    if not exe:
        raise RuntimeError("FFmpeg isn't available, so this video can't be converted. "
                           "Use MP4 (H.264) or WebM, or install FFmpeg.")
    if sequence:
        info = {"duration": 0, "alpha": True if alpha is None else alpha}
        inputs = ["-framerate", str(fps or 30), "-i", src]
    else:
        info = probe(src)
        inputs = ["-i", src]
    see_through = info["alpha"] if alpha is None else alpha
    if see_through:
        dest = dest_base + ".webm"
        codec = ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-crf", "30", "-b:v", "0",
                 "-row-mt", "1", "-deadline", "good", "-cpu-used", "4", "-c:a", "libopus", "-b:a", "160k"]
    else:
        dest = dest_base + ".mp4"
        codec = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium",
                 "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k"]
    args = [exe, "-hide_banner", "-y", *inputs, *codec, "-progress", "pipe:1", "-nostats", dest + ".part"]
    # (the format can't be guessed from ".part")
    args.insert(-1, "-f")
    args.insert(-1, "webm" if see_through else "mp4")
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace",
                            creationflags=_NO_WINDOW)
    err_lines = []
    threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True).start()
    total = info["duration"] or 0
    for line in proc.stdout:
        m = re.match(r"out_time_us=(\d+)", line)
        if m and total:
            progress(min(99, int(m[1]) / 1e6 / total * 100))
    if proc.wait() != 0:
        try:
            os.remove(dest + ".part")
        except OSError:
            pass
        raise RuntimeError("FFmpeg couldn't convert it: " + "".join(err_lines[-3:]).strip())
    os.replace(dest + ".part", dest)
    return dest


def meta_path(assets_dir):
    return os.path.join(assets_dir, ".meta.json")


def load_meta(assets_dir):
    try:
        with open(meta_path(assets_dir), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_meta(assets_dir, meta):
    tmp = meta_path(assets_dir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
    os.replace(tmp, meta_path(assets_dir))
