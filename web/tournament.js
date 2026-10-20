// The Global page's ticker, the Teams page (the team list every workspace
// shares) and the Tournament page (the brackets the bracket graphics show).
"use strict";

(function globalExtras() {
  const pic = p => !p ? "" : /^https?:/.test(p) ? p : "/" + encodeURI(p);
  const table = () => (App.state && App.state.data.tables.Tournament) || [];
  const val = k => GFX.lookup(table(), k);

  // --- the ticker -----------------------------------------------------------------
  const ticker = $("#g-ticker");
  const saveTicker = debounce(() => api("/api/global", { global: { ticker: ticker.value.split("\n").map(s => s.trim()).filter(Boolean) } }), 400);
  ticker.addEventListener("input", saveTicker);
  function renderTicker() {
    const lines = (App.state.global.ticker || []).join("\n");
    if (document.activeElement !== ticker && ticker.value.split("\n").map(s => s.trim()).filter(Boolean).join("\n") !== lines) ticker.value = lines;
  }

  // --- the team list (its own tab): the list, and the picked team to edit -------------
  let teams = null;          // as edited here
  let sel = 0;               // the team being edited
  let teamsPending = false;
  const saveTeams = debounce(() => { teamsPending = false; api("/api/teams", { teams }); }, 400);
  const teamChanged = () => { teamsPending = true; saveTeams(); renderTeamList(); };
  const find = $("#t-find");
  find.addEventListener("input", () => renderTeamList());
  async function uploadTeamLogo(t, file) {
    if (!t.name.trim()) return toast("Name the team first", true);
    if (teamsPending) await new Promise(r => setTimeout(r, 450));    // (a name being typed is saved first)
    const r = await postFile(`/api/teams/logo?team=${encodeURIComponent(t.name.trim())}`, file);
    teams = r.teams;
    sel = Math.max(0, teams.findIndex(x => x.name === t.name.trim()));
    renderTeams();
    toast("Logo saved");
  }
  function renderTeamList() {
    const list = $("#t-list");
    const q = find.value.trim().toLowerCase();
    const shown = teams.map((t, i) => [t, i]).filter(([t]) => !q || t.name.toLowerCase().includes(q) || t.short.toLowerCase().includes(q));
    $("#t-count").textContent = `${teams.length} team${teams.length === 1 ? "" : "s"}`;
    list.replaceChildren(...(shown.length ? shown.map(([t, i]) => h("div", { class: "t-row" + (i === sel ? " sel" : ""), onclick: () => { sel = i; renderTeams(); } },
      h("div", { class: "t-logo" + (t.logo ? " has" : ""), style: { backgroundImage: t.logo ? `url("${pic(t.logo)}")` : "" } }),
      h("div", { class: "t-name" }, t.name || h("span", { class: "muted" }, "(no name)")),
      h("span", { class: "t-short" }, t.short),
      h("span", { class: "t-swatch", style: { background: t.color || "transparent" } })))
      : [h("div", { class: "empty" }, q ? "No team matches." : "No teams yet: + Add team, Import CSV, or “Save to the team list” on a team in Global.")]));
  }
  function renderTeamEditor() {
    const box = $("#t-edit");
    const t = teams[sel];
    if (!t) { box.replaceChildren(h("div", { class: "empty" }, "Pick a team on the left, or add one.")); return; }
    const fileIn = h("input", { type: "file", accept: "image/*", hidden: true,
      onchange: e => { const f = e.target.files[0]; e.target.value = ""; if (f) uploadTeamLogo(t, f); } });
    const drop = h("div", { class: "logo-drop big" + (t.logo ? " has" : ""), title: "Click or drop the logo",
      style: { backgroundImage: t.logo ? `url("${pic(t.logo)}")` : "" },
      onclick: () => fileIn.click(),
      ondragover: e => { e.preventDefault(); e.stopPropagation(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: e => { e.preventDefault(); e.stopPropagation(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) uploadTeamLogo(t, f); } },
      t.logo ? "" : "Click or drop the logo");
    const useAs = side => api("/api/global", { global: { [side]: Object.assign({ name: t.name, short: t.short, logo: t.logo }, t.color ? { color: t.color } : {}) } })
      .then(() => toast(`${t.name} is the ${side} team`));
    box.replaceChildren(
      h("div", { class: "panel-head" }, h("h3", {}, t.name || "New team"),
        h("button", { class: "small danger", onclick: () => {
          if (t.name && !confirm(`Remove ${t.name} from the team list?`)) return;
          teams.splice(sel, 1); sel = Math.max(0, sel - 1); teamChanged(); renderTeamEditor();
        } }, "Remove")),
      h("div", { class: "pad" },
        drop, fileIn,
        h("div", { class: "row-gap", style: { justifyContent: "center" } },
          t.logo ? h("button", { class: "ghost small", onclick: () => { t.logo = ""; teamChanged(); renderTeamEditor(); } }, "Remove logo") : null),
        h("label", {}, "Name", h("input", { value: t.name, placeholder: "e.g. St. Clair Saints", "data-k": "name",
          oninput: e => { t.name = e.target.value; box.querySelector("h3").textContent = t.name || "New team"; teamChanged(); } })),
        h("div", { class: "colour-row" },
          h("label", { style: { flex: 1 } }, "Short name", h("input", { value: t.short, maxlength: 12, placeholder: "e.g. SCC",
            oninput: e => { t.short = e.target.value; teamChanged(); } })),
          h("label", {}, "Colour", h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(t.color) ? t.color : "#333333",
            oninput: e => { t.color = e.target.value; teamChanged(); } }))),
        h("div", { class: "row-gap use-as" },
          h("button", { class: "small", onclick: () => useAs("left") }, "Use as the left team"),
          h("button", { class: "small", onclick: () => useAs("right") }, "Use as the right team"))));
  }
  function renderTeams(reload) {
    if (!teams || reload) teams = JSON.parse(JSON.stringify(App.state.teams || []));
    sel = Math.min(sel, Math.max(0, teams.length - 1));
    renderTeamList();
    renderTeamEditor();
    renderNames();
  }
  $("#t-add").addEventListener("click", () => {
    find.value = "";
    teams.unshift({ name: "", short: "", logo: "", color: "" });
    sel = 0;
    renderTeams();
    $("#t-edit input[data-k=name]").focus();
  });
  $("#t-import").addEventListener("click", () => $("#t-import-file").click());
  $("#t-import-file").addEventListener("change", async e => {
    const f = e.target.files[0]; e.target.value = "";
    if (!f) return;
    const r = await fetch("/api/teams/import", { method: "POST", body: f }).then(r => r.json());
    if (r.error) return toast(r.error, true);
    teams = r.teams;
    renderTeams();
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
    renderNames();
    if (App.tab === "global") renderTicker();
    if (App.tab === "tournament") renderTournament(false);
    const sig = JSON.stringify(s.teams);
    if (App.tab === "teams" && sig !== lastTeams) {
      lastTeams = sig;
      if (!teamsPending && !$("#t-edit").contains(document.activeElement)) renderTeams(true);
    }
  });
  const shown = pages.global.shown;
  pages.global.shown = () => { shown(); if (App.state) renderTicker(); };
  pages.teams = { shown() { if (App.state) { lastTeams = JSON.stringify(App.state.teams); renderTeams(true); } } };
  pages.tournament = { shown() { if (App.state) renderTournament(true); } };
})();
