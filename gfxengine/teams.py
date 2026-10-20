"""The team database every workspace shares: each team's name, short name,
logo and colour, to fill a side of the global configuration (or a bracket)
from a list instead of typing it.

It's a CSV file (library/teams.csv: Name, Short name, Logo, Colour) that can
be edited in a spreadsheet too. Logos added in the engine go in
library/teams/; in the CSV, a logo can also be a web address or the name of
a file in that folder.
"""

import csv
import io
import os
import re
import threading

COLUMNS = ("Name", "Short name", "Logo", "Colour")
# Column titles other spreadsheets use.
ALIASES = {"name": ("name", "team", "team name", "school"),
           "short": ("short name", "short", "abbreviation", "abbr", "tag", "code"),
           "logo": ("logo", "logo path", "image", "picture", "logo url"),
           "color": ("colour", "color", "team colour", "team color")}
MAX = 1000


def _clean(t):
    color = str(t.get("color") or "").strip()
    if color and not re.match(r"^#[0-9a-fA-F]{6}$", color):
        color = "#" + color if re.match(r"^[0-9a-fA-F]{6}$", color) else ""
    return {"name": str(t.get("name") or "").strip()[:120], "short": str(t.get("short") or "").strip()[:12],
            "logo": str(t.get("logo") or "").strip()[:300], "color": color}


class Teams:
    def __init__(self, library_dir):
        self.folder = os.path.join(library_dir, "teams")
        self.path = os.path.join(library_dir, "teams.csv")
        self.lock = threading.Lock()
        self.rev = 0
        self.teams = self._read()

    def _read(self):
        try:
            with open(self.path, encoding="utf-8-sig", newline="") as f:
                return self.parse(f.read())
        except OSError:
            return []

    def parse(self, text):
        """CSV text -> teams (the columns found by their titles)."""
        rows = [r for r in csv.reader(io.StringIO(text)) if any(c.strip() for c in r)]
        if not rows:
            return []
        head = [c.strip().lower() for c in rows[0]]
        cols = {k: next((head.index(a) for a in names if a in head), None) for k, names in ALIASES.items()}
        if cols["name"] is None:      # no titles: Name, Short name, Logo, Colour
            cols = {"name": 0, "short": 1, "logo": 2, "color": 3}
        else:
            rows = rows[1:]
        out = []
        for r in rows:
            t = _clean({k: (r[i] if i is not None and i < len(r) else "") for k, i in cols.items()})
            if not t["name"]:
                continue
            if t["logo"] and not re.match(r"^(https?:|assets/|library/)", t["logo"]):
                t["logo"] = "library/teams/" + os.path.basename(t["logo"])
            out.append(t)
        return out[:MAX]

    def csv_text(self, teams=None):
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(COLUMNS)
        for t in teams if teams is not None else self.teams:
            w.writerow([t["name"], t["short"], t["logo"], t["color"]])
        return buf.getvalue()

    def list(self):
        with self.lock:
            return [dict(t) for t in self.teams]

    def save(self, teams):
        """The whole list (as edited in Global)."""
        clean = [_clean(t) for t in teams or [] if isinstance(t, dict)]
        clean = [t for t in clean if t["name"]][:MAX]
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(self.csv_text(clean))
            os.replace(tmp, self.path)
            self.teams = clean
            self.rev += 1
        return self.list()

    def merge(self, teams):
        """Adds teams, or updates the ones with the same name. Returns how many."""
        current = self.list()
        index = {t["name"].lower(): i for i, t in enumerate(current)}
        for t in teams:
            i = index.get(t["name"].lower())
            if i is None:
                index[t["name"].lower()] = len(current)
                current.append(t)
            else:
                current[i].update({k: v for k, v in t.items() if v})
        self.save(current)
        return len(teams)

    def import_csv(self, text):
        teams = self.parse(text)
        if not teams:
            raise ValueError("No teams in that file: it needs a Name column (and Short name, Logo, Colour)")
        return self.merge(teams)

    def save_logo(self, name, filename, blob):
        """A logo for a team (added to the list if it isn't there)."""
        ext = os.path.splitext(filename or "")[1].lower()
        if ext not in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
            raise ValueError("The logo must be a PNG, JPG, WEBP, SVG or GIF")
        name = str(name or "").strip()
        base = re.sub(r"[^\w\- ]+", "_", name or os.path.splitext(os.path.basename(filename))[0]).strip() or "team"
        os.makedirs(self.folder, exist_ok=True)
        n, file = 2, base + ext
        while os.path.exists(os.path.join(self.folder, file)):
            file = f"{base} {n}{ext}"
            n += 1
        with open(os.path.join(self.folder, file), "wb") as f:
            f.write(blob)
        logo = "library/teams/" + file
        if name:
            self.merge([{"name": name, "short": "", "logo": logo, "color": ""}])
        return logo

    def find(self, name):
        """A team by its name (or short name), or None."""
        key = str(name or "").strip().lower()
        if not key:
            return None
        with self.lock:
            return next((dict(t) for t in self.teams if t["name"].lower() == key), None) or \
                next((dict(t) for t in self.teams if t["short"] and t["short"].lower() == key), None)

    def rows(self):
        """The "Teams" data table."""
        return [list(COLUMNS)] + [[t["name"], t["short"], t["logo"], t["color"]] for t in self.list()]
