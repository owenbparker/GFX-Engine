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
  // Each team: its name, short name, game, colour and logo, and its roster (each
  // player's headshot, name, in-game ID and country).
  let teams = null;          // as edited here
  let sel = 0;               // the team being edited
  let teamsPending = false;
  let countries = [];        // [{code, name}] of the flags that come with the engine
  fetch("/flags/countries.json").then(r => r.json()).then(c => { countries = c; if (App.tab === "teams" && teams) renderTeamEditor(); }).catch(() => {});
  const flagOf = code => code ? `/flags/${code}.svg` : "";
  const saveTeams = debounce(() => { teamsPending = false; api("/api/teams", { teams }); }, 400);
  const teamChanged = () => { teamsPending = true; saveTeams(); renderTeamList(); };
  const find = $("#t-find");
  const gameFilter = $("#t-game");
  find.addEventListener("input", () => renderTeamList());
  gameFilter.addEventListener("change", () => renderTeamList());
  const label = t => t.name + (t.game ? ` · ${t.game}` : "");
  function dropZone(cls, src, empty, onfile) {
    const fileIn = h("input", { type: "file", accept: "image/*", hidden: true,
      onchange: e => { const f = e.target.files[0]; e.target.value = ""; if (f) onfile(f); } });
    const drop = h("div", { class: cls + (src ? " has" : ""), title: "Click or drop a picture",
      style: { backgroundImage: src ? `url("${pic(src)}")` : "" },
      onclick: () => fileIn.click(),
      ondragover: e => { e.preventDefault(); e.stopPropagation(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: e => { e.preventDefault(); e.stopPropagation(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) onfile(f); } },
      src ? "" : empty, fileIn);
    return drop;
  }
  async function uploadTeamLogo(t, file) {
    if (!t.name.trim()) return toast("Name the team first", true);
    if (teamsPending) await new Promise(r => setTimeout(r, 450));    // (a name being typed is saved first)
    const r = await postFile(`/api/teams/logo?team=${encodeURIComponent(t.name.trim())}&game=${encodeURIComponent(t.game || "")}`, file);
    teams = r.teams;
    sel = Math.max(0, teams.findIndex(x => x.name === t.name.trim() && (x.game || "") === (t.game || "")));
    renderTeams();
    toast("Logo saved");
  }
  async function uploadHeadshot(t, p, file) {
    const r = await postFile(`/api/teams/photo?player=${encodeURIComponent(p.ign || p.name || t.name)}`, file);
    p.photo = r.photo;
    teamChanged();
    renderTeamEditor();
  }
  // The games there are HUDs for, then any other a team has (from a CSV, say).
  const allGames = () => [...new Set([...(App.state.games || []), ...teams.map(t => t.game).filter(Boolean)])];
  function gameSelect(t) {
    const sel = h("select", { "data-k": "game", onchange: e => { t.game = e.target.value; teamChanged(); renderTeamEditor(); } },
      h("option", { value: "" }, "Pick the game…"), ...allGames().map(g => h("option", { value: g }, g)));
    sel.value = t.game || "";
    return sel;
  }
  function renderGames() {
    const games = allGames();
    const sig = JSON.stringify(games);
    if (gameFilter.dataset.sig !== sig) {
      gameFilter.dataset.sig = sig;
      const was = gameFilter.value;
      gameFilter.replaceChildren(h("option", { value: "" }, "All games"), ...games.map(g => h("option", { value: g }, g)));
      gameFilter.value = games.includes(was) ? was : "";
    }
  }
  function renderTeamList() {
    renderGames();
    const list = $("#t-list");
    const q = find.value.trim().toLowerCase(), g = gameFilter.value;
    const shown = teams.map((t, i) => [t, i]).filter(([t]) => (!g || t.game === g) && (!q || t.name.toLowerCase().includes(q) || t.short.toLowerCase().includes(q)));
    $("#t-count").textContent = `${teams.length} team${teams.length === 1 ? "" : "s"}`;
    list.replaceChildren(...(shown.length ? shown.map(([t, i]) => h("div", { class: "t-row" + (i === sel ? " sel" : ""), onclick: () => { sel = i; renderTeams(); } },
      h("div", { class: "t-logo" + (t.logo ? " has" : ""), style: { backgroundImage: t.logo ? `url("${pic(t.logo)}")` : "" } }),
      h("div", { class: "t-who" }, h("div", { class: "t-name" }, t.name || h("span", { class: "muted" }, "(no name)")),
        h("div", { class: "t-sub" }, [t.short, t.game].filter(Boolean).join(" · "))),
      h("span", { class: "t-count", title: "Players" }, String((t.players || []).length))))
      : [h("div", { class: "empty" }, q || g ? "No team matches." : "No teams yet: + Add team, Import CSV, or “Save to the team list” on a team in Global.")]));
  }
  function countrySelect(p) {
    const flag = h("img", { class: "t-flag", src: flagOf(p.country), hidden: !p.country, alt: "" });
    const sel = h("select", { onchange: e => { p.country = e.target.value; flag.src = flagOf(p.country); flag.hidden = !p.country; teamChanged(); } },
      h("option", { value: "" }, "—"), ...countries.map(c => h("option", { value: c.code }, c.name)));
    sel.value = p.country || "";
    return h("div", { class: "t-country" }, flag, sel);
  }
  function playerRow(t, p, i) {
    const players = t.players;
    const move = d => { const j = i + d; if (j < 0 || j >= players.length) return; [players[i], players[j]] = [players[j], players[i]]; teamChanged(); renderTeamEditor(); };
    return h("tr", {},
      h("td", { class: "t-num" }, String(i + 1)),
      h("td", {}, dropZone("t-head", p.photo, "+", f => uploadHeadshot(t, p, f))),
      h("td", {}, h("input", { value: p.name, placeholder: "Player name", oninput: e => { p.name = e.target.value; teamChanged(); } })),
      h("td", {}, h("input", { value: p.ign, placeholder: "In-game ID", oninput: e => { p.ign = e.target.value; teamChanged(); } })),
      h("td", {}, countrySelect(p)),
      h("td", { class: "t-acts" },
        h("button", { class: "ghost small", title: "Move up", disabled: i === 0, onclick: () => move(-1) }, "↑"),
        h("button", { class: "ghost small", title: "Move down", disabled: i === players.length - 1, onclick: () => move(1) }, "↓"),
        p.photo ? h("button", { class: "ghost small", title: "Remove the headshot", onclick: () => { p.photo = ""; teamChanged(); renderTeamEditor(); } }, "⌫") : null,
        h("button", { class: "ghost small", title: "Remove the player", onclick: () => { players.splice(i, 1); teamChanged(); renderTeamEditor(); } }, "✕")));
  }
  function renderTeamEditor() {
    const box = $("#t-edit");
    const t = teams[sel];
    if (!t) { box.replaceChildren(h("div", { class: "empty" }, "Pick a team on the left, or add one.")); return; }
    t.players = t.players || [];
    const useAs = side => api("/api/global", { global: { [side]: Object.assign({ name: t.name, short: t.short, logo: t.logo, game: t.game || "" }, t.color ? { color: t.color } : {}) } })
      .then(() => toast(`${t.name} is the ${side} team`));
    const head = h("div", { class: "t-head-title" }, h("b", {}, t.name || "New team"), h("span", { class: "muted" }, t.short ? ` / ${t.short}` : ""),
      h("div", { class: "muted small" }, t.game || "No game set"));
    box.replaceChildren(
      h("div", { class: "t-top" },
        h("div", { class: "t-logo big" + (t.logo ? " has" : ""), style: t.logo ? { backgroundImage: `url("${pic(t.logo)}")` } : { background: t.color || "" } }),
        head, h("div", { class: "spacer" }),
        h("button", { class: "small", onclick: () => useAs("left") }, "Use as left team"),
        h("button", { class: "small", onclick: () => useAs("right") }, "Use as right team"),
        h("button", { class: "small danger", title: "Remove the team", onclick: () => {
          if (t.name && !confirm(`Remove ${label(t)} from the team list?`)) return;
          teams.splice(sel, 1); sel = Math.max(0, sel - 1); teamChanged(); renderTeamEditor();
        } }, "🗑")),
      h("section", { class: "t-sect" },
        h("div", { class: "t-sect-head" }, h("h4", {}, "Team details"), h("p", { class: "muted small" }, "What the graphics show for this team.")),
        h("div", { class: "t-fields" },
          h("label", {}, "Name", h("input", { value: t.name, placeholder: "e.g. St. Clair Saints", "data-k": "name",
            oninput: e => { t.name = e.target.value; head.querySelector("b").textContent = t.name || "New team"; teamChanged(); } })),
          h("label", {}, "Short name", h("input", { value: t.short, maxlength: 12, placeholder: "e.g. SCC",
            oninput: e => { t.short = e.target.value; teamChanged(); } })),
          h("label", {}, "Game", gameSelect(t)),
          h("label", {}, "Colour", h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(t.color) ? t.color : "#333333",
            oninput: e => { t.color = e.target.value; teamChanged(); } })))),
      h("section", { class: "t-sect" },
        h("div", { class: "t-sect-head" }, h("h4", {}, "Team logo"), h("p", { class: "muted small" }, "Click or drop the logo. A big PNG looks sharpest.")),
        h("div", { class: "row-gap t-logo-row" }, dropZone("logo-drop big", t.logo, "Click or drop the logo", f => uploadTeamLogo(t, f)),
          t.logo ? h("button", { class: "ghost small", onclick: () => { t.logo = ""; teamChanged(); renderTeamEditor(); } }, "Remove logo") : null)),
      h("section", { class: "t-sect" },
        h("div", { class: "t-sect-head row-gap" }, h("div", {}, h("h4", {}, "Team members"),
          h("p", { class: "muted small" }, "The player graphics show these, in this order: the headshot, the flag and the name (or the in-game ID).")),
          h("div", { class: "spacer" }),
          h("button", { class: "small", onclick: () => { t.players.push({ name: "", ign: "", country: "", photo: "" }); teamChanged(); renderTeamEditor();
            const rows = box.querySelectorAll(".t-roster tbody tr"); rows[rows.length - 1].querySelector("input").focus(); } }, "+ Add player")),
        t.players.length ? h("table", { class: "t-roster" },
          h("thead", {}, h("tr", {}, h("th", {}, "#"), h("th", {}, "Headshot"), h("th", {}, "Player name"), h("th", {}, "In-game ID"), h("th", {}, "Country"), h("th", {}))),
          h("tbody", {}, ...t.players.map((p, i) => playerRow(t, p, i))))
          : h("div", { class: "empty" }, "No players yet: + Add player.")));
    return head;
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
    teams.unshift({ name: "", short: "", logo: "", color: "", game: gameFilter.value || "", players: [] });
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
    const names = [...new Set((App.state.teams || []).map(t => t.name).filter(Boolean))];
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
