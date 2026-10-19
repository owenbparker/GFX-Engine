"""The desktop app: runs the engine and shows the control panel in its own
window (no command prompt).

    GFXEngine.exe                the built app
    python -m gfxengine.gui      the same, from source (needs: pip install pywebview)
"""

import argparse
import json
import os
import sys
import urllib.request
import webbrowser

from .__main__ import add_arguments, build_engine
from .app import start
from .config import DATA_DIR
from .log import log

TITLE = "SCC GFX Engine"


def message_box(text, title=TITLE, error=False):
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    else:
        print(f"{title}: {text}")


def already_running(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/hello", timeout=2) as r:
            return json.loads(r.read()).get("app") == "scc-gfx-engine"
    except Exception:
        return False


def smoke_test(engine, port):
    """Used by the build: the packaged app serves its pages, can import a PSD
    and has FFmpeg and its window library. Writes smoke-test.txt next to the app."""
    results, ok = [], True
    for path in ("/control", "/output", "/runtime.js", "/control.js", "/control.css", "/vendor/lottie.min.js",
                 "/fonts/Inter.ttf", "/api/state", "/api/assets", "/api/hello"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
                results.append(f"OK   {path} ({len(r.read())} bytes)")
        except Exception as e:
            ok = False
            results.append(f"FAIL {path}: {e}")
    checks = []
    try:
        import subprocess
        from .media import _NO_WINDOW, ffmpeg_path, probe
        exe = ffmpeg_path()
        if not exe:
            raise RuntimeError("no FFmpeg")
        encoders = subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True,
                                  creationflags=_NO_WINDOW, timeout=30).stdout
        for needed in ("libvpx-vp9", "libx264", "libopus"):
            if needed not in encoders:
                raise RuntimeError(f"FFmpeg has no {needed}")
        state = engine.state()
        videos = [a for a in engine.assets.list() if a["kind"] == "video"]
        if videos:
            info = probe(engine.ws.asset_path(videos[0]["path"]))
            if not info["duration"]:
                raise RuntimeError(f"couldn't read {videos[0]['path']}")
        checks.append(f"OK   FFmpeg ({exe}), {len(state['project']['compositions'])} graphics")
    except Exception as e:
        ok = False
        checks.append(f"FAIL FFmpeg: {e!r}")
    try:
        import psd_tools  # noqa: F401
        import openpyxl  # noqa: F401
        checks.append("OK   PSD and Excel readers")
    except Exception as e:
        ok = False
        checks.append(f"FAIL PSD/Excel readers: {e!r}")
    try:
        import webview  # noqa: F401
        if sys.platform == "win32":
            import webview.platforms.winforms  # noqa: F401  (loads the Edge WebView2 bridge)
        checks.append("OK   window library")
    except Exception as e:
        ok = False
        checks.append(f"FAIL window library: {e!r}")
    with open(os.path.join(DATA_DIR, "smoke-test.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(results + checks + ["PASSED" if ok else "FAILED"]) + "\n")
    return ok


def main():
    # A windowed .exe has no console; give print() somewhere harmless to go.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    parser = argparse.ArgumentParser(description="SCC GFX Engine desktop app")
    add_arguments(parser)
    parser.add_argument("--debug", action="store_true", help="allow right-click > Inspect in the window")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    engine = build_engine(args)
    port = engine.settings.get()["http_port"]
    own_server = True
    try:
        start(engine)
    except OSError as e:
        if already_running(port):
            own_server = False   # another copy is running: open a window onto it
        else:
            message_box(f"Couldn't start the engine on port {port}:\n{e}\n\n"
                        "Another program may be using that port. Change http_port in settings.json.", error=True)
            return 1

    if args.smoke_test:
        ok = smoke_test(engine, port)
        engine.stop()
        return 0 if ok else 1

    url = f"http://127.0.0.1:{port}/control"
    try:
        import webview
        try:
            webview.settings["ALLOW_DOWNLOADS"] = True   # exports and backups
        except Exception:
            pass
        window = webview.create_window(f"{TITLE} {engine.updater.current}", url, width=1600, height=900,
                                       min_size=(1100, 680), background_color="#141619", text_select=True)
        engine.updater.on_exit = window.destroy
        webview.start(debug=args.debug)
    except Exception as e:
        # No WebView2 (very old Windows 10) or no window library: use the browser.
        log(f"Couldn't open the app window ({e!r}); using the web browser instead", "warn")
        webbrowser.open(url)
        if own_server:
            message_box("The GFX Engine has opened in your web browser.\n\n"
                        "It keeps running until you close this box.")
    finally:
        if own_server:
            engine.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
