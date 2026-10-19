// The Home page (the workspaces: open one, make a new one with a name and a
// picture) and the Global page (the teams, the series and the event, which
// every graphic can use as {{Global!...}} and the game HUDs keep up to date).
"use strict";

const initials = name => (String(name || "").match(/\b[\p{L}\p{N}]/gu) || ["?"]).slice(0, 2).join("").toUpperCase();
function wsPicture(el, ws, bust) {
  if (ws.picture) { el.style.backgroundImage = `url("/api/workspace-picture/${encodeURIComponent(ws.id)}?v=${bust || ""}")`; el.textContent = ""; }
  else { el.style.backgroundImage = ""; el.textContent = initials(ws.name); }
}
async function postFile(path, file) {
  const r = await fetch(path + (path.includes("?") ? "&" : "?") + "name=" + encodeURIComponent(file.name),
    { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.error) { toast(data.error || "Upload failed", true); throw new Error(data.error); }
  return data;
}
function ago(t) {
  const s = Date.now() / 1000 - t;
  if (s < 90) return "just now";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400 * 2) return Math.round(s / 3600) + " h ago";
  return new Date(t * 1000).toLocaleDateString();
}

// --- the header's workspace chip ---------------------------------------------------
let picBust = Date.now();
$("#brand").addEventListener("click", () => showTab("home"));
$("#ws-pic").addEventListener("click", () => showTab("home"));
App.on(s => {
  const w = s.workspace;
  const pic = $("#ws-pic");
  const sig = JSON.stringify([w.id, w.name, w.picture, picBust]);
  if (pic.dataset.sig !== sig) { pic.dataset.sig = sig; wsPicture(pic, w, picBust); }
});

