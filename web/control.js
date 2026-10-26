// The control panel: shared bits (the engine's state, talking to it, tabs)
// and the Control page (Preview / Program, the take bar, the rundown and the
// selected graphic's fields). Composer is in composer.js, the other pages in pages.js.
"use strict";

// --- helpers ---------------------------------------------------------------
function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k in e && typeof v !== "string") e[k] = v;
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) e.append(kid instanceof Node ? kid : String(kid));
  return e;
}
const $ = s => document.querySelector(s);
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
let toastTimer;
function toast(msg, error) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), error ? 6000 : 2200);
}
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.error) { toast(data.error || `${path} failed (${r.status})`, true); throw new Error(data.error || r.status); }
  return data;
}
function debounce(fn, ms) {
  let t;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}
function copy(text, what) {
  const done = () => toast(`Copied ${what || text}`);
  if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, () => fallback());
  else fallback();
  function fallback() {
    const t = h("textarea", { style: { position: "fixed", opacity: 0 } }, text);
    document.body.appendChild(t); t.select();
    try { document.execCommand("copy"); done(); } catch (e) { toast("Couldn't copy", true); }
    t.remove();
  }
}
const fmtBytes = n => n > 1e9 ? (n / 1e9).toFixed(1) + " GB" : n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1e3)) + " KB";

// A small, still picture of a graphic (cached until it or its values change).
const thumbCache = new Map();
function thumb(comp, values, width) {
  const key = comp.id + ":" + width;
  const sig = JSON.stringify([comp.layers, values]);
  let entry = thumbCache.get(key);
  if (!entry || entry.sig !== sig) {
    const box = h("div", { class: "thumb", style: { width: width + "px", height: Math.round(width * 9 / 16) + "px" } });
    const stage = h("div", { class: "gfx-stage", style: { transform: `scale(${width / GFX.W})` } });
    stage.appendChild(GFX.buildComp(comp, values || {}, { still: true, muted: true }));
    box.appendChild(stage);
    if (entry) GFX.destroy(entry.box);
    entry = { sig, box };
    thumbCache.set(key, entry);
  }
  return entry.box;
}

// --- the engine's state ----------------------------------------------------
const App = {
  state: null,
  assets: [],
  assetsRev: null,
  listeners: [],
  tab: null,
  on(fn) { this.listeners.push(fn); },
  comps() { return this.state ? this.state.project.compositions : []; },
  comp(id) { return this.comps().find(c => c.id === id); },
  fields(comp) {
    // The graphic's fields, once each, in layer order (top first).
    const seen = new Map();
    for (const l of [...(comp.layers || [])].reverse()) if (l.field && !seen.has(l.field)) seen.set(l.field, l);
    return [...seen.values()];
  },
  async loadAssets() {
    const r = await fetch("/api/assets").then(r => r.json());
    this.assets = r.assets;
    this.assetsRev = r.rev;
    this.emit("assets");
  },
  emit(what) { for (const fn of this.listeners) { try { fn(this.state, what); } catch (e) { console.error(e); } } },
  apply(msg) {
    // (each message has only what changed: the rest is as it was)
    const state = this.state = Object.assign({}, this.state, msg);
    if (msg.fonts) GFX.loadFonts(state.fonts);
    if (msg.data) {
      GFX.setClock(state.data.now);
      GFX.setData(state.data.tables);
    }
    if (state.assets_rev !== this.assetsRev) this.loadAssets();
    this.emit("state");
  },
};
window.App = App;

function connect() {
  const es = new EventSource("/api/stream");
  es.onmessage = e => App.apply(JSON.parse(e.data));
}
fetch("/api/state").then(r => r.json()).then(s => App.apply(s)).finally(connect);

