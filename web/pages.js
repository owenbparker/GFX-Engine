// The Assets, Data, Transitions and Outputs pages, and adding files (the
// Add button, or dropping files anywhere on the window).
"use strict";

// --- adding files ----------------------------------------------------------------
async function upload(file) {
  const fps = +($("#seq-fps") && $("#seq-fps").value) || 30;
  toast(`Adding ${file.name}…`);
  const r = await fetch(`/api/upload?fps=${fps}`, { method: "POST", headers: { "X-Filename": encodeURIComponent(file.name) }, body: file });
  const data = await r.json().catch(() => ({}));
  if (!r.ok || data.error) { toast(`${file.name}: ${data.error || r.status}`, true); return null; }
  if (data.comps && data.comps.length) {
    const c = data.comps[0];
    toast(`Made the graphic "${c.name}" (${c.layers.length} layers)` + (data.missing_fonts && data.missing_fonts.length ? ` - add these fonts: ${data.missing_fonts.join(", ")}` : ""));
  } else if (data.job) toast(`Converting ${file.name}…`);
  else if (data.sources && data.sources.length) toast(`Added ${file.name} as a data source`);
  else toast(`Added ${file.name}`);
  return data;
}
async function uploadAll(files) {
  for (const f of files) await upload(f);
}
// Drop files anywhere.
let dragDepth = 0;
addEventListener("dragenter", e => { if ([...e.dataTransfer.types].includes("Files")) { dragDepth++; document.body.classList.add("dragging"); } });
addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; document.body.classList.remove("dragging"); } });
addEventListener("dragover", e => { if ([...e.dataTransfer.types].includes("Files")) e.preventDefault(); });
addEventListener("drop", e => {
  if (!e.dataTransfer.files.length) return;
  e.preventDefault();
  dragDepth = 0;
  document.body.classList.remove("dragging");
  uploadAll([...e.dataTransfer.files]);
});

