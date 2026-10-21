"""Where things live, and the app's own settings (settings.json).

The graphics themselves (compositions, transitions, data sources) and their
files are workspaces: workspaces/<id>/project.json and assets/, next to the
app (next to GFXEngine.exe in the desktop build). Fonts are shared by every
workspace, in library/fonts.
"""

import copy
import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FROZEN = getattr(sys, "frozen", False)
RESOURCE_DIR = getattr(sys, "_MEIPASS", ROOT) if FROZEN else ROOT
DATA_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else ROOT
WEB_DIR = os.path.join(RESOURCE_DIR, "web")
STARTER_DIR = os.path.join(RESOURCE_DIR, "starter")
WORKSPACES_DIR = os.path.join(DATA_DIR, "workspaces")
LEGACY_WORKSPACE_DIR = os.path.join(DATA_DIR, "workspace")   # (v1.0.1: one workspace)
LIBRARY_DIR = os.path.join(DATA_DIR, "library")             # shared by every workspace (fonts)
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")

# Not the League (8777, 8779), VALORANT (8778), CoD (8780), RL (8781) HUDs'
# or the HUD Manager's (8790) ports. Engines find each other on DISCOVERY_PORT.
PORT = 8782
DISCOVERY_PORT = 8783

DEFAULTS = {
    "http_port": PORT,
    # Other PCs can open the outputs and the control panel, and find this
    # engine (it announces itself on the network).
    "allow_network": True,
    # The one network other PCs reach it on (this PC's address on it, e.g. the
    # NDI VLAN's), or "" for every network.
    "network_address": "",
    # This engine's name on the network.
    "name": "",
    # The workspace open (its folder in workspaces/).
    "workspace": "",
}

_lock = threading.Lock()


class Settings:
    def __init__(self, path=SETTINGS_PATH):
        self.path = path
        self.data = copy.deepcopy(DEFAULTS)
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    self.data.update(json.load(f))
            except (OSError, ValueError):
                pass

    def get(self):
        with _lock:
            return copy.deepcopy(self.data)

    def update(self, changes):
        with _lock:
            self.data.update({k: v for k, v in changes.items() if k in DEFAULTS})
            snapshot = copy.deepcopy(self.data)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2)
        os.replace(tmp, self.path)
        return snapshot


def safe_join(base, rel):
    """base/rel on disk if it's a file inside base, else None."""
    rel = rel.replace("\\", "/").lstrip("/")
    path = os.path.normpath(os.path.join(base, rel))
    if not path.startswith(os.path.normpath(base) + os.sep) or not os.path.isfile(path):
        return None
    return path