// --- HOME ---------------------------------------------------------------------------
(function home() {
  let list = [], current = null;
  async function load() {
    const r = await fetch("/api/workspaces").then(r => r.json());
    list = r.workspaces; current = r.current;
    render();
  }
  function render() {
    const grid = $("#ws-grid");
    grid.replaceChildren(
      ...list.map(w => {
        const cover = h("div", { class: "cover" });
        wsPicture(cover, w, picBust);
        return h("div", { class: "ws-card" + (w.id === current ? " current" : ""), role: "button", tabindex: 0,
          onclick: () => open(w), onkeydown: e => { if (e.key === "Enter") open(w); } },
          cover,
          w.id === current ? h("span", { class: "badge" }, "OPEN") : null,
          h("button", { class: "menu small", title: "Rename, picture, delete", onclick: e => { e.stopPropagation(); edit(w); } }, "⋯"),
          h("div", { class: "info" }, h("div", { class: "name" }, w.name),
            h("div", { class: "sub" }, `${w.graphics} graphic${w.graphics === 1 ? "" : "s"} · ${ago(w.updated)}`)));
      }),
      h("button", { class: "ws-card add", onclick: () => create() }, h("span", { class: "plus" }, "+"), "New workspace"));
  }
  async function open(w) {
    if (w.id !== current) {
      await api("/api/workspaces/open", { id: w.id });
      toast(`Opened ${w.name}`);
    }
    showTab("control");
  }

  // The dialog: a new workspace, or changing one.
  const dlg = $("#dialog"), form = $("#dialog-form");
  let pending = null, editing = null;
  function dialog(w) {
    editing = w || null;
    pending = null;
    $("#dialog-title").textContent = w ? "Workspace" : "New workspace";
    $("#dlg-name").value = w ? w.name : "";
    $("#dlg-ok").textContent = w ? "Save" : "Create";
    $("#dlg-template-row").hidden = !!w;
    $("#dlg-delete").hidden = !w;
    $("#dlg-delete").disabled = !!w && w.id === current;
    $("#dlg-delete").title = w && w.id === current ? "Open another workspace first" : "";
    $("#dlg-file").value = "";
    wsPicture($("#dlg-pic"), w || { name: "+" }, picBust);
    if (!w) $("#dlg-pic").textContent = "🖼";
    dlg.hidden = false;
    setTimeout(() => $("#dlg-name").focus(), 0);
  }
  const create = () => dialog(null);
  const edit = w => dialog(w);
  $("#dlg-file").addEventListener("change", e => {
    pending = e.target.files[0] || null;
    if (pending) { const p = $("#dlg-pic"); p.style.backgroundImage = `url("${URL.createObjectURL(pending)}")`; p.textContent = ""; }
  });
  $("#dlg-name").addEventListener("input", () => {
    const p = $("#dlg-pic");
    if (!pending && !(editing && editing.picture)) p.textContent = initials($("#dlg-name").value) || "🖼";
  });
  const close = () => { dlg.hidden = true; };
  $("#dlg-cancel").addEventListener("click", close);
  dlg.addEventListener("click", e => { if (e.target === dlg) close(); });
  addEventListener("keydown", e => { if (e.key === "Escape" && !dlg.hidden) close(); });
  form.addEventListener("submit", async e => {
    e.preventDefault();
    const name = $("#dlg-name").value.trim();
    if (!name) return;
    const btn = $("#dlg-ok");
    btn.disabled = true;
    try {
      let id;
      if (editing) {
        id = editing.id;
        if (name !== editing.name) await api("/api/workspaces/rename", { id, name });
      } else {
        const template = (form.querySelector("input[name=dlg-template]:checked") || {}).value || "scc";
        // Made (and opened) first, so the picture has somewhere to go.
        id = (await api("/api/workspaces/create", { name, template, open: false })).id;
      }
      if (pending) { await postFile(`/api/workspaces/picture?id=${encodeURIComponent(id)}`, pending); picBust = Date.now(); }
      close();
      if (!editing) { await api("/api/workspaces/open", { id }); toast(`Created ${name}`); showTab("control"); }
      await load();
    } finally { btn.disabled = false; }
  });
  $("#dlg-delete").addEventListener("click", async () => {
    if (!editing || !confirm(`Delete the workspace "${editing.name}"? Its graphics and files are moved to workspaces/.deleted.`)) return;
    await api("/api/workspaces/delete", { id: editing.id });
    close();
    load();
  });

  let lastSig = "";
  App.on(s => {
    const sig = s.workspace.id + "|" + s.workspace.name + "|" + s.workspace.picture + "|" + s.project.compositions.length;
    if (sig !== lastSig && App.tab === "home") { lastSig = sig; load(); }
  });
  pages.home = { shown() { lastSig = ""; load(); } };
})();