// --- ASSETS ------------------------------------------------------------------------
(function assets() {
  let kind = "all";
  const KINDS = [["all", "All"], ["image", "Pictures"], ["video", "Video"], ["font", "Fonts"], ["lottie", "Lottie"], ["audio", "Audio"], ["data", "Data"], ["other", "Other"]];
  $("#asset-add").addEventListener("click", () => $("#asset-file").click());
  $("#asset-file").addEventListener("change", e => { uploadAll([...e.target.files]); e.target.value = ""; });
  $("#asset-folder").addEventListener("click", () => api("/api/open", { what: "assets" }));

  function preview(a) {
    if (a.kind === "image") return h("img", { src: "/" + encodeURI(a.path), loading: "lazy" });
    if (a.kind === "video") {
      const v = h("video", { src: "/" + encodeURI(a.path) + "#t=0.5", preload: "metadata", muted: true, playsInline: true,
        onmouseenter: e => e.target.play().catch(() => {}), onmouseleave: e => e.target.pause() });
      return v;
    }
    if (a.kind === "font") return h("span", { style: { fontFamily: `"${a.postscript}"`, fontSize: "38px" } }, "Aa");
    return h("span", {}, { lottie: "✦", audio: "♪", data: "▦" }[a.kind] || "📄");
  }
  function info(a) {
    const bits = [fmtBytes(a.size)];
    if (a.width) bits.unshift(`${a.width}×${a.height}`);
    if (a.kind === "video") bits.unshift(`${(a.duration || 0).toFixed(1)} s`);
    if (a.kind === "font") bits.unshift(a.postscript);
    return bits.join(" · ");
  }
  function render() {
    const s = App.state;
    if (!s) return;
    const chips = $("#asset-kinds");
    const counts = {};
    for (const a of App.assets) counts[a.kind] = (counts[a.kind] || 0) + 1;
    chips.replaceChildren(...KINDS.filter(([k]) => k === "all" || counts[k]).map(([k, t]) =>
      h("button", { class: k === kind ? "on" : "", onclick: () => { kind = k; render(); } }, `${t}${k === "all" ? "" : " " + counts[k]}`)));
    // Fonts the graphics use that aren't added.
    const used = new Set();
    for (const c of s.project.compositions) for (const l of c.layers) if (l.type === "text" && l.font) used.add(l.font);
    const missing = [...used].filter(f => !GFX.hasFont(f)).sort();
    const note = $("#missing-fonts");
    note.hidden = !missing.length;
    note.textContent = missing.length ? `The graphics use fonts that aren't added yet (similar ones stand in): ${missing.join(", ")}. Drop their .ttf / .otf files here.` : "";
    const shown = App.assets.filter(a => kind === "all" || a.kind === kind);
    const folders = new Map();
    for (const a of shown) { if (!folders.has(a.folder)) folders.set(a.folder, []); folders.get(a.folder).push(a); }
    const grid = $("#asset-grid");
    if (!shown.length) { grid.replaceChildren(h("div", { class: "empty" }, "Nothing here yet.")); return; }
    grid.replaceChildren(...[...folders.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([folder, list]) => h("div", {},
      h("div", { class: "folder-title" }, folder || "assets"),
      h("div", { class: "cards" }, list.map(a => h("div", { class: "card" },
        h("div", { class: "pv" }, preview(a)),
        h("div", { class: "meta" },
          h("div", { class: "nm", title: a.path }, a.name,
            a.kind === "video" && a.alpha ? h("span", { class: "badge", title: "See-through" }, "ALPHA") : null,
            a.kind === "video" && a.playable === false ? h("span", { class: "badge", title: "Not web-ready" }, "!") : null),
          h("div", { class: "info" }, info(a))),
        h("div", { class: "acts" },
          h("button", { class: "small", title: "Copy its path", onclick: () => copy(a.path) }, "Copy"),
          a.kind === "video" ? h("button", { class: "small", title: "Make a stinger transition with it", onclick: () => makeStinger(a) }, "Stinger") : null,
          a.kind === "image" ? h("button", { class: "small", title: "A new graphic with this picture", onclick: () => graphicFrom(a) }, "Graphic") : null,
          h("div", { class: "spacer" }),
          h("button", { class: "small danger", title: "Delete the file", onclick: async () => {
            if (confirm(`Delete ${a.path}?`)) { await api("/api/asset/delete", { path: a.path }); }
          } }, "✕"))))))));
  }
  function renderJobs() {
    const jobs = (App.state && App.state.jobs || []).filter(j => j.status !== "done" || Date.now() / 1000);
    $("#jobs").replaceChildren(...jobs.filter(j => j.status !== "done").map(j => h("div", { class: "job" + (j.status === "error" ? " error" : "") },
      h("span", {}, j.name), j.status === "error" ? h("span", {}, j.error) : h("progress", { max: 100, value: j.progress }),
      j.status === "running" ? h("span", { class: "muted" }, j.progress + "%") : null)));
  }
  async function makeStinger(a) {
    const cut = (await fetch("/api/stinger-cut?src=" + encodeURIComponent(a.path)).then(r => r.json())).cut;
    const list = App.state.project.transitions.slice();
    list.push({ id: "t" + Math.random().toString(16).slice(2, 10), name: a.name.replace(/\.\w+$/, ""), type: "stinger", src: a.path,
      cut: cut == null ? Math.round((a.duration || 1) * 500) : cut, audio: true, volume: 1, enabled: true });
    await api("/api/transitions", { transitions: list });
    toast(`Stinger "${a.name}" added` + (cut == null ? " (it never covers the whole screen: check its cut point)" : ` (cuts at ${cut} ms)`));
    showTab("transitions");
  }
  async function graphicFrom(a) {
    const w = a.width || 1920, hh = a.height || 1080;
    const k = Math.min(1, 1920 / w, 1080 / hh);
    const { layer } = await api("/api/layer/blank", { type: "image" });
    Object.assign(layer, { name: a.name.replace(/\.\w+$/, ""), src: a.path, fit: "fill", w: Math.round(w * k), h: Math.round(hh * k),
      x: Math.round((1920 - w * k) / 2), y: Math.round((1080 - hh * k) / 2) });
    const comp = { name: layer.name, layer: 0, layers: [layer] };
    const r = await api("/api/comp/new", { comp });
    window.editGraphic(r.comp.id);
  }
  let lastJobs = "";
  App.on((s, what) => {
    const jobs = JSON.stringify(s.jobs);
    if (jobs !== lastJobs) { lastJobs = jobs; renderJobs(); }
    if (what === "assets" || App.tab === "assets") render();
  });
  pages.assets = { shown: render };
})();

