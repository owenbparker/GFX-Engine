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
  apply(state) {
    this.state = state;
    GFX.loadFonts(state.fonts);
    GFX.setData(state.data.tables);
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
  for (const b of document.querySelectorAll("#tabs button")) b.classList.toggle("on", b.dataset.tab === name);
  for (const p of document.querySelectorAll(".page")) p.hidden = p.id !== "page-" + name;
  try { localStorage.setItem("gfx-tab", name); } catch (e) { /* private window */ }
  if (pages[name] && pages[name].shown) pages[name].shown();
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
}
document.querySelectorAll("#tabs button").forEach(b => b.addEventListener("click", () => showTab(b.dataset.tab)));
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
  const filter = $("#rundown-filter");
  filter.addEventListener("input", () => renderRundown(App.state, true));
  let dragId = null;
  function renderRundown(s, force) {
    const list = $("#rundown");
    const q = filter.value.trim().toLowerCase();
    const comps = s.project.compositions.filter(c => !q || c.name.toLowerCase().includes(q));
    const pv = s.live.preview, pg = s.live.program;
    if (!selected || !App.comp(selected)) selected = comps[0] && comps[0].id;
    const sig = JSON.stringify([comps.map(c => [c.id, c.name, c.layers]), pv.on, pg.on, pv.values, selected]);
    if (!force && list.dataset.sig === sig) return;
    list.dataset.sig = sig;
    if (!comps.length) {
      list.replaceChildren(h("div", { class: "empty" }, q ? "Nothing matches." : "No graphics yet. Make one in Composer, or add a Photoshop file in Assets."));
      return;
    }
    list.replaceChildren(...comps.map(c => {
      const onPvw = pv.on.includes(c.id), onPgm = pg.on.includes(c.id);
      const nFields = App.fields(c).length;
      const row = h("div", {
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
          h("button", { class: "in-btn" + (onPgm ? " on" : ""), title: onPgm ? "Take it off air (its Out animation)" : "Straight on air (its In animation), leaving the rest",
            onclick: e => { e.stopPropagation(); api("/api/program", { id: c.id, on: !onPgm }); } }, onPgm ? "OUT" : "IN")));
      return row;
    }));
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

  function assetOptions(kind, current) {
    const kinds = kind === "image" ? ["image"] : kind === "video" ? ["video", "image"] : kind === "lottie" ? ["lottie"] : [kind];
    const opts = App.assets.filter(a => kinds.includes(a.kind));
    return [h("option", { value: "" }, "(as designed)"),
      ...opts.map(a => h("option", { value: a.path, selected: a.path === current }, a.path.replace(/^assets\//, "")))];
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
    const sig = JSON.stringify([comp.id, fields.map(f => [f.field, f.type]), App.assetsRev]);
    if (!force && box.dataset.sig === sig) {
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
      box.replaceChildren(h("div", { class: "empty" }, "This graphic has no fields. In Composer, pick a layer and give it a field name to change it from here."));
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
      return h("div", { class: "field" },
        h("label", {}, l.field, h("span", { class: "kind" }, l.type), h("span", { class: "live", "data-live": l.field },
          onAir && (pvVals[l.field] ?? "") !== (pgVals[l.field] ?? "") ? "≠ ON AIR" : "")),
        h("div", { class: "row-gap" }, input,
          h("button", { class: "ghost small", title: "Back to the design's own", onclick: () => { input.value = ""; push(comp.id, l.field, null); updateResolved(res, l, ""); } }, "↺")),
        res);
    }));
  }
  function updateResolved(el, layer, value) {
    if (layer.type !== "text") { el.textContent = ""; return; }
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