// --- GLOBAL ---------------------------------------------------------------------------
(function globalPage() {
  let g = null;                  // as edited here
  let queued = {};               // changes not sent yet
  const flush = debounce(() => { const send = queued; queued = {}; api("/api/global", { global: send }); }, 250);
  function change(changes) {
    for (const [k, v] of Object.entries(changes)) {
      if ((k === "left" || k === "right") && typeof v === "object") queued[k] = Object.assign(queued[k] || {}, v);
      else queued[k] = v;
    }
    flush();
  }

  // A team: logo, name, short name, colour.
  function teamCard(side) {
    const card = document.querySelector(`.team-card[data-side=${side}]`);
    const fileIn = h("input", { type: "file", accept: "image/*", hidden: true,
      onchange: async e => { const f = e.target.files[0]; if (f) await uploadLogo(side, f); e.target.value = ""; } });
    const drop = h("div", { class: "logo-drop", title: "Click or drop a logo", onclick: () => fileIn.click(),
      ondragover: e => { e.preventDefault(); drop.classList.add("over"); },
      ondragleave: () => drop.classList.remove("over"),
      ondrop: e => { e.preventDefault(); drop.classList.remove("over"); const f = e.dataTransfer.files[0]; if (f) uploadLogo(side, f); } },
      "Click or drop the logo");
    const input = (key, attrs) => h("input", Object.assign({ "data-k": key,
      oninput: e => { g[side][key] = e.target.value; change({ [side]: { [key]: e.target.value } }); renderScore(); } }, attrs));
    card.replaceChildren(
      h("div", { class: "panel-head" }, h("h3", {}, side === "left" ? "Left team" : "Right team"),
        h("span", { class: "side-tag", "data-k": "tag" }, side === "left" ? "LEFT" : "RIGHT")),
      h("div", { class: "pad" },
        drop, fileIn,
        h("div", { class: "row-gap", style: { justifyContent: "center" } },
          h("button", { class: "ghost small", "data-k": "logo-clear", onclick: () => { g[side].logo = ""; change({ [side]: { logo: "" } }); render(true); } }, "Remove logo")),
        h("label", {}, "Name", input("name", { placeholder: side === "left" ? "e.g. St. Clair Saints" : "e.g. George Mason" })),
        h("div", { class: "colour-row" },
          h("label", { style: { flex: 1 } }, "Short name", input("short", { placeholder: "e.g. SCC", maxlength: 8 })),
          h("label", {}, "Colour", input("color", { type: "color" })))));
    return card;
  }
  async function uploadLogo(side, file) {
    const r = await postFile(`/api/global/logo?side=${side}`, file);
    g = r.global;
    render(true);
    toast("Logo saved");
  }
  const cards = { left: teamCard("left"), right: teamCard("right") };

  // The series.
  function bump(side, by) {
    const n = Math.max(0, (Number(g[side].score) || 0) + by);
    g[side].score = n;
    change({ [side]: { score: n } });
    renderScore();
  }
  function renderScore() {
    const box = $("#g-score");
    const need = Math.floor(g.best_of / 2) + 1;
    const ls = Number(g.left.score) || 0, rs = Number(g.right.score) || 0;
    const game = g.game || String(ls + rs + 1);
    const over = ls >= need || rs >= need;
    const side = s => h("div", { class: "side" },
      h("div", { class: "short", style: { color: g[s].color } }, g[s].short || (s === "left" ? "LEFT" : "RIGHT")),
      h("div", { class: "num" }, String(g[s].score)),
      h("div", { class: "pm" }, h("button", { onclick: () => bump(s, -1) }, "−"), h("button", { onclick: () => bump(s, 1) }, "+")));
    box.replaceChildren(side("left"),
      h("div", { class: "mid" }, h("b", {}, over ? "Final" : `Game ${game}`), `Best of ${g.best_of}`, h("br"), `First to ${need}`),
      side("right"));
  }
  const bind = (sel, key, num) => {
    const el = $(sel);
    el.addEventListener(el.tagName === "SELECT" ? "change" : "input", () => {
      const v = num ? Number(el.value) : el.value;
      g[key] = v; change({ [key]: v }); renderScore(); renderTokens();
    });
  };
  bind("#g-bestof", "best_of", true);
  bind("#g-game", "game");
  bind("#g-event", "event");
  bind("#g-stage", "stage");
  $("#g-reset").addEventListener("click", () => {
    g.left.score = g.right.score = 0;
    change({ left: { score: 0 }, right: { score: 0 }, game: "" });
    g.game = "";
    render(true);
  });
  $("#g-swap").addEventListener("click", () => {
    const l = g.left; g.left = g.right; g.right = l;
    api("/api/global", { global: { left: g.left, right: g.right } });
    render(true);
  });

  // More fields.
  function renderCustom() {
    $("#g-custom").replaceChildren(...(g.custom.length ? g.custom.map((row, i) => h("div", { class: "custom-row" },
      h("input", { value: row[0], placeholder: "Label", oninput: e => { g.custom[i][0] = e.target.value; saveCustom(); } }),
      h("input", { value: row[1], placeholder: "Value", oninput: e => { g.custom[i][1] = e.target.value; saveCustom(); } }),
      h("button", { class: "ghost small", title: "Remove", onclick: () => { g.custom.splice(i, 1); saveCustom(); renderCustom(); } }, "✕")))
      : [h("div", { class: "muted small" }, "Anything else every graphic should know: a caster's name, the hashtag, the next match…")]));
  }
  const saveCustom = debounce(() => { api("/api/global", { global: { custom: g.custom.filter(r => r[0].trim()) } }); renderTokens(); }, 300);
  $("#g-custom-add").addEventListener("click", () => { g.custom.push(["", ""]); renderCustom(); const ins = $("#g-custom").querySelectorAll("input"); ins[ins.length - 2].focus(); });

  // A drop target: click to pick files, or drop them.
  function dropZone(el, accept, multiple, onFiles) {
    const input = h("input", { type: "file", accept, multiple, hidden: true,
      onchange: e => { const fs = [...e.target.files]; e.target.value = ""; if (fs.length) onFiles(fs); } });
    el.after(input);
    el.addEventListener("click", () => input.click());
    el.addEventListener("dragover", e => { e.preventDefault(); e.stopPropagation(); el.classList.add("over"); });
    el.addEventListener("dragleave", () => el.classList.remove("over"));
    el.addEventListener("drop", e => {
      e.preventDefault(); e.stopPropagation(); el.classList.remove("over");
      const fs = [...e.dataTransfer.files]; if (fs.length) onFiles(fs);
    });
  }
  const pic = p => !p ? "" : /^https?:/.test(p) ? p : "/" + encodeURI(p);

  // The tournament's logo.
  dropZone($("#g-tourney"), "image/*", false, async ([f]) => {
    g = (await postFile("/api/global/logo?side=tournament", f)).global; render(true); toast("Tournament logo saved");
  });
  $("#g-tourney-clear").addEventListener("click", () => { g.tournament_logo = ""; api("/api/global", { global: { tournament_logo: "" } }); render(true); });
  function renderBrand() {
    const d = $("#g-tourney"), logo = pic(g.tournament_logo);
    d.classList.toggle("has", !!logo);
    d.style.backgroundImage = logo ? `url("${logo}")` : "";
    $("#g-tourney-clear").hidden = !logo;
  }

  // The sponsors, in order, each for its own seconds.
  dropZone($("#g-sponsor-add"), "image/*", true, async fs => {
    for (const f of fs) g = (await postFile("/api/global/logo?side=sponsor", f)).global;
    render(true); toast(fs.length > 1 ? `${fs.length} sponsors added` : "Sponsor added");
  });
  const saveSponsors = debounce(() => api("/api/global", { global: { sponsors: g.sponsors } }), 400);
  function moveSponsor(i, by) {
    const j = i + by;
    if (j < 0 || j >= g.sponsors.length) return;
    [g.sponsors[i], g.sponsors[j]] = [g.sponsors[j], g.sponsors[i]];
    api("/api/global", { global: { sponsors: g.sponsors } });
    renderSponsors(true);
  }
  function renderSponsors(force) {
    const list = $("#g-sponsor-list");
    const sig = JSON.stringify(g.sponsors.map(x => x.logo));
    if (force || list.dataset.sig !== sig) {
      list.dataset.sig = sig;
      list.replaceChildren(...(g.sponsors.length ? g.sponsors.map((sp, i) => h("div", { class: "sponsor", "data-i": i },
        h("div", { class: "thumb", style: { backgroundImage: `url("${pic(sp.logo)}")` }, title: sp.logo }),
        h("div", {},
          h("div", { class: "secs" }, "On for", h("input", { type: "number", min: 1, max: 600, value: sp.secs,
            onchange: e => { sp.secs = Math.max(1, +e.target.value || 10); saveSponsors(); } }), "seconds"),
          h("div", { class: "now" })),
        h("div", { class: "acts" },
          h("button", { class: "ghost small", title: "Earlier", onclick: () => moveSponsor(i, -1) }, "↑"),
          h("button", { class: "ghost small", title: "Later", onclick: () => moveSponsor(i, 1) }, "↓"),
          h("button", { class: "ghost small", title: "Remove", onclick: () => {
            g.sponsors.splice(i, 1); api("/api/global", { global: { sponsors: g.sponsors } }); renderSponsors(true);
          } }, "✕")),
        h("div", { class: "bar" })))
        : [h("div", { class: "muted small" }, "No sponsors yet: the sponsor spots show the design's own picture.")]));
    }
    tickSponsors();
  }
  // Which one is on now, and how long it has left.
  function tickSponsors() {
    const now = GFX.sponsorNow();
    $("#g-sponsor-list").querySelectorAll(".sponsor").forEach((row, i) => {
      const on = i === now.index;
      row.classList.toggle("on", on);
      row.querySelector(".now").textContent = on ? `On air now · ${Math.ceil(now.left)} s left` : "";
      row.querySelector(".bar").style.transform = `scaleX(${on && now.secs ? now.left / now.secs : 0})`;
    });
  }
  setInterval(() => { if (App.tab === "global") tickSponsors(); }, 250);

  // The background loop.
  const loopSrc = () => g.bgloop.src || "loops/scc-bg-loop.webm";
  function renderLoop() {
    const L = g.bgloop, v = $("#g-loop-video");
    $("#g-loop-on").checked = L.on;
    $("#g-loop-preview").classList.toggle("off", !L.on);
    if (document.activeElement !== $("#g-loop-color")) $("#g-loop-color").value = /^#[0-9a-f]{6}$/i.test(L.color) ? L.color : "#2fa85a";
    if (document.activeElement !== $("#g-loop-bright")) $("#g-loop-bright").value = L.brightness;
    if (document.activeElement !== $("#g-loop-speed")) $("#g-loop-speed").value = L.speed;
    $("#g-loop-bright-v").textContent = Number(L.brightness).toFixed(1);
    $("#g-loop-speed-v").textContent = Number(L.speed).toFixed(1) + "×";
    const src = pic(loopSrc());
    if (v.dataset.src !== src) { v.dataset.src = src; v.src = src; v.play().catch(() => {}); }
    v.playbackRate = L.speed;
    v.style.filter = `grayscale(1) brightness(${L.brightness})`;
    $("#g-loop-tint").style.background = L.color;
    $("#g-loop-default").hidden = !g.bgloop.src;
  }
  const loopChange = changes => { Object.assign(g.bgloop, changes); change({ bgloop: changes }); renderLoop(); };
  $("#g-loop-on").addEventListener("change", e => loopChange({ on: e.target.checked }));
  $("#g-loop-color").addEventListener("input", e => loopChange({ color: e.target.value }));
  $("#g-loop-bright").addEventListener("input", e => loopChange({ brightness: +e.target.value }));
  $("#g-loop-speed").addEventListener("input", e => loopChange({ speed: +e.target.value }));
  $("#g-loop-default").addEventListener("click", () => loopChange({ src: "" }));
  $("#g-loop-file").addEventListener("click", () => $("#g-loop-input").click());
  $("#g-loop-input").addEventListener("change", async e => {
    const f = e.target.files[0]; e.target.value = "";
    if (!f) return;
    toast(`Adding ${f.name}…`);
    g = (await postFile("/api/global/logo?side=bgloop", f)).global; render(true); toast("Background loop saved");
  });

  // The game's stats (kept after the game).
  function renderStats(s) {
    const st = s.data.stats || {}, rows = s.data.tables.Stats || [];
    const val = k => (rows.find(r => r[0] === k) || [])[1] || "";
    $("#g-stats").replaceChildren(...(!st.kept ? ["No game stats yet."] :
      [h("b", {}, st.live ? "Stats live" : "Final stats kept"), ` from ${st.from || "a HUD"} · ${val("Game")}` +
        (st.live ? "" : ` · ${new Date(st.at * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`)]));
    $("#g-stats-clear").hidden = !st.kept;
  }
  $("#g-stats-clear").addEventListener("click", () => { if (confirm("Forget the last game's stats? The stats graphics go blank until a HUD sends new ones.")) api("/api/stats/clear", {}); });

  // The tokens, and the HUDs' data.
  function renderTokens() {
    const rows = (App.state.data.tables.Global || []).slice(1);
    const list = $("#g-token-list");
    const sig = JSON.stringify(rows.map(r => r[0]));
    if (list.dataset.sig === sig) return;
    list.dataset.sig = sig;
    list.replaceChildren(...rows.map(r => {
      const t = `{{Global!${r[0]}}}`;
      return h("code", { title: "Copy", onclick: () => copy(t) }, t);
    }));
  }
  function renderFeeds(s) {
    const feeds = s.data.feeds || {};
    const box = $("#g-feeds");
    const names = Object.keys(feeds);
    if (!names.length) {
      box.replaceChildren(h("div", { class: "muted small" },
        "No game HUD is connected. In the League, VALORANT, CoD or Rocket League HUD, open GFX Engine, pick this engine and connect: its stats come in here as a data table, and its series score updates the one above."));
      return;
    }
    box.replaceChildren(...names.map(n => {
      const f = feeds[n], rows = (s.data.tables[n] || []).slice(1);
      const stale = f.age > 10;
      return h("div", { class: "feed" + (stale ? " stale" : "") },
        h("div", { class: "feed-head" }, h("span", { class: "dot" }), h("b", {}, n),
          h("span", { class: "muted small" }, `${f.game ? f.game + " · " : ""}${f.from} · ${stale ? "last heard " + Math.round(f.age) + " s ago" : "live"}`)),
        h("table", {}, h("tbody", {}, ...rows.slice(0, 60).map(r => h("tr", {},
          h("td", { title: `Copy {{${n}!${r[0]}}}`, onclick: () => copy(`{{${n}!${r[0]}}}`) }, r[0]), h("td", { title: r[1] }, r[1]))))),
        rows.length > 60 ? h("div", { class: "muted small" }, `…and ${rows.length - 60} more (Data tab)`) : null);
    }));
  }

  function render(force) {
    const s = App.state;
    if (!g || force) g = JSON.parse(JSON.stringify(g || s.global));
    for (const side of ["left", "right"]) {
      const card = cards[side], t = g[side];
      for (const input of card.querySelectorAll("input[data-k]")) {
        if (document.activeElement !== input && input.value !== String(t[input.dataset.k] ?? "")) input.value = t[input.dataset.k] || (input.type === "color" ? "#000000" : "");
      }
      card.querySelector("[data-k=tag]").style.background = t.color;
      const drop = card.querySelector(".logo-drop");
      const logo = t.logo ? (/^https?:/.test(t.logo) ? t.logo : "/" + encodeURI(t.logo)) : "";
      drop.classList.toggle("has", !!logo);
      drop.style.backgroundImage = logo ? `url("${logo}")` : "";
      card.querySelector("[data-k=logo-clear]").hidden = !logo;
    }
    for (const [sel, key] of [["#g-bestof", "best_of"], ["#g-game", "game"], ["#g-event", "event"], ["#g-stage", "stage"]]) {
      const el = $(sel);
      if (document.activeElement !== el) el.value = String(g[key] ?? "");
    }
    renderScore();
    if (force || !document.activeElement || !$("#g-custom").contains(document.activeElement)) renderCustom();
    renderTokens();
    renderFeeds(s);
    renderBrand();
    renderSponsors(force);
    renderLoop();
    renderStats(s);
  }

  // Changes from elsewhere (a HUD's score, another control panel) come in when not being edited here.
  let lastGlobal = "";
  App.on(s => {
    const sig = JSON.stringify(s.global);
    if (sig !== lastGlobal) {
      lastGlobal = sig;
      if (!Object.keys(queued).length) g = JSON.parse(JSON.stringify(s.global));
      if (App.tab === "global") render();
    } else if (App.tab === "global") { renderFeeds(s); renderStats(s); }
  });
  pages.global = { shown() { if (App.state) { g = JSON.parse(JSON.stringify(App.state.global)); render(true); } } };
})();

// Outputs > Workspace: the SCC graphics this workspace doesn't have yet.
$("#ws-pack").addEventListener("click", async () => {
  const r = await api("/api/pack/import", {});
  toast(r.added.length ? `Added ${r.added.length}: ${r.added.join(", ")}` : "It has every SCC graphic already");
});