// --- DATA ---------------------------------------------------------------------------
(function data() {
  let selected = null;
  let adding = false;
  const colName = i => { let s = ""; i++; while (i) { const r = (i - 1) % 26; s = String.fromCharCode(65 + r) + s; i = Math.floor((i - 1) / 26); } return s; };
  function sources() { return App.state.project.sources; }

  function renderList() {
    const s = App.state;
    const list = $("#src-list");
    if (!sources().length && !adding) adding = true;
    list.replaceChildren(...sources().map(src => {
      const st = s.data.status[src.id] || {};
      const rows = (s.data.tables[src.name] || []).length;
      return h("div", { class: "src" + (src.id === selected ? " sel" : ""), onclick: () => { selected = src.id; adding = false; render(); } },
        h("div", { class: "nm" }, src.name),
        h("div", { class: "info" }, { gsheet: "Google Sheet", file: "File", url: "Web" }[src.type], " · ", src.url || src.path || ""),
        st.error ? h("div", { class: "err" }, st.error) : h("div", { class: "info" }, `${rows} rows · every ${src.refresh}s`));
    }));
  }
  function form(src) {
    const isNew = !src;
    src = src ? JSON.parse(JSON.stringify(src)) : { name: "Data", type: "gsheet", url: "", path: "", sheet: "", refresh: 5 };
    const where = h("div", { class: "full" });
    const typeSel = h("select", { onchange: e => { src.type = e.target.value; drawWhere(); } },
      [["gsheet", "Google Sheet"], ["file", "File (CSV, Excel, text, JSON)"], ["url", "Web address (CSV / JSON)"]].map(([v, t]) => h("option", { value: v, selected: src.type === v }, t)));
    function drawWhere() {
      if (src.type === "gsheet") {
        where.replaceChildren(h("label", {}, "Link to the sheet (share it as \"Anyone with the link can view\", or File > Share > Publish to web)",
          h("input", { value: src.url || "", placeholder: "https://docs.google.com/spreadsheets/d/…", oninput: e => (src.url = e.target.value) })));
      } else if (src.type === "url") {
        where.replaceChildren(h("label", {}, "Web address", h("input", { value: src.url || "", placeholder: "https://…/data.csv", oninput: e => (src.url = e.target.value) })));
      } else {
        const files = App.assets.filter(a => a.kind === "data" || a.kind === "lottie");
        const file = h("input", { type: "file", hidden: true, accept: ".csv,.tsv,.txt,.json,.xlsx,.xlsm", onchange: async e => {
          const f = e.target.files[0];
          if (!f) return;
          const r = await upload(f);
          if (r && r.sources && r.sources[0]) { src.path = r.sources[0].path; await App.loadAssets(); drawWhere(); }
        } });
        where.replaceChildren(h("label", {}, "A file added to the engine, or the full path of a file on this PC (it's read again when it changes)",
          h("div", { class: "row-gap" },
            h("input", { list: "data-files", value: src.path || "", placeholder: "assets/scores.csv or C:\\Scores\\live.xlsx", oninput: e => (src.path = e.target.value) }),
            h("datalist", { id: "data-files" }, files.map(a => h("option", { value: a.path }))),
            h("button", { onclick: () => file.click() }, "Add file…"), file)));
      }
    }
    drawWhere();
    return h("div", { class: "data-form" },
      h("label", {}, "Name (used in {{Name!B2}})", h("input", { value: src.name, oninput: e => (src.name = e.target.value) })),
      h("label", {}, "Kind", typeSel),
      h("label", {}, "Sheet / tab (optional)", h("input", { value: src.sheet || "", placeholder: "first", oninput: e => (src.sheet = e.target.value) })),
      h("label", {}, "Read every (seconds)", h("input", { type: "number", min: 1, value: src.refresh, oninput: e => (src.refresh = +e.target.value) })),
      where,
      h("div", { class: "full row-gap", style: { marginTop: "10px" } },
        h("button", { class: "primary", onclick: async () => {
          const list = sources().filter(x => x.id !== src.id);
          if (isNew) list.push(src); else list.splice(sources().findIndex(x => x.id === src.id), 0, src);
          await api("/api/sources", { sources: list });
          adding = false;
          setTimeout(() => { const found = sources().find(x => x.name === src.name || x.id === src.id); if (found) selected = found.id; render(); }, 300);
        } }, isNew ? "Add source" : "Save"),
        !isNew ? h("button", { onclick: () => api("/api/source/refresh", { id: src.id }) }, "Read now") : null,
        h("div", { class: "spacer" }),
        !isNew ? h("button", { class: "danger", onclick: async () => {
          if (!confirm(`Remove the data source "${src.name}"? Graphics using it show nothing there.`)) return;
          await api("/api/sources", { sources: sources().filter(x => x.id !== src.id) });
          selected = null; render();
        } }, "Remove") : h("button", { onclick: () => { adding = false; render(); } }, "Cancel")));
  }
  function table(src) {
    const rows = App.state.data.tables[src.name] || [];
    const st = App.state.data.status[src.id] || {};
    const cols = Math.max(1, ...rows.map(r => r.length));
    const head = h("tr", {}, h("th", {}, ""), Array.from({ length: cols }, (_, i) => h("th", {}, colName(i))));
    const body = rows.slice(0, 500).map((r, ri) => h("tr", {}, h("td", { class: "rn" }, ri + 1),
      Array.from({ length: cols }, (_, ci) => {
        const ref = `{{${src.name}!${colName(ci)}${ri + 1}}}`;
        const hdr = ri > 0 && rows[0][ci] ? `{{${src.name}!${rows[0][ci]}#${ri}}}` : null;
        return h("td", { class: "c", title: `Click: ${ref}` + (hdr ? `\nShift+click: ${hdr}` : ""),
          onclick: e => copy(e.shiftKey && hdr ? hdr : ref) }, r[ci] || "");
      })));
    return h("div", { class: "table-wrap" },
      st.error ? h("div", { class: "notice", style: { margin: "10px" } }, st.error) : null,
      rows.length ? h("table", { class: "sheet" }, h("thead", {}, head), h("tbody", {}, body))
        : h("div", { class: "empty" }, st.error ? "" : "No data read yet."),
      st.updated ? h("div", { class: "muted small", style: { padding: "6px 10px" } }, "Read at " + new Date(st.updated * 1000).toLocaleTimeString()) : null);
  }
  function render() {
    if (!App.state) return;
    renderList();
    const main = $("#src-main");
    if (adding) { main.replaceChildren(h("div", { class: "panel-head" }, h("h3", {}, "New data source")), form(null)); return; }
    const src = sources().find(x => x.id === selected) || sources()[0];
    if (!src) { main.replaceChildren(); return; }
    selected = src.id;
    const keep = main.querySelector(".data-form") && main.dataset.src === src.id && main.contains(document.activeElement);
    if (keep) { const old = main.querySelector(".table-wrap"); if (old) old.replaceWith(table(src)); return; }
    main.dataset.src = src.id;
    main.replaceChildren(h("div", { class: "panel-head" }, h("h3", {}, src.name)), form(src), table(src));
  }
  $("#src-add").addEventListener("click", () => { adding = true; render(); });
  let sig = "";
  App.on(s => {
    const now = JSON.stringify([s.project.sources, s.data.rev]);
    if (now !== sig && App.tab === "data") { sig = now; render(); }
  });
  pages.data = { shown: () => { sig = ""; render(); } };
})();