// --- tabs and header -------------------------------------------------------
const pages = {};
function showTab(name) {
  if (!pages[name] && name !== "control") name = "control";
  App.tab = name;
  for (const b of document.querySelectorAll("#tabs button[data-tab]")) b.classList.toggle("on", b.dataset.tab === name);
  // (Assets, Data, Transitions and Outputs are under Extras: it shows which one is open)
  const extra = document.querySelector(`#extras-menu button[data-tab="${name}"]`);
  $("#extras-btn").classList.toggle("on", !!extra);
  $("#extras-btn").firstChild.textContent = extra ? extra.textContent + " " : "Extras ";
  extrasMenu(false);
  for (const p of document.querySelectorAll(".page")) p.hidden = p.id !== "page-" + name;
  try { localStorage.setItem("gfx-tab", name); } catch (e) { /* private window */ }
  if (pages[name] && pages[name].shown) pages[name].shown();
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
}
document.querySelectorAll("#tabs button[data-tab]").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
function extrasMenu(open) {
  $("#extras-menu").hidden = !open;
  $("#extras-btn").setAttribute("aria-expanded", String(open));
}
$("#extras-btn").addEventListener("click", e => { e.stopPropagation(); extrasMenu($("#extras-menu").hidden); });
document.addEventListener("click", e => { if (!e.target.closest("#extras")) extrasMenu(false); });
document.addEventListener("keydown", e => { if (e.key === "Escape") extrasMenu(false); });
addEventListener("load", () => {
  let start = location.hash.slice(1);
  if (!start) { try { start = localStorage.getItem("gfx-tab") || "control"; } catch (e) { start = "control"; } }
  showTab(start);
});

const projectName = $("#project-name");
projectName.addEventListener("change", () => api("/api/project", { name: projectName.value }));
App.on(s => {
  if (document.activeElement !== projectName) projectName.value = s.project.name;
  document.title = `${s.project.name} · GFX Engine`;
  const net = $("#net");
  const addr = s.app.addresses[0];
  net.className = "pill" + (s.app.network ? " on" : "");
  net.textContent = s.app.network ? `${addr || "localhost"}:${s.app.port}` : "This PC only";
  $("#version").textContent = s.app.version === "dev" ? "dev" : s.app.version;
  const up = s.update, btn = $("#update");
  btn.hidden = !(up.available && up.can_install) && up.status !== "downloading" && up.status !== "installing";
  btn.disabled = up.status === "downloading" || up.status === "installing";
  btn.textContent = up.status === "downloading" ? `Downloading ${up.progress}%` : up.status === "installing" ? "Installing…" : `Update to ${up.latest}`;
});
$("#update").addEventListener("click", () => api("/api/update/install"));

