// Live data for Composer: what a layer can show, fill by or be shown by - the
// Global configuration, and what each game HUD sends (the Rocket League HUD's
// fields are listed even before it connects, so a graphic can be linked up
// ahead of the match).
"use strict";

window.LiveData = (function () {
  const RL = "Rocket League HUD";
  const STATS = [["goals", "goals"], ["shots", "shots"], ["assists", "assists"], ["saves", "saves"], ["demos", "demos"],
    ["score", "score"], ["touches", "touches"]];
  function rocketLeague() {
    const g = [];
    g.push(["Match", [
      ["clock", "Clock (5:00, +0:42)"], ["clock_seconds", "Clock in seconds"], ["overtime", "Overtime (1 in overtime)"],
      ["live", "In play (1 while the ball is live)"], ["replay", "Goal replay (1 during a replay)"],
      ["phase", "Phase (countdown, live, goal, replay, ended, podium)"], ["team_size", "Players a side (1, 2, 3)"],
      ["left_goals", "Left (blue) goals"], ["right_goals", "Right (orange) goals"],
      ["left_series", "Left games won (the HUD's)"], ["right_series", "Right games won (the HUD's)"],
      ["best_of", "Best of"], ["event", "Event"], ["stage", "Stage"], ["arena", "Arena"], ["ball_speed", "Ball speed (km/h)"]]]);
    const SP = "Spectated player's";
    g.push(["Spectated player", [
      ["target", SP + " name"], ["target_side", SP + " side (left / right)"], ["target_boost", SP + " boost (0-100)"],
      ...STATS.map(([k, t]) => ["target_" + k, `${SP} ${t}`]),
      ["target_speed", SP + " speed (km/h)"], ["target_logo", SP + " team logo"], ["target_color", SP + " team colour"],
      ["target_has_cam", SP + " cam is on (1)"], ["target_cam", SP + " cam (a web page layer)"]]]);
    for (const side of ["left", "right"]) {
      for (let n = 1; n <= 3; n++) {
        const k = `${side}_p${n}`, S = `${side === "left" ? "Left" : "Right"} player ${n}`;
        g.push([S, [[k + "_name", S + " name"], [k + "_boost", S + " boost (0-100)"],
          ...STATS.map(([s, t]) => [`${k}_${s}`, `${S} ${t}`]),
          [k + "_spectated", S + " is spectated (1)"], [k + "_demolished", S + " is demolished (1)"],
          [k + "_here", S + " is in the match (1)"]]]);
      }
    }
    g.push(["Goal (for 8 seconds after one)", [["goal_scorer", "Goal: scorer"], ["goal_assister", "Goal: assist by"],
      ["goal_speed", "Goal: speed (km/h)"], ["goal_side", "Goal: team side (left / right)"]]]);
    return g.map(([group, items]) => [`${RL}: ${group}`, items.map(([k, t]) => [`{{${RL}!${k}}}`, t])]);
  }
  function global() {
    const items = [["Event", "Event"], ["Stage", "Stage"], ["Best of", "Best of"], ["Game", "Game number"]];
    for (const S of ["Left", "Right"]) {
      items.push([`${S} name`, `${S} team name`], [`${S} short`, `${S} short name`], [`${S} logo`, `${S} team logo`],
        [`${S} color`, `${S} team colour`], [`${S} score`, `${S} series score (games won)`]);
      for (let n = 1; n <= 4; n++) items.push([`${S} won ${n}`, `${S} has won ${n} game${n > 1 ? "s" : ""} (series box ${n}, from the outside)`]);
    }
    for (let n = 1; n <= 4; n++) items.push([`Game box ${n}`, `Series box ${n} is used (from the best of)`]);
    items.push(["Tournament logo", "Tournament logo"], ["Sponsor logo", "First sponsor's logo"]);
    return [["Global", items.map(([k, t]) => [`{{Global!${k}}}`, t])]];
  }
  // Every group: [label, [[token, text]]], with what's live now that isn't listed.
  function groups() {
    const out = [...global(), ...rocketLeague()];
    const known = new Set(out.flatMap(([, items]) => items.map(([v]) => v.toLowerCase())));
    const data = (window.App && App.state && App.state.data) || {};
    for (const name of Object.keys(data.feeds || {})) {
      const rows = ((data.tables || {})[name] || []).slice(1);
      const extra = rows.map(r => [`{{${name}!${r[0]}}}`, r[0]]).filter(([v]) => !known.has(v.toLowerCase()));
      if (extra.length) out.push([`${name} (live now)`, extra]);
    }
    return out;
  }
  const isToken = v => /^\s*\{\{[^{}]+\}\}\s*$/.test(String(v || ""));
  const label = v => { for (const [, items] of groups()) for (const [t, text] of items) if (t === v) return text; return v; };
  // A dropdown of the data; "first" is the option for nothing.
  function select(value, onChange, first) {
    const gs = groups();
    const found = gs.some(([, items]) => items.some(([v]) => v === value));
    return h("select", { onchange: e => onChange(e.target.value) },
      h("option", { value: "" }, first || "(none)"),
      value && !found ? h("option", { value, selected: true }, value) : null,
      gs.map(([group, items]) => h("optgroup", { label: group }, items.map(([v, t]) => h("option", { value: v, selected: v === value }, t)))));
  }
  return { groups, select, isToken, label, RL };
})();
