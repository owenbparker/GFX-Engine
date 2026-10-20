// The Global page's ticker, team list (every workspace shares it) and
// tournament (the brackets the bracket graphics show).
"use strict";

(function globalExtras() {
  const pic = p => !p ? "" : /^https?:/.test(p) ? p : "/" + encodeURI(p);
  const table = () => (App.state && App.state.data.tables.Tournament) || [];
  const val = k => GFX.lookup(table(), k);
  const onGlobal = () => App.tab === "global";

  // --- the ticker -----------------------------------------------------------------
  const ticker = $("#g-ticker");
  const saveTicker = debounce(() => api("/api/global", { global: { ticker: ticker.value.split("\n").map(s => s.trim()).filter(Boolean) } }), 400);
  ticker.addEventListener("input", saveTicker);
  function renderTicker() {
    const lines = (App.state.global.ticker || []).join("\n");
    if (document.activeElement !== ticker && ticker.value.split("\n").map(s => s.trim()).filter(Boolean).join("\n") !== lines) ticker.value = lines;
  }

  // --- the team list ----------------------------------------------------------------
  let teams = null;          // as edited here
  const saveTeams = debounce(() => api("/api/teams", { teams }), 400);
  const find = $("#t-find");
  find.addEventListener("input", () => renderTeams(true));
  function teamLogo(t, i) {
    const input = h("input", { type: "file", accept: "image/*", hidden: true,
      onchange: e => { const f = e.target.files[0]; e.target.value = ""; if (f) uploadTeamLogo(t, f); } });
    const box = h("div", { class: "t-logo" + (t.logo ? " has" : ""), title: "Click or drop the logo",
      style: { backgroundImage: t.logo ? `url("${pic(t.logo)}")` : "" },
      onclick: () => input.click(),
      ondragover: e => { e.preventDefault(); e.stopPropagation(); box.classList.add("over"); },
      ondragleave: () => box.classList.remove("over"),
      ondrop: e => { e.preventDefault(); e.stopPropagation(); box.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) uploadTeamLogo(t, f); } },
      t.logo ? "" : "+");
    return [box, input];
  }
  async function uploadTeamLogo(t, file) {
    if (!t.name.trim()) return toast("Name the team first", true);
    await new Promise(r => setTimeout(r, 450));       // (a name being typed is saved first)
    const r = await postFile(`/api/teams/logo?team=${encodeURIComponent(t.name.trim())}`, file);
    teams = r.teams;
    renderTeams(true);
    toast("Logo saved");
  }
  function renderTeams(force) {
    const list = $("#t-list");
    if (!teams || force === "reload") teams = JSON.parse(JSON.stringify(App.state.teams || []));
    const sig = JSON.stringify([teams, find.value]);
    if (!force && (list.dataset.sig === sig || list.contains(document.activeElement))) return;
    list.dataset.sig = sig;
    const q = find.value.trim().toLowerCase();
    const shown = teams.map((t, i) => [t, i]).filter(([t]) => !q || t.name.toLowerCase().includes(q) || t.short.toLowerCase().includes(q));
    list.replaceChildren(...(shown.length ? shown.map(([t, i]) => h("div", { class: "t-row" },
      ...teamLogo(t, i),
      h("input", { value: t.name, placeholder: "Name", oninput: e => { t.name = e.target.value; saveTeams(); } }),
      h("input", { value: t.short, placeholder: "Short", maxlength: 12, class: "t-short", oninput: e => { t.short = e.target.value; saveTeams(); } }),
      h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(t.color) ? t.color : "#333333", title: "Colour",
        oninput: e => { t.color = e.target.value; saveTeams(); } }),
      h("button", { class: "ghost small", title: "Remove", onclick: () => { teams.splice(i, 1); saveTeams(); renderTeams(true); } }, "✕")))
      : [h("div", { class: "muted small" }, q ? "No team matches." : "No teams yet. Add them here, import a CSV, or use “Save to the team list” on a team above.")]));
    renderNames();
  }
  $("#t-add").addEventListener("click", () => {
    find.value = "";
    teams.unshift({ name: "", short: "", logo: "", color: "" });
    renderTeams(true);
    $("#t-list input").focus();
  });
  $("#t-import").addEventListener("click", () => $("#t-import-file").click());
  $("#t-import-file").addEventListener("change", async e => {
    const f = e.target.files[0]; e.target.value = "";
    if (!f) return;
    const r = await fetch("/api/teams/import", { method: "POST", body: f }).then(r => r.json());
    if (r.error) return toast(r.error, true);
    teams = r.teams;
    renderTeams(true);
    toast(`${r.added} team${r.added === 1 ? "" : "s"} imported`);
  });
  // The names to pick from.
  function renderNames() {
    const dl = $("#team-names");
    const names = (App.state.teams || []).map(t => t.name).filter(Boolean);
    const sig = JSON.stringify(names);
    if (dl.dataset.sig === sig) return;
    dl.dataset.sig = sig;
    dl.replaceChildren(...names.map(n => h("option", { value: n })));
  }
  window.teamList = () => App.state.teams || [];

  // --- the tournament -----------------------------------------------------------------
  let t = null;              // as edited here
  let pending = false;
  const saveT = debounce(() => { pending = false; api("/api/global", { global: { tournament: t } }); }, 350);
  const changed = () => { pending = true; saveT(); };
  const ROUNDS = { 8: ["Quarter-finals", "Semi-finals", "Final"], 16: ["Round of 16", "Quarter-finals", "Semi-finals", "Final"] };
  const GROUP_MATCHES = ["Opening 1", "Opening 2", "Winners", "Elimination", "Decider"];

  function teamInput(value, onchange) {
    return h("input", { class: "tn-team", list: "team-names", value, placeholder: "Team",
      oninput: e => { onchange(e.target.value); } });
  }
  function scoreInput(scores, key, side) {
    return h("input", { class: "tn-score", value: (scores[key] || ["", ""])[side], inputmode: "numeric", "data-score": key + "|" + side,
      oninput: e => {
        const pair = scores[key] || ["", ""];
        pair[side] = e.target.value.trim();
        if (pair[0] || pair[1]) scores[key] = pair; else delete scores[key];
        changed();
      } });
  }
  const logoOf = name => { const tm = (App.state.teams || []).find(x => x.name.toLowerCase() === String(name || "").toLowerCase()); return tm && tm.logo; };
  const nameBox = row => h("div", { class: "tn-name", "data-row": row });

  function renderTop() {
    const top = t.top, size = top.size, box = $("#tn-top");
    for (const b of document.querySelectorAll("#tn-size button")) b.classList.toggle("on", +b.dataset.size === size);
    const cols = ROUNDS[size].map((title, r) => {
      const matches = [];
      for (let m = 0; m < size >> (r + 1); m++) {
        const key = `R${r + 1} M${m + 1}`;
        const side = s => h("div", { class: "tn-slot" },
          h("i", { class: "tn-logo", "data-logo": `Top ${key} team ${s + 1}` }),
          r === 0 ? teamInput(top.teams[2 * m + s], v => { top.teams[2 * m + s] = v; changed(); }) : nameBox(`Top ${key} team ${s + 1}`),
          scoreInput(top.scores, key, s));
        matches.push(h("div", { class: "tn-match" }, side(0), side(1)));
      }
      return h("div", { class: "tn-col" }, h("div", { class: "tn-title" }, title), h("div", { class: "tn-col-body" }, ...matches));
    });
    cols.push(h("div", { class: "tn-col champ" }, h("div", { class: "tn-title" }, "Champion"),
      h("div", { class: "tn-col-body" }, h("div", { class: "tn-match" }, h("div", { class: "tn-slot" },
        h("i", { class: "tn-logo", "data-logo": "Top champion" }), nameBox("Top champion"))))));
    box.replaceChildren(...cols);
  }
  document.querySelectorAll("#tn-size button").forEach(b => b.addEventListener("click", () => {
    t.top.size = +b.dataset.size; changed(); renderTop(); refresh();
  }));
  $("#tn-top-scores").addEventListener("click", () => { if (confirm("Clear every score in the knockout bracket?")) { t.top.scores = {}; changed(); renderTop(); } });
  $("#tn-group-scores").addEventListener("click", () => { if (confirm("Clear every score in the groups?")) { t.groups.forEach(g => (g.scores = {})); changed(); renderGroups(); } });

  function renderGroups() {
    $("#tn-groups").replaceChildren(...t.groups.map((g, gi) => {
      const L = "ABCD"[gi];
      return h("div", { class: "tn-group" },
        h("input", { class: "tn-gname", value: g.name, oninput: e => { g.name = e.target.value; changed(); } }),
        h("div", { class: "tn-seeds" }, ...g.teams.map((name, i) => h("div", { class: "tn-slot" },
          h("span", { class: "muted small tn-seed" }, String(i + 1)),
          teamInput(name, v => { g.teams[i] = v; changed(); })))),
        ...GROUP_MATCHES.map(m => h("div", { class: "tn-gmatch" },
          h("div", { class: "tn-mname muted small" }, m === "Winners" ? "Winners' match" : m === "Elimination" ? "Elimination" : m),
          h("div", { class: "tn-match" },
            ...[0, 1].map(s => h("div", { class: "tn-slot" }, nameBox(`Group ${L} ${m} team ${s + 1}`), scoreInput(g.scores, m, s)))))),
        h("div", { class: "tn-result" }, h("span", { class: "muted small" }, "1st"), nameBox(`Group ${L} 1st`),
          h("span", { class: "muted small" }, "2nd"), nameBox(`Group ${L} 2nd`)));
    }));
  }

  // The winners (worked out by the engine), the logos and the values typed elsewhere.
  function refresh() {
    for (const el of document.querySelectorAll(".g-tournament [data-row]")) el.textContent = val(el.dataset.row) || "—";
    for (const el of document.querySelectorAll(".g-tournament [data-logo]")) {
      const logo = val(el.dataset.logo + " logo");
      el.style.backgroundImage = logo ? `url("${pic(logo)}")` : "";
    }
    for (const el of document.querySelectorAll(".g-tournament .tn-team")) el.title = logoOf(el.value) ? "" : el.value ? "Not in the team list (no logo)" : "";
  }
  function renderTournament(force) {
    const panel = document.querySelector(".g-tournament");
    const editing = panel.contains(document.activeElement) || pending;
    const server = App.state.global.tournament;
    if (!t || (force && !pending)) { t = JSON.parse(JSON.stringify(server)); force = true; }
    else if (!editing && JSON.stringify(t) !== JSON.stringify(server)) { t = JSON.parse(JSON.stringify(server)); force = true; }
    if (force) { renderTop(); renderGroups(); }
    refresh();
  }

  // --- in step with the engine ----------------------------------------------------------
  let lastTeams = "";
  App.on(s => {
    if (!onGlobal()) return;
    renderTicker();
    const sig = JSON.stringify(s.teams);
    if (sig !== lastTeams) { lastTeams = sig; if (!$("#t-list").contains(document.activeElement)) renderTeams("reload"); renderNames(); }
    renderTournament(false);
  });
  const shown = pages.global.shown;
  pages.global.shown = () => {
    shown();
    if (!App.state) return;
    renderTicker();
    renderTeams("reload");
    renderTournament(true);
  };
})();