// --- TRANSITIONS ---------------------------------------------------------------------
(function transitions() {
  let list = null;
  const save = debounce(() => api("/api/transitions", { transitions: list, default: App.state.project.default_transition }), 250);
  function card(t) {
    const set = (k, v, redraw) => { t[k] = v; save(); if (redraw) render(true); };
    const isDefault = App.state.project.default_transition === t.id;
    const body = [];
    if (["fade", "dip", "wipe"].includes(t.type)) {
      body.push(h("div", { class: "grid3" },
        h("label", {}, "Length (ms)", h("input", { type: "number", min: 0, step: 50, value: t.dur || 500, onchange: e => set("dur", +e.target.value) })),
        t.type === "dip" ? h("label", {}, "Colour", h("input", { type: "color", value: t.color || "#000000", onchange: e => set("color", e.target.value) })) : null,
        t.type === "wipe" ? h("label", {}, "Direction", h("select", { onchange: e => set("direction", e.target.value) },
          ["left", "right", "up", "down"].map(d => h("option", { value: d, selected: (t.direction || "left") === d }, d)))) : null));
    }
    if (t.type === "animate") body.push(h("p", { class: "muted small" }, "Each graphic plays its own In and Out animation (set in Composer)."));
    if (t.type === "cut") body.push(h("p", { class: "muted small" }, "Straight away, no animation."));
    if (t.type === "stinger") {
      const videos = App.assets.filter(a => a.kind === "video");
      const vid = h("video", { src: t.src ? "/" + encodeURI(t.src) : "", muted: true, playsInline: true, preload: "auto" });
      const asset = videos.find(a => a.path === t.src);
      const dur = asset ? asset.duration : 0;
      const range = h("input", { type: "range", min: 0, max: Math.round(dur * 1000) || 1000, value: t.cut || 0,
        oninput: e => { vid.currentTime = +e.target.value / 1000; cutInput.value = e.target.value; mark.style.left = pct(+e.target.value); },
        onchange: e => set("cut", +e.target.value) });
      const pct = ms => (dur ? Math.min(100, ms / (dur * 10)) : 0) + "%";
      const mark = h("div", { class: "cut-mark", style: { left: pct(t.cut || 0) } });
      const cutInput = h("input", { type: "number", min: 0, step: 10, value: t.cut || 0,
        onchange: e => { set("cut", +e.target.value); range.value = e.target.value; mark.style.left = pct(+e.target.value); vid.currentTime = +e.target.value / 1000; } });
      vid.addEventListener("loadeddata", () => { vid.currentTime = (t.cut || 0) / 1000; });
      body.push(
        h("label", {}, "Video (see-through WebM, or any video; .mov is converted when added)",
          h("select", { onchange: e => { set("src", e.target.value, true); detect(t); } }, h("option", { value: "" }, "(pick one)"),
            videos.map(a => h("option", { value: a.path, selected: a.path === t.src }, a.path.replace(/^assets\//, "") + (a.alpha ? "" : " (not see-through)"))))),
        h("div", { class: "tr-video" }, vid),
        h("div", { class: "scrub" }, range, mark),
        h("div", { class: "grid3" },
          h("label", { title: "When the stinger covers the screen and Program changes underneath" }, "Cut point (ms)", cutInput),
          h("label", {}, "Volume", h("input", { type: "number", min: 0, max: 1, step: 0.1, value: t.volume ?? 1, onchange: e => set("volume", +e.target.value) })),
          h("label", {}, "\u00a0", h("button", { title: "Find when it first covers the whole screen", onclick: () => detect(t) }, "Find cut point"))),
        h("div", { class: "row-gap" },
          h("label", { class: "toggle" }, h("input", { type: "checkbox", checked: t.audio !== false, onchange: e => set("audio", e.target.checked) }), "Play its sound"),
          h("button", { class: "small", onclick: () => { vid.currentTime = 0; vid.play(); } }, "▶ Play"),
          asset && !asset.alpha ? h("span", { class: "warnline" }, "Not see-through: it covers everything while it plays.") : null));
    }
    return h("div", { class: "tr" + (t.enabled === false ? " off" : "") },
      h("div", { class: "tr-head" },
        h("input", { type: "checkbox", title: "On the take bar", checked: t.enabled !== false, onchange: e => set("enabled", e.target.checked, true) }),
        h("input", { class: "nm", value: t.name, onchange: e => set("name", e.target.value) }),
        h("span", { class: "badge" }, t.type.toUpperCase()),
        h("button", { class: "small" + (isDefault ? " on" : ""), title: "TAKE uses this unless another is picked",
          onclick: () => { App.state.project.default_transition = t.id; api("/api/transitions", { transitions: list, default: t.id }); } }, isDefault ? "Default" : "Make default"),
        h("button", { class: "small danger", title: "Remove", onclick: () => { list = list.filter(x => x !== t); save(); render(true); } }, "✕")),
      body);
  }
  async function detect(t) {
    if (!t.src) return;
    toast("Finding the cut point…");
    const r = await fetch("/api/stinger-cut?src=" + encodeURIComponent(t.src)).then(r => r.json());
    if (r.cut == null) { toast("It never covers the whole screen; set the cut point by hand", true); return; }
    t.cut = r.cut;
    save();
    render(true);
    toast(`Cuts at ${r.cut} ms`);
  }
  function render(force) {
    if (!App.state) return;
    if (!list || force !== true) list = JSON.parse(JSON.stringify(App.state.project.transitions));
    $("#tr-list").replaceChildren(...list.map(card));
  }
  document.querySelectorAll("[data-new-tr]").forEach(b => b.addEventListener("click", () => {
    const type = b.dataset.newTr;
    const t = { id: "t" + Math.random().toString(16).slice(2, 10), type, enabled: true,
      name: { fade: "Fade", dip: "Dip to black", wipe: "Wipe", stinger: "Stinger" }[type], dur: type === "dip" ? 800 : 500, cut: 500, audio: true };
    list.push(t);
    save();
    render(true);
  }));
  let sig = "";
  App.on((s, what) => {
    const now = JSON.stringify([s.project.transitions, s.project.default_transition, App.assetsRev]);
    if (App.tab === "transitions" && now !== sig && !document.querySelector("#tr-list").contains(document.activeElement)) { sig = now; render(); }
  });
  pages.transitions = { shown: () => { sig = ""; render(); } };
})();

// --- OUTPUTS ------------------------------------------------------------------------
(function outputs() {
  const chosen = new Set();
  function urlRow(label, url) {
    return h("div", { class: "url-row" }, h("span", { class: "lbl", title: label }, label), h("code", { title: url }, url),
      h("button", { class: "small", onclick: () => copy(url, label + " address") }, "Copy"),
      h("a", { class: "btn small", href: url, target: "_blank" }, "Open"));
  }
  function render() {
    const s = App.state;
    if (!s) return;
    const hosts = ["localhost", ...(s.app.network ? s.app.addresses : [])];
    const base = host => `http://${host}:${s.app.port}`;
    const out = $("#out-urls");
    out.replaceChildren(
      ...hosts.map(host => h("div", {},
        h("div", { class: "folder-title" }, host === "localhost" ? "On this PC" : `From other PCs (${host})`),
        urlRow("Program", base(host) + "/output"),
        urlRow("Preview", base(host) + "/output?bus=preview"),
        host === "localhost" ? null : urlRow("Control panel", base(host) + "/control"))),
      h("div", { class: "folder-title" }, "One graphic each (shows when it's on Program)"),
      ...s.project.compositions.map(c => urlRow(c.name, base(hosts[hosts.length - 1]) + "/output?comp=" + c.id)));
    const plain = (label, text) => h("div", { class: "url-row" }, h("span", { class: "lbl" }, label), h("code", {}, text),
      h("button", { class: "small", onclick: () => copy(text, label) }, "Copy"));
    $("#companion-info").replaceChildren(
      ...hosts.map(host => plain(host === "localhost" ? "On this PC" : "From another PC", host === "localhost" ? "127.0.0.1" : host)),
      plain("Port", String(s.app.port)));
    const allow = $("#net-allow");
    allow.checked = s.app.network;
    const name = $("#net-name");
    if (document.activeElement !== name) name.value = s.app.name;
    // Export list.
    const ex = $("#export-list");
    for (const c of s.project.compositions) if (!ex.dataset.init) chosen.add(c.id);
    ex.dataset.init = "1";
    ex.replaceChildren(...s.project.compositions.map(c => h("label", {},
      h("input", { type: "checkbox", checked: chosen.has(c.id), onchange: e => { e.target.checked ? chosen.add(c.id) : chosen.delete(c.id); } }), c.name)));
  }
  async function engines(scan) {
    const box = $("#engines");
    if (scan) box.replaceChildren(h("div", { class: "muted" }, "Looking on the network…"));
    const r = await fetch(scan ? "/api/scan" : "/api/engines").then(r => r.json()).catch(() => ({ engines: [] }));
    box.replaceChildren(...(r.engines.length ? r.engines.map(e => h("div", { class: "engine" },
      h("b", {}, e.name), h("span", { class: "muted" }, `${e.ip}:${e.port}`), h("div", { class: "spacer" }),
      h("button", { class: "small", onclick: () => copy(`${e.url}/output`, "its Program address") }, "Copy output"),
      h("a", { class: "btn small", href: `${e.url}/control`, target: "_blank" }, "Open"))) :
      [h("div", { class: "muted small" }, scan ? "No other engines found." : "None seen yet. Engines that allow the network show up here by themselves; Scan looks for them too.")]));
  }
  $("#net-scan").addEventListener("click", () => engines(true));
  $("#net-allow").addEventListener("change", e => api("/api/settings", { allow_network: e.target.checked }));
  $("#net-name").addEventListener("change", e => api("/api/settings", { name: e.target.value.trim() }));
  $("#export-all").addEventListener("click", () => { App.comps().forEach(c => chosen.add(c.id)); render(); });
  $("#export-none").addEventListener("click", () => { chosen.clear(); render(); });
  $("#export-go").addEventListener("click", () => {
    if (!chosen.size) return toast("Pick some graphics to export", true);
    const ids = App.comps().filter(c => chosen.has(c.id)).map(c => c.id);
    const name = ids.length === 1 ? App.comp(ids[0]).name : App.state.project.name;
    location.href = `/api/export?comps=${ids.join(",")}&name=${encodeURIComponent(name)}`;
  });
  $("#ws-folder").addEventListener("click", () => api("/api/open", { what: "workspace" }));

  let logAfter = 0;
  async function pollLog() {
    try {
      const r = await fetch("/api/log?after=" + logAfter).then(r => r.json());
      const box = $("#log");
      for (const l of r.lines) {
        logAfter = l.id;
        box.appendChild(h("div", { class: l.level }, h("span", { class: "t" }, l.time), l.message));
      }
      while (box.childNodes.length > 400) box.firstChild.remove();
      if (r.lines.length) box.scrollTop = box.scrollHeight;
    } catch (e) { /* engine restarting */ }
  }
  setInterval(() => { if (App.tab === "outputs") pollLog(); }, 1500);
  let sig = "";
  App.on(s => {
    const now = JSON.stringify([s.app, s.project.compositions.map(c => [c.id, c.name])]);
    if (App.tab === "outputs" && now !== sig) { sig = now; render(); }
  });
  pages.outputs = { shown: () => { sig = ""; render(); engines(false); pollLog(); } };
})();
