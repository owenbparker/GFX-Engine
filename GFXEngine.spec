# PyInstaller build for the desktop app.
#
#   pip install -r requirements-windows.txt pyinstaller
#   pyinstaller --noconfirm GFXEngine.spec
#
# Produces dist/GFXEngine/GFXEngine.exe (plus its _internal folder). The GitHub
# Actions workflow in .github/workflows/build-windows.yml runs this.
import os
import sys

from PyInstaller.utils.hooks import collect_all

root = SPECPATH
icon = os.path.join(root, "packaging", "icon.ico")

hidden = []
datas = [(os.path.join(root, "web"), "web"), (os.path.join(root, "starter"), "starter")]
binaries = []
# FFmpeg (for converting video) and the PSD reader's data files.
for package in ("imageio_ffmpeg", "psd_tools"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hidden += h
hidden += ["openpyxl"]
if sys.platform == "win32":
    # pywebview's Windows window (Edge WebView2) is loaded at runtime.
    hidden += ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]

a = Analysis(
    [os.path.join(root, "GFXEngine.py")],
    pathex=[root],
    datas=datas,
    binaries=binaries,
    hiddenimports=hidden,
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GFXEngine",
    console=False,
    icon=icon if sys.platform == "win32" else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="GFXEngine")
