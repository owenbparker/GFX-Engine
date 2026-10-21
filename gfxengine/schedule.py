"""The upcoming schedule: the matches the Schedule graphic lists, set in the
Upcoming Schedule tab and kept in the workspace's global configuration.

    {"count": 3,       # how many the graphic shows (1, 2 or 3)
     "matches": [{"tournament", "game", "type", "team1", "team2",
                  "date": "2026-11-11", "time": "19:30"}, ...]}

The "Schedule" data table has, for each match n: {{Schedule!Match 1 tournament}},
{{Schedule!Match 1 game}} ("ROCKET LEAGUE | PLAYOFFS"), {{Schedule!Match 1 teams}}
("George Mason vs. St. Clair Saints"), {{Schedule!Match 1 when}}
("WED 11/11  |  7:30 PM"), the teams one by one (and their logos, from the
team list), and {{Schedule!Match 1 show}} ("1" when the graphic shows it).
"""

import datetime
import re

COUNTS = (1, 2, 3)
SLOTS = 3
MAX = 40
KEYS = ("tournament", "game", "type", "team1", "team2", "date", "time")


def default():
    return {"count": 3, "matches": []}


def clean(s):
    s = s if isinstance(s, dict) else {}
    try:
        count = int(s.get("count") or 3)
    except (TypeError, ValueError):
        count = 3
    matches = []
    for m in s.get("matches") or []:
        if not isinstance(m, dict):
            continue
        m = {k: str(m.get(k) or "").strip()[:120] for k in KEYS}
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", m["date"]):
            m["date"] = ""
        if not re.match(r"^\d{1,2}:\d{2}$", m["time"]):
            m["time"] = ""
        matches.append(m)
    return {"count": count if count in COUNTS else 3, "matches": matches[:MAX]}


def when(m):
    """"WED 11/11  |  7:30 PM" (as much of it as is set)."""
    parts = []
    if m["date"]:
        try:
            d = datetime.date.fromisoformat(m["date"])
            parts.append(f"{d.strftime('%a').upper()} {d.month}/{d.day}")
        except ValueError:
            pass
    if m["time"]:
        h, mi = (int(x) for x in m["time"].split(":"))
        parts.append(f"{(h % 12) or 12}:{mi:02d} {'AM' if h < 12 else 'PM'}")
    return "  |  ".join(parts)


def rows(s, find=None):
    """The "Schedule" data table: label | value. find(name) -> a team from the team list."""
    s = clean(s)
    shown = min(s["count"], len(s["matches"]))
    out = [["Field", "Value"], ["Count", str(shown)]]
    for n in range(1, max(SLOTS, len(s["matches"])) + 1):
        m = s["matches"][n - 1] if n <= len(s["matches"]) else dict.fromkeys(KEYS, "")
        game = " | ".join(x for x in (m["game"], m["type"]) if x)
        teams = " vs. ".join(x for x in (m["team1"], m["team2"]) if x)
        out += [[f"Match {n} tournament", m["tournament"]], [f"Match {n} game", game],
                [f"Match {n} teams", teams], [f"Match {n} when", when(m)],
                [f"Match {n} show", "1" if n <= shown else ""]]
        for t in (1, 2):
            name = m[f"team{t}"]
            info = (find(name) if find and name else None) or {}
            out += [[f"Match {n} team {t}", name], [f"Match {n} team {t} logo", info.get("logo", "")]]
    return out
