"""The tournament: the two brackets the SCC bracket graphics show, set in
Global and kept in the workspace's global configuration.

    "top":    the knockout bracket (8 or 16 teams): the first round's teams,
              and each match's scores ("R1 M1": ["2", "1"]). Winners go
              through to the next round by themselves; a team with nobody
              against it in the first round goes straight through.
    "groups": four groups (A-D) of four teams, played GSL style: two
              opening matches, the winners' match (its winner is 1st), the
              elimination match between the openings' losers, and the
              decider (the winners' match loser against the elimination
              winner, for 2nd).

The "Tournament" data table has every slot, e.g. {{Tournament!Top R1 M1 team 1}},
{{Tournament!Top R1 M1 team 1 score}}, {{Tournament!Top champion}},
{{Tournament!Group A Winners team 2 logo}}, {{Tournament!Group A 1st}};
and for the final four: {{Tournament!Top semi 1}} ... {{Tournament!Top final 2}}.
"""

SIZES = (8, 16)
GROUP_NAMES = ("A", "B", "C", "D")
GROUP_MATCHES = ("Opening 1", "Opening 2", "Winners", "Elimination", "Decider")
ROUND_NAMES = {16: ("Round of 16", "Quarter-finals", "Semi-finals", "Final"),
               8: ("Quarter-finals", "Semi-finals", "Final")}


def _score(v):
    return str(v if v is not None else "").strip()[:6]


def _scores(raw, keys):
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k in keys:
        pair = raw.get(k)
        if isinstance(pair, (list, tuple)) and len(pair) == 2 and any(_score(x) for x in pair):
            out[k] = [_score(pair[0]), _score(pair[1])]
    return out


def match_keys(size):
    keys, n, r = [], size // 2, 1
    while n >= 1:
        keys += [f"R{r} M{m}" for m in range(1, n + 1)]
        n //= 2
        r += 1
    return keys


def default():
    return {"top": {"size": 8, "teams": [""] * 16, "scores": {}},
            "groups": [{"name": f"GROUP {g}", "teams": [""] * 4, "scores": {}} for g in GROUP_NAMES]}


def clean(t):
    t = t if isinstance(t, dict) else {}
    top = t.get("top") if isinstance(t.get("top"), dict) else {}
    try:
        size = int(top.get("size") or 8)
    except (TypeError, ValueError):
        size = 8
    size = size if size in SIZES else 8
    teams = [str(x or "").strip()[:120] for x in (top.get("teams") or [])][:16]
    out = {"top": {"size": size, "teams": teams + [""] * (16 - len(teams)), "scores": _scores(top.get("scores"), match_keys(16))}}
    groups = t.get("groups") if isinstance(t.get("groups"), list) else []
    out["groups"] = []
    for i, g in enumerate(GROUP_NAMES):
        raw = groups[i] if i < len(groups) and isinstance(groups[i], dict) else {}
        gt = [str(x or "").strip()[:120] for x in (raw.get("teams") or [])][:4]
        out["groups"].append({"name": str(raw.get("name") or f"GROUP {g}")[:40], "teams": gt + [""] * (4 - len(gt)),
                              "scores": _scores(raw.get("scores"), GROUP_MATCHES)})
    return out


def result(a, b, score, byes=False):
    """(winner, loser) of a match, or ("", "") while it isn't decided."""
    if byes and a and not b:
        return a, ""
    if byes and b and not a:
        return b, ""
    if not (a and b and score):
        return "", ""
    try:
        sa, sb = float(score[0]), float(score[1])
    except (TypeError, ValueError):
        return "", ""
    if sa == sb:
        return "", ""
    return (a, b) if sa > sb else (b, a)


def top_rounds(top):
    """[[{"teams": [a, b], "score": [x, y], "winner"}, ...] per round], champion."""
    size = top["size"]
    cur = top["teams"][:size]
    rounds, r = [], 1
    while len(cur) > 1:
        matches = []
        for m in range(len(cur) // 2):
            a, b = cur[2 * m], cur[2 * m + 1]
            score = top["scores"].get(f"R{r} M{m + 1}", ["", ""])
            win, _ = result(a, b, score, byes=r == 1)
            matches.append({"teams": [a, b], "score": score, "winner": win})
        rounds.append(matches)
        cur = [m["winner"] for m in matches]
        r += 1
    return rounds, cur[0] if cur else ""


def group_matches(group):
    """{match: {"teams", "score", "winner", "loser"}}, 1st, 2nd."""
    t, sc = group["teams"], group["scores"]
    out = {}

    def play(name, a, b):
        score = sc.get(name, ["", ""])
        win, lose = result(a, b, score)
        out[name] = {"teams": [a, b], "score": score, "winner": win, "loser": lose}
        return win, lose

    w1, l1 = play("Opening 1", t[0], t[1])
    w2, l2 = play("Opening 2", t[2], t[3])
    first, wl = play("Winners", w1, w2)
    ew, _ = play("Elimination", l1, l2)
    second, _ = play("Decider", wl, ew)
    return out, first, second


def rows(t, find=None):
    """The "Tournament" data table: label | value. find(name) -> a team from the database."""
    t = clean(t)
    out = [["Field", "Value"]]

    def team(label, name, score=None):
        info = (find(name) if find and name else None) or {}
        out.extend([[label, name], [label + " short", info.get("short") or name],
                    [label + " logo", info.get("logo", "")]])
        if score is not None:
            out.append([label + " score", score])

    top = t["top"]
    out.append(["Top teams", str(top["size"])])
    rounds, champion = top_rounds(top)
    for r, matches in enumerate(rounds, 1):
        for m, match in enumerate(matches, 1):
            for s in range(2):
                team(f"Top R{r} M{m} team {s + 1}", match["teams"][s], match["score"][s])
    team("Top champion", champion)
    # The last rounds by name, for the final four.
    if len(rounds) >= 2:
        for i, (match, s) in enumerate([(m, s) for m in rounds[-2] for s in range(2)], 1):
            team(f"Top semi {i}", match["teams"][s], match["score"][s])
    for s in range(2):
        team(f"Top final {s + 1}", rounds[-1][0]["teams"][s], rounds[-1][0]["score"][s])
    for g, group in zip(GROUP_NAMES, t["groups"]):
        out.append([f"Group {g} name", group["name"]])
        matches, first, second = group_matches(group)
        for name, match in matches.items():
            for s in range(2):
                team(f"Group {g} {name} team {s + 1}", match["teams"][s], match["score"][s])
        team(f"Group {g} 1st", first)
        team(f"Group {g} 2nd", second)
    return out