// --- CONTROL ----------------------------------------------------------------
(function control() {
  const pvw = $("#mon-pvw"), pgm = $("#mon-pgm");
  pvw.src = "/output?bus=preview&monitor=1&bg=checker";
  pgm.src = "/output?bus=program&monitor=1&bg=checker";
  $("#pgm-open").href = "/output?bg=checker";
  let selected = null;
  try { selected = localStorage.getItem("gfx-sel"); } catch (e) { /* */ }
  let transition = null;
  try { transition = localStorage.getItem("gfx-tr"); } catch (e) { /* */ }

  function chosen(s) {
    const enabled = s.project.transitions.filter(t => t.enabled !== false);
    const t = enabled.find(t => t.id === transition) || enabled.find(t => t.id === s.project.default_transition) || enabled[0];
    return t ? t.id : "cut";
  }

  // The take bar.
  function renderChips(s) {
    const box = $("#tr-chips");
    const enabled = s.project.transitions.filter(t => t.enabled !== false);
    const cur = chosen(s);
    const sig = JSON.stringify([enabled.map(t => [t.id, t.name]), cur]);
    if (box.dataset.sig === sig) return;
    box.dataset.sig = sig;
    box.replaceChildren(...enabled.map((t, i) => h("button", {
      class: t.id === cur ? "on" : "", title: `${t.name} (${i + 1})`,
      onclick: () => { transition = t.id; try { localStorage.setItem("gfx-tr", t.id); } catch (e) { /* */ } renderChips(App.state); },
    }, t.name, h("span", { class: "k" }, i < 9 ? String(i + 1) : ""))));
  }
  async function take(tid) {
    const btn = $("#take");
    btn.classList.add("busy");
    try { await api("/api/take", { transition: tid || chosen(App.state) }); } finally { setTimeout(() => btn.classList.remove("busy"), 400); }
  }
  $("#take").addEventListener("click", () => take());
  $("#cut").addEventListener("click", () => take("cut"));
  $("#pgm-clear").addEventListener("click", () => api("/api/clear", { bus: "program", transition: chosen(App.state) }));
  $("#pvw-clear").addEventListener("click", () => api("/api/clear", { bus: "preview" }));
  addEventListener("keydown", e => {
    if (App.tab !== "control" || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.code === "Space") { e.preventDefault(); take(); }
    else if (e.key === "Enter") { e.preventDefault(); take("cut"); }
    else if (/^[1-9]$/.test(e.key)) {
      const t = App.state.project.transitions.filter(t => t.enabled !== false)[+e.key - 1];
      if (t) { transition = t.id; renderChips(App.state); }
    }
  });

  // The rundown.
  const KIND_TITLES = [["board", "Full-page boards"], ["lower third", "Lower thirds"], ["overlay", "Overlays"]];
  const filter = $("#rundown-filter");
  filter.addEventListener("input", () => renderRundown(App.state, true));
  let dragId = null;
  function renderRundown(s, force) {
    const list = $("#rundown");
    const q = filter.value.trim().toLowerCase();
    const comps = s.project.compositions.filter(c => !q || c.name.toLowerCase().includes(q));
    const pv = s.live.preview, pg = s.live.program;
    if (!selected || !App.comp(selected)) selected = comps[0] && comps[0].id;
    const sig = JSON.stringify([comps.map(c => [c.id, c.name, c.kind, c.layers]), pv.on, pg.on, pv.values, selected]);
    if (!force && list.dataset.sig === sig) return;
    list.dataset.sig = sig;
    if (!comps.length) {
      list.replaceChildren(h("div", { class: "empty" }, q ? "Nothing matches." : "No graphics yet. Make one in Composer, or add a Photoshop file in Assets."));
      return;
    }
    // Full-page boards, lower thirds, overlays: one board and one lower third on air at a time.
    const rows = [];
    for (const [kind, title] of KIND_TITLES) {
      const these = comps.filter(c => (c.kind || "overlay") === kind && !c.hud);
      if (!these.length) continue;
      rows.push(h("div", { class: "rd-group" }, title), ...these.map(row));
    }
    // A connected game HUD's own pages (VALORANT's agent select...), live from the HUD.
    const huds = comps.filter(c => c.hud);
    if (huds.length) rows.push(h("div", { class: "rd-group" }, "Game HUD"), ...huds.map(row));
    list.replaceChildren(...rows);
  }
  function row(c) {
    const pv = App.state.live.preview, pg = App.state.live.program;
    const onPvw = pv.on.includes(c.id), onPgm = pg.on.includes(c.id);
    const nFields = App.fields(c).length;
    return h("div", {
      class: `rd${onPvw ? " on-pvw" : ""}${onPgm ? " on-pgm" : ""}${c.id === selected ? " sel" : ""}`, draggable: true,
      onclick: () => select(c.id),
      ondblclick: () => api("/api/cue", { id: c.id, on: !onPvw }),
      ondragstart: e => { dragId = c.id; e.dataTransfer.effectAllowed = "move"; },
      ondragover: e => { e.preventDefault(); },
      ondrop: e => {
        e.preventDefault();
        if (!dragId || dragId === c.id) return;
        const ids = App.comps().map(x => x.id).filter(x => x !== dragId);
        ids.splice(ids.indexOf(c.id), 0, dragId);
        api("/api/comp/order", { ids });
      },
    },
      h("div", { class: "bar" }),
      thumb(c, pv.values[c.id], 112),
      h("div", { style: { minWidth: 0 } }, h("div", { class: "name" }, c.name),
        h("div", { class: "sub" }, `${nFields} field${nFields === 1 ? "" : "s"}`, onPgm ? " · ON AIR" : onPvw ? " · on preview" : "")),
      h("div", { class: "btns" },
        h("button", { class: "pvw-btn" + (onPvw ? " on" : ""), title: "On / off Preview (double-click the row)",
          onclick: e => { e.stopPropagation(); api("/api/cue", { id: c.id, on: !onPvw }); } }, "PVW"),
        h("button", { class: "in-btn" + (onPgm ? " on" : ""), title: onPgm ? "Take it off air (its Out animation)" : "Straight on air (its In animation): a board or lower third replaces the one on air, the rest stays",
          onclick: e => { e.stopPropagation(); api("/api/program", { id: c.id, on: !onPgm }); } }, onPgm ? "OUT" : "IN")));
  }
  function select(id) {
    selected = id;
    try { localStorage.setItem("gfx-sel", id); } catch (e) { /* */ }
    renderRundown(App.state, true);
    renderFields(App.state, true);
  }
  window.selectGraphic = select;

  // The selected graphic's fields (they change Preview as you type).
  const sendValues = {};
  function push(id, field, value) {
    (sendValues[id] = sendValues[id] || {})[field] = value;
    pushSoon();
  }
  const pushSoon = debounce(() => {
    for (const [id, values] of Object.entries(sendValues)) { api("/api/values", { id, values, bus: "preview" }); delete sendValues[id]; }
  }, 150);
  $("#fields-send").addEventListener("click", () => { if (selected) api("/api/send", { id: selected }); });

  const GLOBAL_PICTURES = [["{{Global!Left logo}}", "Left team's logo"], ["{{Global!Right logo}}", "Right team's logo"],
    ["{{Global!Tournament logo}}", "Tournament logo"], ["{{Sponsors}}", "Sponsors (in turn)"]];
  function assetOptions(kind, current) {
    const kinds = kind === "image" ? ["image"] : kind === "video" ? ["video", "image"] : kind === "lottie" ? ["lottie"] : [kind];
    const opts = App.assets.filter(a => kinds.includes(a.kind));
    const out = [h("option", { value: "" }, "(as designed)")];
    if (kind === "image") {
      out.push(h("optgroup", { label: "Global configuration" },
        ...GLOBAL_PICTURES.map(([t, label]) => h("option", { value: t, selected: t === current }, label))));
    }
    out.push(...opts.map(a => h("option", { value: a.path, selected: a.path === current }, a.path.replace(/^(assets|library)\//, ""))));
    return out;
  }

  function renderFields(s, force) {
    const box = $("#fields");
    const comp = App.comp(selected);
    $("#fields-title").textContent = comp ? comp.name : "Fields";
    if (!comp) { box.replaceChildren(h("div", { class: "empty" }, "Pick a graphic.")); return; }
    const fields = App.fields(comp);
    const pvVals = s.live.preview.values[comp.id] || {};
    const pgVals = s.live.program.values[comp.id] || {};
    const onAir = s.live.program.on.includes(comp.id);
    const differs = onAir && fields.some(l => (pvVals[l.field] ?? "") !== (pgVals[l.field] ?? ""));
    $("#fields-send").classList.toggle("differs", differs);
    $("#fields-send").disabled = !fields.length;
    const bracket = comp.layers.some(l => l.type === "bracket");
    const sched = comp.layers.some(l => /\{\{\s*Schedule!/i.test(l.show || ""));
    const clock = comp.layers.some(l => /\{\{\s*clock\s*\}\}/i.test(l.text || ""));
    const timer = comp.layers.some(l => /\{\{\s*timer\s*\}\}/i.test(l.text || ""));
    const roster = comp.layers.some(l => /\{\{\s*Roster!/i.test((l.text || "") + (l.src || "")));
    const mvp = comp.layers.some(l => /\{\{\s*Stats!MVP/i.test((l.text || "") + (l.src || "")));
    const caster = comp.layers.some(l => /Global!Caster/i.test(l.move || ""));
    const pics = comp.layers.some(l => /\{\{\s*Stats!.*(headshot|champion)\}\}/i.test(l.src || ""));
    // (Player stats has its own setting: its picture is the MVP's)
    const picsPage = comp.layers.some(l => /\{\{\s*Stats!MVP (headshot|champion)\}\}/i.test(l.src || "")) ? "player" : "team";
    const extras = () => [comp.hud ? hudField(s, comp) : null, caster ? casterField(s) : null, roster ? rosterField(s) : null, mvp ? mvpField(s) : null, pics ? picturesField(s, picsPage) : null, clock ? clockField(s) : null, timer ? timerField(s) : null, bracket ? sizeField(s) : null, sched ? countField(s) : null].filter(Boolean);
    const sig = JSON.stringify([comp.id, fields.map(f => [f.field, f.type]), App.assetsRev, bracket, sched, clock, timer, roster, mvp, caster, pics, picsPage,
      Object.keys(s.data.feeds || {}), (s.data.tables.Global || []).map(r => r[0]),
      comp.hud ? JSON.stringify(s.data.feeds[comp.hud.split("/")[0]] && s.data.feeds[comp.hud.split("/")[0]].unreachable) : ""]);
    if (!force && box.dataset.sig === sig) {
      markSize(box, s);
      // Same fields: only bring in values changed elsewhere (not the one being typed in).
      for (const l of fields) {
        const input = box.querySelector(`[data-field="${CSS.escape(l.field)}"]`);
        const v = pvVals[l.field] ?? "";
        if (input && document.activeElement !== input && input.value !== String(v) && !(l.field in (sendValues[comp.id] || {}))) {
          if (input.type === "color") input.value = v || l.fill || "#000000"; else input.value = v;
        }
        const res = box.querySelector(`[data-resolved="${CSS.escape(l.field)}"]`);
        if (res) updateResolved(res, l, input ? input.value : "");
        const liveTag = box.querySelector(`[data-live="${CSS.escape(l.field)}"]`);
        if (liveTag) liveTag.textContent = onAir && (pvVals[l.field] ?? "") !== (pgVals[l.field] ?? "") ? "≠ ON AIR" : "";
      }
      return;
    }
    box.dataset.sig = sig;
    if (!fields.length) {
      box.replaceChildren(...(bracket || sched || clock || timer || roster || mvp || caster || pics || comp.hud ? extras() : [h("div", { class: "empty" }, "This graphic has no fields. In Composer, pick a layer and give it a field name to change it from here.")]));
      return;
    }
    box.replaceChildren(...fields.map(l => {
      const v = pvVals[l.field];
      let input;
      if (l.type === "text") {
        input = h("textarea", { "data-field": l.field, placeholder: l.text, rows: Math.min(4, Math.max(1, String(v ?? "").split("\n").length)),
          oninput: e => { push(comp.id, l.field, e.target.value); updateResolved(res, l, e.target.value); } });
        input.value = v ?? "";
      } else if (l.type === "rect") {
        input = h("input", { type: "color", "data-field": l.field, value: v || l.fill || "#000000",
          oninput: e => push(comp.id, l.field, e.target.value) });
      } else {
        input = h("select", { "data-field": l.field, onchange: e => push(comp.id, l.field, e.target.value || null) }, assetOptions(l.type, v));
      }
      const res = h("div", { class: "resolved", "data-resolved": l.field });
      updateResolved(res, l, v ?? "");
      // Text or a colour can follow the global configuration (or a game HUD's data).
      const link = l.type === "image" ? null : h("select", { class: "small link", title: "Use the global configuration (or a connected game HUD)",
        onchange: e => {
          if (!e.target.value) return;
          input.value = e.target.value; push(comp.id, l.field, e.target.value); updateResolved(res, l, e.target.value);
          e.target.value = "";
        } }, linkOptions(s, l.type));
      return h("div", { class: "field" },
        h("label", {}, l.field, h("span", { class: "kind" }, l.type), h("span", { class: "live", "data-live": l.field },
          onAir && (pvVals[l.field] ?? "") !== (pgVals[l.field] ?? "") ? "≠ ON AIR" : "")),
        h("div", { class: "row-gap" }, input, link,
          h("button", { class: "ghost small", title: "Back to the design's own", onclick: () => { input.value = ""; push(comp.id, l.field, null); updateResolved(res, l, ""); } }, "↺")),
        res);
    }));
    box.prepend(...extras());
  }
  // A knockout bracket: how many teams (the tournament's, in Global; changes it on air too).
  function sizeField(s) {
    const set = size => {
      const t = JSON.parse(JSON.stringify(App.state.global.tournament));
      t.top.size = size;
      api("/api/global", { global: { tournament: t } });
    };
    const el = h("div", { class: "field bracket-size" },
      h("label", {}, "Teams in the bracket", h("span", { class: "kind" }, "tournament")),
      h("select", { "data-k": "size", onchange: e => set(+e.target.value) }, ...[8, 16].map(n => h("option", { value: n }, `${n} teams`))),
      h("div", { class: "resolved" }, "The teams and scores are in the Tournament tab. This changes the bracket on air too."));
    markSize(el, s);
    return el;
  }
  // The Schedule: how many upcoming matches it lists (changes it on air too).
  function countField(s) {
    const set = count => {
      const sc = JSON.parse(JSON.stringify(App.state.global.schedule));
      sc.count = count;
      api("/api/global", { global: { schedule: sc } });
    };
    const el = h("div", { class: "field bracket-size" },
      h("label", {}, "Matches shown", h("span", { class: "kind" }, "schedule")),
      h("select", { "data-k": "count", onchange: e => set(+e.target.value) }, ...[1, 2, 3].map(n => h("option", { value: n }, n === 1 ? "1 match" : `${n} matches`))),
      h("div", { class: "resolved" }, "The matches are in the Upcoming Schedule tab. This changes the graphic on air too."));
    markSize(el, s);
    return el;
  }
  // The player graphics: whose players (the left or right team's roster, from the Teams tab).
  function rosterField(s) {
    const el = h("div", { class: "field roster-field" },
      h("label", {}, "Players from", h("span", { class: "kind" }, "teams")),
      h("select", { "data-k": "roster", onchange: e => api("/api/global", { global: { roster: e.target.value } }) },
        h("option", { value: "left" }), h("option", { value: "right" })),
      h("div", { class: "resolved", "data-k": "roster-note" }));
    markSize(el, s);
    return el;
  }
  // The caster lower third: how many boxes, and its colours (Global's, so
  // they change on air too).
  function casterField(s) {
    const set = change => api("/api/global", { global: { caster: change } });
    const el = h("div", { class: "field caster-field" },
      h("label", {}, "Caster boxes", h("span", { class: "kind" }, "global")),
      h("div", { class: "row-gap" },
        h("select", { "data-k": "caster-count", onchange: e => set({ count: +e.target.value }) },
          ...[1, 2, 3, 4].map(n => h("option", { value: n }, n === 1 ? "1 box" : `${n} boxes`))),
        h("label", { class: "swatch" }, "Primary colour",
          h("input", { type: "color", "data-k": "caster-primary", title: "The box", onchange: e => set({ primary: e.target.value }) })),
        h("label", { class: "swatch" }, "Secondary colour",
          h("input", { type: "color", "data-k": "caster-secondary", title: "The box's edge and its shadow", onchange: e => set({ secondary: e.target.value }) })),
        h("label", { class: "swatch" }, "Font colour",
          h("input", { type: "color", "data-k": "caster-text", title: "The name and handle", onchange: e => set({ text: e.target.value }) }))),
      h("div", { class: "resolved" }, "Primary is the box; secondary is the box's edge and its shadow; font is the name and handle. Each box's name and handle are below."));
    markSize(el, s);
    return el;
  }
  // A game HUD's own page (VALORANT's agent select...), shown live from the HUD.
  function hudField(s, comp) {
    const hud = comp.hud.split("/")[0], feed = (s.data.feeds || {})[hud];
    const note = !feed ? `Shows when the ${hud} is connected (its GFX Engine page).`
      : feed.unreachable ? `The ${hud} is on another PC: tick "Let other PCs on the network read the HUD" in it, so this can show here.`
      : `Live from the ${hud} (${feed.from}). Take it like any other graphic.`;
    return h("div", { class: "field" }, h("label", {}, "Game HUD", h("span", { class: "kind" }, hud)),
      h("div", { class: "resolved" }, note));
  }
  // The stats pages: each team's players shown with their headshot or their
  // champion / agent. Team stats and Player stats each have their own (in
  // Global, so it changes on air too).
  function picturesField(s, page) {
    const set = (side, v) => api("/api/global", { global: { pictures: { [page]: { [side]: v } } } });
    const pick = side => h("label", { class: "swatch" }, side === "left" ? "Left team" : "Right team",
      h("select", { "data-k": "pic-" + side, onchange: e => set(side, e.target.value) },
        h("option", { value: "headshot" }, "Headshots"), h("option", { value: "champion" }, "Champions / agents / heroes")));
    const el = h("div", { class: "field caster-field", "data-page": page },
      h("label", {}, "Player pictures", h("span", { class: "kind" }, page === "player" ? "player stats" : "team stats")),
      h("div", { class: "row-gap" }, pick("left"), pick("right")),
      h("div", { class: "resolved" }, "Headshots come from the Teams tab; champions (League), agents (VALORANT) and heroes (Overwatch) from the game. Only " + (page === "player" ? "Player stats" : "Team stats") + " follows this."));
    markSize(el, s);
    return el;
  }
  // The Player stats page: the top player in the game (most of stat 1), or one picked.
  function mvpField(s) {
    const el = h("div", { class: "field mvp-field" },
      h("label", {}, "Player", h("span", { class: "kind" }, "game")),
      h("select", { "data-k": "mvp", onchange: e => api("/api/global", { global: { player_stats: e.target.value } }) }),
      h("div", { class: "resolved", "data-k": "mvp-note" }));
    markSize(el, s);
    return el;
  }
  // The clock: the time of day, or a countdown for Starting Soon or Be Right Back
  // (Global's, so every clock changes, on air too).
  function clockField(s) {
    const set = change => api("/api/global", { global: { clock: Object.assign({}, App.state.global.clock, change) } });
    const el = h("div", { class: "field clock-field" },
      h("label", {}, "Clock", h("span", { class: "kind" }, "global")),
      h("div", { class: "row-gap" },
        h("select", { "data-k": "clock-mode", onchange: e => set({ mode: e.target.value }) },
          h("option", { value: "time" }, "Current time"), h("option", { value: "soon" }, "Starting Soon"), h("option", { value: "brb" }, "Be Right Back")),
        h("input", { type: "time", "data-k": "clock-until", title: "Counts down to this time", onchange: e => set({ until: e.target.value }) })),
      h("div", { class: "resolved", "data-k": "clock-note" }));
    markSize(el, s);
    return el;
  }
  // The timer ({{timer}}): Global's, so it runs on Preview and Program alike.
  function timerField(s) {
    const act = body => api("/api/timer", body);
    const el = h("div", { class: "field timer-field" },
      h("label", {}, "Timer", h("span", { class: "kind" }, "global")),
      h("div", { class: "row-gap" },
        h("span", { class: "timer-now", "data-k": "timer-now" }, GFX.timerText()),
        h("button", { "data-k": "timer-go", onclick: () => act({ action: "toggle" }) }, "Start"),
        h("button", { class: "ghost", onclick: () => act({ action: "reset" }) }, "Reset")),
      h("div", { class: "row-gap" },
        h("input", { type: "text", "data-k": "timer-from", placeholder: "0:00", title: "Starts from this time (m:ss)",
          onchange: e => act({ action: "set", secs: e.target.value }) }),
        h("select", { "data-k": "timer-down", onchange: e => act({ action: "set", down: e.target.value === "down" }) },
          h("option", { value: "up" }, "Counts up"), h("option", { value: "down" }, "Counts down"))),
      h("div", { class: "resolved" }, "Type the time it starts from (m:ss). Reset goes back to it. It runs on air too."));
    markSize(el, s);
    return el;
  }
  const mss = secs => { const t = Math.round(secs); return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`; };
  setInterval(() => document.querySelectorAll(".timer-field").forEach(el => {
    const tm = App.state.global.timer || {};
    // (a countdown that reached 0 has stopped)
    const running = !!tm.started && !(tm.down && GFX.timerSecs() <= 0);
    const go = el.querySelector("[data-k=timer-go]");
    el.querySelector("[data-k=timer-now]").textContent = GFX.timerText();
    go.textContent = running ? "Pause" : "Start";
    go.classList.toggle("on", running);
  }), 250);
  function markSize(el, s) {
    const ro = el.querySelector("[data-k=roster]");
    if (ro) {
      const label = side => { const t = s.global[side]; return `${side === "left" ? "Left" : "Right"} team: ${t.name || "(none)"}${t.game ? ` (${t.game})` : ""}`; };
      ro.options[0].textContent = label("left"); ro.options[1].textContent = label("right");
      if (document.activeElement !== ro) ro.value = s.global.roster || "left";
      const rows = Object.fromEntries((s.data.tables.Roster || []).slice(1));
      el.querySelector("[data-k=roster-note]").textContent = rows.Team
        ? `${rows.Players} player${rows.Players === "1" ? "" : "s"} on ${rows.Team}'s roster in the Teams tab.`
        : "That team isn't in the Teams tab, so the names come from the game's stats.";
    }
    const cs = s.global.caster || { count: 1, primary: "#c2bdff", secondary: "#001a1a" };
    for (const [k, v] of [["caster-count", String(cs.count)], ["caster-primary", cs.primary], ["caster-secondary", cs.secondary],
                          ["caster-text", cs.text || cs.secondary]]) {
      const inp = el.querySelector(`[data-k=${k}]`);
      if (inp && document.activeElement !== inp) inp.value = v;
    }
    for (const side of ["left", "right"]) {
      const sel = el.querySelector(`[data-k=pic-${side}]`);
      const page = (el.querySelector("[data-page]") || el).dataset.page || "team";
      if (sel && document.activeElement !== sel) sel.value = (((s.global.pictures || {})[page] || {})[side]) || "headshot";
    }
    const mv = el.querySelector("[data-k=mvp]");
    if (mv) {
      const st = Object.fromEntries((s.data.tables.Stats || []).slice(1));
      const t1 = st["Stat 1 title"] || "KILLS", title = t1.length <= 3 || t1.includes("/") ? t1 : t1.toLowerCase();   // (ACS, K/D/A stay as they are)
      const opts = [["auto", `Top player (most ${title})`]];
      for (const side of ["Left", "Right"]) {
        for (let n = 1; n <= 10 && (`${side} player ${n}` in st); n++) {
          const name = st[`${side} player ${n}`];
          if (name) opts.push([`${side.toLowerCase()} ${n}`, `${name} (${st[`${side} name`] || side}): ${st[`${side} player ${n} stat 1`] || 0} ${title}`]);
        }
      }
      const pick = s.global.player_stats || "auto";
      if (!opts.some(o => o[0] === pick)) opts.push([pick, "(the player picked, not in this game)"]);
      const sig = JSON.stringify(opts);
      if (mv.dataset.sig !== sig) { mv.dataset.sig = sig; mv.replaceChildren(...opts.map(([v, t]) => h("option", { value: v }, t))); }
      if (document.activeElement !== mv) mv.value = pick;
      el.querySelector("[data-k=mvp-note]").textContent = !st.Status
        ? "No game's stats yet: connect a game HUD. The top player is picked automatically, or pick one here."
        : `Showing ${st["MVP name"] || st.MVP || "nobody"}${st["MVP headshot"] ? "" : " (no headshot in the Teams tab)"}. Their name, flag and headshot come from their team's roster in the Teams tab.`;
    }
    const c = s.global.clock || { mode: "time", until: "" };
    const mode = el.querySelector("[data-k=clock-mode]"), until = el.querySelector("[data-k=clock-until]");
    if (mode && document.activeElement !== mode) mode.value = c.mode;
    if (until) {
      until.hidden = c.mode === "time";
      if (document.activeElement !== until) until.value = c.until || "";
      el.querySelector("[data-k=clock-note]").textContent = c.mode === "time" ? `Shows the time of day, with LOCAL TIME under it.`
        : `Counts down to ${c.until || "(pick a time)"}, with ${c.mode === "soon" ? "STARTING SOON" : "BE RIGHT BACK"} under it.`;
    }
    const tm = s.global.timer || { secs: 0, from: 0, down: false, started: 0 };
    if (el.querySelector("[data-k=timer-go]")) {
      const from = el.querySelector("[data-k=timer-from]"), dn = el.querySelector("[data-k=timer-down]");
      if (document.activeElement !== from) from.value = mss(tm.from);
      if (document.activeElement !== dn) dn.value = tm.down ? "down" : "up";
    }
    const size = ((s.global.tournament || {}).top || {}).size || 8;
    const sel = el.querySelector("[data-k=size]");
    if (sel && document.activeElement !== sel) sel.value = String(size);
    const cnt = el.querySelector("[data-k=count]");
    if (cnt && document.activeElement !== cnt) cnt.value = String((s.global.schedule || {}).count || 3);
  }
  function linkOptions(s, type) {
    const out = [h("option", { value: "" }, "⛓")];
    const tables = s.data.tables || {};
    const names = ["Global", ...Object.keys(s.data.feeds || {})];
    for (const n of names) {
      let rows = (tables[n] || []).slice(1);
      if (type === "rect") rows = rows.filter(r => /colou?r/i.test(r[0]));
      if (!rows.length) continue;
      out.push(h("optgroup", { label: n === "Global" ? "Global configuration" : n },
        ...rows.map(r => h("option", { value: `{{${n}!${r[0]}}}` }, `${r[0]}${r[1] ? " — " + String(r[1]).slice(0, 30) : ""}`))));
    }
    return out;
  }
  function updateResolved(el, layer, value) {
    if (layer.type !== "text") { el.textContent = /\{\{/.test(value || "") ? `${value} → ${GFX.resolve(value)}` : ""; return; }
    const raw = value || layer.text;
    el.textContent = /\{\{/.test(raw) ? "→ " + GFX.resolve(raw) : value ? "" : "Shows: " + layer.text;
  }
  setInterval(() => { if (App.state && App.tab === "control") renderFields(App.state); }, 1000);

  App.on((s, what) => {
    renderChips(s);
    renderRundown(s, what === "assets");
    renderFields(s, what === "assets");
    const names = ids => ids.map(id => (App.comp(id) || {}).name).filter(Boolean).join(", ") || "—";
    $("#pvw-list").textContent = names(s.live.preview.on);
    $("#pgm-list").textContent = names(s.live.program.on);
  });
  pages.control = { shown() { if (App.state) { renderRundown(App.state, true); renderFields(App.state, true); } } };
})();
