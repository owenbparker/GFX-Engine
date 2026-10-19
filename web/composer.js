// Composer: making and editing graphics. The graphic list and its layers on
// the left, the canvas in the middle (drag to move, handles to resize), the
// selected layer's properties and animation on the right.
"use strict";

(function composer() {
  const canvas = $("#canvas"), stage = $("#canvas-stage"), selLayer = $("#canvas-sel");
  let compId = null;          // the graphic being edited
  let comp = null;            // our copy of it (changes are saved as they're made)
  let root = null;            // its element on the canvas
  let selected = null;        // selected layer id
  let scale = 0.5, offX = 0, offY = 0;
  let pending = false, lastSent = "";
  const undo = [], redo = [];
  try { compId = localStorage.getItem("gfx-edit"); } catch (e) { /* */ }

  const TYPE_ICON = { text: "T", rect: "▭", image: "🖼", video: "▶", lottie: "✦" };

  // --- saving ------------------------------------------------------------
  const saveSoon = debounce(save, 120);
  function save() {
    if (!comp) return;
    const body = JSON.stringify(comp);
    if (body === lastSent) { pending = false; return; }
    lastSent = body;
    api("/api/comp/save", { comp }).finally(() => { pending = false; });
  }
  function changed(opts) {
    pending = true;
    saveSoon();
    redraw();
    if (!opts || !opts.keepList) renderLayers();
    if (opts && opts.props) renderProps();
    else syncPropsGeometry();
  }
  function snapshot() {
    undo.push(JSON.stringify(comp));
    if (undo.length > 100) undo.shift();
    redo.length = 0;
  }
  function restore(json) {
    comp = JSON.parse(json);
    if (!comp.layers.some(l => l.id === selected)) selected = null;
    changed({ props: true });
  }

  // --- the graphic list ---------------------------------------------------
  function renderComps() {
    const list = $("#comp-list");
    const comps = App.comps();
    const sig = JSON.stringify(comps.map(c => [c.id, c.name, c.layers]) ) + compId;
    if (list.dataset.sig === sig) return;
    list.dataset.sig = sig;
    list.replaceChildren(...comps.map(c => h("div", { class: "comp-item" + (c.id === compId ? " sel" : ""), onclick: () => open(c.id) },
      thumb(c, {}, 48), h("span", { class: "nm" }, c.name))));
    if (!comps.length) list.replaceChildren(h("div", { class: "empty" }, "No graphics yet."));
  }
  function open(id) {
    compId = id;
    selected = null;
    undo.length = redo.length = 0;
    try { localStorage.setItem("gfx-edit", id); } catch (e) { /* */ }
    adopt(true);
  }
  // Takes the engine's copy of the graphic (unless we've changes on the way).
  function adopt(force) {
    const server = App.comp(compId) || App.comps()[0];
    if (!server) { comp = null; compId = null; draw(); renderLayers(); renderProps(); renderComps(); return; }
    if (server.id !== compId) { compId = server.id; force = true; }
    const json = JSON.stringify(server);
    if (!force && (pending || json === JSON.stringify(comp))) return;
    if (!force && json === lastSent) return;
    comp = JSON.parse(json);
    lastSent = json;
    if (selected && !comp.layers.some(l => l.id === selected)) selected = null;
    draw();
    renderLayers();
    renderProps();
    renderComps();
  }
  $("#comp-new").addEventListener("click", async () => {
    const name = prompt("Name of the new graphic", "New graphic");
    if (!name) return;
    const r = await api("/api/comp/new", { name, after: compId });
    open(r.comp.id);
  });
  $("#comp-dup").addEventListener("click", async () => { if (compId) open((await api("/api/comp/duplicate", { id: compId })).comp.id); });
  $("#comp-del").addEventListener("click", async () => {
    if (!comp || !confirm(`Delete "${comp.name}"? It comes off air too.`)) return;
    await api("/api/comp/delete", { id: compId });
    compId = null;
    adopt(true);
  });

  // --- layers ---------------------------------------------------------------
  let dragLayer = null;
  function renderLayers() {
    const list = $("#layer-list");
    if (!comp) { list.replaceChildren(); return; }
    // Top layer first, as in Photoshop.
    list.replaceChildren(...[...comp.layers].reverse().map(l => h("div", {
      class: "ly" + (l.id === selected ? " sel" : ""), draggable: true,
      onclick: () => selectLayer(l.id),
      ondragstart: e => { dragLayer = l.id; e.dataTransfer.effectAllowed = "move"; },
      ondragover: e => { e.preventDefault(); e.currentTarget.classList.add("drag-over"); },
      ondragleave: e => e.currentTarget.classList.remove("drag-over"),
      ondrop: e => {
        e.preventDefault();
        e.currentTarget.classList.remove("drag-over");
        if (!dragLayer || dragLayer === l.id) return;
        snapshot();
        const moving = comp.layers.find(x => x.id === dragLayer);
        comp.layers = comp.layers.filter(x => x.id !== dragLayer);
        // Dropped on a row: goes just above it.
        comp.layers.splice(comp.layers.findIndex(x => x.id === l.id) + 1, 0, moving);
        changed();
      },
    },
      h("span", { class: "eye" + (l.visible === false ? " off" : ""), title: "Show / hide",
        onclick: e => { e.stopPropagation(); snapshot(); l.visible = l.visible === false; changed(); } }, "👁"),
      h("span", { class: "ic" }, TYPE_ICON[l.type] || "?"),
      h("span", { class: "nm", title: l.name }, l.name),
      l.field ? h("span", { class: "fld", title: `Changed from Control as "${l.field}"` }, "field") : null)));
  }
  function selectLayer(id) {
    selected = id;
    renderLayers();
    renderProps();
    drawSelection();
  }
  document.querySelectorAll("[data-add]").forEach(b => b.addEventListener("click", async () => {
    if (!comp) return toast("Make or pick a graphic first", true);
    const { layer } = await api("/api/layer/blank", { type: b.dataset.add });
    snapshot();
    layer.name = { text: "Text", rect: "Shape", image: "Picture", video: "Video", lottie: "Animation" }[layer.type];
    comp.layers.push(layer);
    selected = layer.id;
    changed({ props: true });
  }));

  // --- the canvas --------------------------------------------------------------
  function fitStage() {
    const r = canvas.getBoundingClientRect();
    const pad = 24;
    scale = Math.min((r.width - pad * 2) / GFX.W, (r.height - pad * 2) / GFX.H);
    offX = (r.width - GFX.W * scale) / 2;
    offY = (r.height - GFX.H * scale) / 2;
    stage.style.transform = `translate(${offX}px, ${offY}px) scale(${scale})`;
    drawSelection();
  }
  new ResizeObserver(fitStage).observe(canvas);
  $("#canvas-bg").addEventListener("change", e => { canvas.className = "canvas " + e.target.value; try { localStorage.setItem("gfx-canvas-bg", e.target.value); } catch (err) { /* */ } });
  try { const bg = localStorage.getItem("gfx-canvas-bg"); if (bg) { $("#canvas-bg").value = bg; } } catch (e) { /* */ }
  canvas.className = "canvas " + $("#canvas-bg").value;

  function draw() {
    if (root) { GFX.destroy(root); root.remove(); root = null; }
    $("#canvas-name").textContent = comp ? comp.name : "";
    if (!comp) return;
    root = GFX.buildComp(comp, {}, { showHidden: true, muted: true });
    stage.appendChild(root);
    drawSelection();
  }
  function redraw() {
    if (!comp) return;
    if (!root) return draw();
    GFX.updateComp(root, comp, {});
    $("#canvas-name").textContent = comp.name;
    drawSelection();
  }
  const layerById = id => comp && comp.layers.find(l => l.id === id);
  const toScreen = (x, y) => [offX + x * scale, offY + y * scale];

  const HANDLES = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
  function drawSelection(guides) {
    selLayer.replaceChildren();
    const l = layerById(selected);
    if (!l) { $("#canvas-pos").textContent = ""; return; }
    const [x, y] = toScreen(l.x, l.y);
    const w = l.w * scale, hgt = l.h * scale;
    const box = h("div", { class: "sel-box", style: { left: x + "px", top: y + "px", width: w + "px", height: hgt + "px",
      transform: l.rotation ? `rotate(${l.rotation}deg)` : "" } });
    for (const hd of HANDLES) {
      const hx = hd.includes("w") ? 0 : hd.includes("e") ? 100 : 50;
      const hy = hd.includes("n") ? 0 : hd.includes("s") ? 100 : 50;
      box.appendChild(h("div", { class: "handle", "data-h": hd, style: { left: hx + "%", top: hy + "%", cursor: hd + "-resize" } }));
    }
    selLayer.appendChild(box);
    for (const g of guides || []) {
      if (g.x != null) { const [gx] = toScreen(g.x, 0); selLayer.appendChild(h("div", { class: "guide", style: { left: gx + "px", top: 0, bottom: 0, width: "1px" } })); }
      if (g.y != null) { const [, gy] = toScreen(0, g.y); selLayer.appendChild(h("div", { class: "guide", style: { top: gy + "px", left: 0, right: 0, height: "1px" } })); }
    }
    $("#canvas-pos").textContent = `${Math.round(l.x)}, ${Math.round(l.y)} · ${Math.round(l.w)}×${Math.round(l.h)}`;
  }

  // Which layer is at a point (top first, visible ones only).
  function hit(px, py) {
    for (const l of [...comp.layers].reverse()) {
      if (l.visible === false) continue;
      if (px >= l.x && px <= l.x + l.w && py >= l.y && py <= l.y + l.h) return l;
    }
    return null;
  }
  // Snapping to the canvas' edges and middle and other layers' edges and middles.
  function snap(l, moving) {
    const tol = 6 / scale;
    const xs = [0, GFX.W / 2, GFX.W], ys = [0, GFX.H / 2, GFX.H];
    for (const o of comp.layers) {
      if (o.id === l.id || o.visible === false) continue;
      xs.push(o.x, o.x + o.w / 2, o.x + o.w);
      ys.push(o.y, o.y + o.h / 2, o.y + o.h);
    }
    const guides = [];
    const best = (vals, cands) => {
      let b = null;
      for (const [edge, off] of vals) for (const c of cands) if (Math.abs(edge - c) < tol && (!b || Math.abs(edge - c) < Math.abs(b.d))) b = { d: c - edge, c, off };
      return b;
    };
    if (moving) {
      const bx = best([[l.x, 0], [l.x + l.w / 2, 0], [l.x + l.w, 0]], xs);
      if (bx) { l.x += bx.d; guides.push({ x: bx.c }); }
      const by = best([[l.y, 0], [l.y + l.h / 2, 0], [l.y + l.h, 0]], ys);
      if (by) { l.y += by.d; guides.push({ y: by.c }); }
    }
    return guides;
  }

  canvas.addEventListener("mousedown", e => {
    if (!comp || e.button !== 0) return;
    const r = canvas.getBoundingClientRect();
    const px = (e.clientX - r.left - offX) / scale, py = (e.clientY - r.top - offY) / scale;
    const handle = e.target.dataset && e.target.dataset.h;
    let l = layerById(selected);
    if (!handle) {
      const under = hit(px, py);
      // Clicking inside the selected layer keeps it (it may be under another).
      if (!(l && px >= l.x && px <= l.x + l.w && py >= l.y && py <= l.y + l.h) || e.altKey) l = under;
      selected = l ? l.id : null;
      renderLayers();
      renderProps();
      drawSelection();
      if (!l) return;
    }
    e.preventDefault();
    const start = { x: l.x, y: l.y, w: l.w, h: l.h, px, py };
    const ratio = l.w / Math.max(1, l.h);
    let moved = false;
    const move = ev => {
      const qx = (ev.clientX - r.left - offX) / scale, qy = (ev.clientY - r.top - offY) / scale;
      let dx = qx - start.px, dy = qy - start.py;
      if (!moved && Math.abs(dx) < 2 && Math.abs(dy) < 2) return;
      if (!moved) { snapshot(); moved = true; }
      let guides = [];
      if (!handle) {
        if (ev.shiftKey) { if (Math.abs(dx) > Math.abs(dy)) dy = 0; else dx = 0; }
        l.x = Math.round(start.x + dx); l.y = Math.round(start.y + dy);
        if (!ev.ctrlKey) guides = snap(l, true);
        l.x = Math.round(l.x); l.y = Math.round(l.y);
      } else {
        let { x, y, w, h: hh } = start;
        if (handle.includes("e")) w = Math.max(4, start.w + dx);
        if (handle.includes("s")) hh = Math.max(4, start.h + dy);
        if (handle.includes("w")) { w = Math.max(4, start.w - dx); x = start.x + start.w - w; }
        if (handle.includes("n")) { hh = Math.max(4, start.h - dy); y = start.y + start.h - hh; }
        if (ev.shiftKey && handle.length === 2) {
          // Keep the shape.
          if (w / hh > ratio) { hh = w / ratio; if (handle.includes("n")) y = start.y + start.h - hh; }
          else { w = hh * ratio; if (handle.includes("w")) x = start.x + start.w - w; }
        }
        Object.assign(l, { x: Math.round(x), y: Math.round(y), w: Math.round(w), h: Math.round(hh) });
      }
      pending = true;
      saveSoon();
      redraw();
      drawSelection(guides);
      syncPropsGeometry();
    };
    const up = () => {
      removeEventListener("mousemove", move);
      removeEventListener("mouseup", up);
      if (moved) changed();
      drawSelection();
    };
    addEventListener("mousemove", move);
    addEventListener("mouseup", up);
  });
  canvas.addEventListener("dblclick", () => {
    const l = layerById(selected);
    if (l && l.type === "text") { const t = document.querySelector("#props textarea[data-k=text]"); if (t) { t.focus(); t.select(); } }
  });

  addEventListener("keydown", e => {
    if (App.tab !== "composer" || !comp || /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
    const l = layerById(selected);
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "z") {
      e.preventDefault();
      const from = e.shiftKey ? redo : undo, to = e.shiftKey ? undo : redo;
      if (from.length) { to.push(JSON.stringify(comp)); restore(from.pop()); }
      return;
    }
    if (mod && e.key.toLowerCase() === "y") { e.preventDefault(); if (redo.length) { undo.push(JSON.stringify(comp)); restore(redo.pop()); } return; }
    if (!l) return;
    const step = e.shiftKey ? 10 : 1;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    if (moves[e.key]) {
      e.preventDefault();
      snapshot();
      l.x += moves[e.key][0]; l.y += moves[e.key][1];
      changed({ keepList: true });
    } else if (e.key === "Delete" || e.key === "Backspace") {
      e.preventDefault();
      snapshot();
      comp.layers = comp.layers.filter(x => x.id !== l.id);
      selected = null;
      changed({ props: true });
    } else if (mod && e.key.toLowerCase() === "d") {
      e.preventDefault();
      duplicateLayer(l);
    } else if (e.key === "Escape") {
      selectLayer(null);
    }
  });
  function duplicateLayer(l) {
    snapshot();
    const copyL = JSON.parse(JSON.stringify(l));
    copyL.id = "l" + Math.random().toString(16).slice(2, 10);
    copyL.name = l.name + " copy";
    copyL.x += 20; copyL.y += 20;
    if (copyL.field) copyL.field = uniqueField(copyL.field);
    comp.layers.splice(comp.layers.indexOf(l) + 1, 0, copyL);
    selected = copyL.id;
    changed({ props: true });
  }
  function uniqueField(name) {
    const taken = new Set(comp.layers.map(l => (l.field || "").toLowerCase()));
    let n = 2, out = name;
    while (taken.has(out.toLowerCase())) out = `${name.replace(/ \d+$/, "")} ${n++}`;
    return out;
  }

  // Playing the animation on the canvas.
  $("#anim-in").addEventListener("click", () => { if (root) { GFX.finish(root); GFX.play(root, "in").then(() => {}); } });
  $("#anim-out").addEventListener("click", () => {
    if (!root) return;
    GFX.finish(root);
    GFX.play(root, "out").then(() => setTimeout(() => root && root.querySelectorAll(".gfx-A").forEach(a => a.getAnimations().forEach(x => x.cancel())), 600));
  });

  // --- properties ----------------------------------------------------------------
  const props = $("#props");
  function fontOptions(current) {
    const assetFonts = (App.state.fonts || []).map(f => f.postscript);
    const all = [...GFX.builtinFonts, ...assetFonts];
    const out = [];
    if (current && !all.includes(current)) out.push(h("option", { value: current, selected: true }, `${current} (not added: stand-in)`));
    out.push(h("optgroup", { label: "Built in" }, GFX.builtinFonts.map(f => h("option", { value: f, selected: f === current }, f))));
    if (assetFonts.length) out.push(h("optgroup", { label: "Added fonts" }, [...new Set(assetFonts)].sort().map(f => h("option", { value: f, selected: f === current }, f))));
    return out;
  }
  function assetSelect(kind, value, onChange) {
    const kinds = kind === "video" ? ["video"] : [kind];
    const list = App.assets.filter(a => kinds.includes(a.kind));
    // Pictures and the loop can follow the global configuration.
    const linked = kind === "image" ? [["{{Global!Left logo}}", "Left team's logo"], ["{{Global!Right logo}}", "Right team's logo"],
      ["{{Global!Tournament logo}}", "Tournament logo"], ["{{Sponsors}}", "Sponsors (in turn)"]]
      : kind === "video" ? [["{{Global!BG loop}}", "Background loop"]] : [];
    const known = list.some(a => a.path === value) || linked.some(([v]) => v === value);
    const sel = h("select", { onchange: e => onChange(e.target.value) },
      h("option", { value: "" }, "(none)"),
      linked.length ? h("optgroup", { label: "Global configuration" }, linked.map(([v, t]) => h("option", { value: v, selected: v === value }, t))) : null,
      h("optgroup", { label: "Files" }, list.map(a => h("option", { value: a.path, selected: a.path === value }, a.path.replace(/^assets\//, "")))),
      value && !known ? h("option", { value, selected: true }, value + " (missing)") : null);
    const file = h("input", { type: "file", hidden: true, accept: kind === "image" ? "image/*" : kind === "video" ? "video/*,.mov,.webm,.zip" : ".json,.zip",
      onchange: async e => {
        const f = e.target.files[0];
        if (!f) return;
        const r = await upload(f);
        if (r && r.assets && r.assets[0]) onChange(r.assets[0]);
        else if (r && r.job) toast("Converting… pick it when it's done");
      } });
    return h("div", { class: "pick" }, sel, h("button", { class: "small", title: "Add a file", onclick: () => file.click() }, "+"), file);
  }

  // An input bound to a layer property.
  function bind(l, key, kind, extra) {
    extra = extra || {};
    const set = v => { snapshot(); l[key] = v; changed({ keepList: key !== "name" && key !== "field" }); };
    let input;
    if (kind === "number") {
      input = h("input", { type: "number", step: extra.step || 1, min: extra.min, max: extra.max, value: l[key] ?? "", "data-k": key,
        onchange: e => set(e.target.value === "" ? 0 : +e.target.value) });
    } else if (kind === "color") {
      input = h("div", { class: "row-gap" },
        h("input", { type: "color", value: /^#[0-9a-f]{6}$/i.test(l[key]) ? l[key] : "#ffffff", oninput: e => { l[key] = e.target.value; e.target.nextSibling.value = e.target.value; changed({ keepList: true }); }, onchange: () => {} }),
        h("input", { value: l[key] || "", "data-k": key, onchange: e => set(e.target.value) }));
    } else if (kind === "check") {
      input = h("label", { class: "toggle" }, h("input", { type: "checkbox", checked: !!l[key], onchange: e => set(e.target.checked) }), extra.label);
    } else if (kind === "select") {
      input = h("select", { "data-k": key, onchange: e => set(extra.num ? +e.target.value : e.target.value) },
        extra.options.map(o => Array.isArray(o) ? h("option", { value: o[0], selected: String(l[key]) === String(o[0]) }, o[1]) : h("option", { value: o, selected: l[key] === o }, o)));
    } else if (kind === "textarea") {
      input = h("textarea", { "data-k": key, rows: 3, oninput: e => { l[key] = e.target.value; pending = true; saveSoon(); redraw(); }, onchange: () => { snapshot(); changed({ keepList: true }); } });
      input.value = l[key] || "";
    } else {
      input = h("input", { value: l[key] ?? "", "data-k": key, placeholder: extra.placeholder || "", onchange: e => set(e.target.value) });
    }
    return extra.label && kind !== "check" ? h("label", {}, extra.label, input) : kind === "check" ? input : input;
  }
  const lab = (text, ...kids) => h("label", {}, text, ...kids);

  function syncPropsGeometry() {
    const l = layerById(selected);
    if (!l) return;
    for (const k of ["x", "y", "w", "h"]) {
      const input = props.querySelector(`input[data-k="${k}"]`);
      if (input && document.activeElement !== input) input.value = Math.round(l[k]);
    }
  }

  function renderProps() {
    if (!comp) { props.replaceChildren(h("div", { class: "empty" }, "Make a graphic with + New, or add a Photoshop file in Assets.")); return; }
    const l = layerById(selected);
    if (!l) return renderCompProps();
    const sections = [];
    sections.push(h("div", { class: "sect" },
      h("h3", {}, { text: "Text", rect: "Shape", image: "Picture", video: "Video", lottie: "Lottie animation" }[l.type] + " layer"),
      lab("Name", bind(l, "name", "text")),
      h("label", { title: "Give it a name to change it from Control (and from data)" }, "Field (changed from Control)",
        h("div", { class: "row-gap" },
          h("input", { value: l.field || "", placeholder: "(fixed: not a field)", "data-k": "field",
            onchange: e => { snapshot(); l.field = e.target.value.trim() ? uniqueFieldExcept(e.target.value.trim(), l) : ""; changed({ props: true }); } }),
          !l.field ? h("button", { class: "small", onclick: () => { snapshot(); l.field = uniqueField(l.name); changed({ props: true }); } }, "Make field") : null)),
      h("div", { class: "grid4" }, lab("X", bind(l, "x", "number")), lab("Y", bind(l, "y", "number")),
        lab("W", bind(l, "w", "number", { min: 1 })), lab("H", bind(l, "h", "number", { min: 1 }))),
      h("div", { class: "grid3" },
        lab("Opacity", bind(l, "opacity", "number", { step: 0.05, min: 0, max: 1 })),
        lab("Rotate °", bind(l, "rotation", "number")),
        lab("Blend", bind(l, "blend", "select", { options: ["normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "plus-lighter"] }))),
      h("div", { class: "row-gap" },
        h("button", { class: "small", onclick: () => duplicateLayer(l) }, "Duplicate"),
        h("button", { class: "small", title: "Full screen", onclick: () => { snapshot(); Object.assign(l, { x: 0, y: 0, w: GFX.W, h: GFX.H }); changed({ props: true }); } }, "Fill"),
        h("button", { class: "small", title: "Centre on the canvas", onclick: () => { snapshot(); l.x = Math.round((GFX.W - l.w) / 2); l.y = Math.round((GFX.H - l.h) / 2); changed({ props: true }); } }, "Centre"),
        h("div", { class: "spacer" }),
        h("button", { class: "small danger", onclick: () => { snapshot(); comp.layers = comp.layers.filter(x => x !== l); selected = null; changed({ props: true }); } }, "Delete"))));

    if (l.type === "text") {
      const missing = !GFX.hasFont(l.font);
      sections.push(h("div", { class: "sect" }, h("h3", {}, "Text"),
        lab("Text", bind(l, "text", "textarea")),
        h("div", { class: "muted small" }, "Use data: {{Source!B2}} · clock: {{time}} · {{countdown:19:30}}"),
        lab("Font", h("select", { onchange: e => { snapshot(); l.font = e.target.value; changed({ props: true }); } }, fontOptions(l.font))),
        missing ? h("div", { class: "warnline" }, `"${l.font}" isn't added: a similar font stands in. Add the font file in Assets.`) : null,
        h("div", { class: "grid3" }, lab("Size", bind(l, "size", "number", { min: 1 })), bind(l, "color", "color", { label: "Colour" }),
          lab("Weight", bind(l, "weight", "select", { num: true, options: [[300, "Light"], [400, "Regular"], [500, "Medium"], [600, "Semibold"], [700, "Bold"], [800, "Extra bold"], [900, "Black"]] }))),
        h("div", { class: "grid3" },
          lab("Align", bind(l, "align", "select", { options: [["left", "Left"], ["center", "Centre"], ["right", "Right"]] })),
          lab("Vertical", bind(l, "valign", "select", { options: [["top", "Top"], ["middle", "Middle"], ["bottom", "Bottom"]] })),
          lab("Too long", bind(l, "fit", "select", { options: [["shrink", "Shrink"], ["squeeze", "Squeeze"], ["none", "Overflow"]] }))),
        h("div", { class: "grid3" },
          lab("Tracking", bind(l, "tracking", "number", { step: 10 })),
          lab("Line height", bind(l, "lineHeight", "number", { step: 0.05, min: 0.5 })),
          lab("Scroll px/s", bind(l, "scroll", "number", { min: 0, step: 10 }))),
        h("div", { class: "row-gap" }, bind(l, "caps", "check", { label: "ALL CAPS" }), bind(l, "italic", "check", { label: "Italic" }),
          bind(l, "shadow", "check", { label: "Shadow" }))));
    } else if (l.type === "rect") {
      sections.push(h("div", { class: "sect" }, h("h3", {}, "Shape"),
        h("div", { class: "grid2" }, bind(l, "fill", "color", { label: "Fill" }), lab("Corner radius", bind(l, "radius", "number", { min: 0 }))),
        h("div", { class: "grid2" }, bind(l, "stroke", "color", { label: "Border" }), lab("Border width", bind(l, "strokeWidth", "number", { min: 0 })))));
    } else {
      sections.push(h("div", { class: "sect" }, h("h3", {}, "Source"),
        lab("File", assetSelect(l.type, l.src, v => { snapshot(); l.src = v; changed({ props: true }); })),
        l.type === "image" && l.src ? h("button", { class: "small", style: { marginTop: "6px" }, onclick: () => naturalSize(l) }, "Actual size") : null,
        lab("Fit", bind(l, "fit", "select", { options: [["contain", "Fit inside"], ["cover", "Fill and crop"], ["fill", "Stretch"]] })),
        /\{\{\s*sponsors\s*\}\}/i.test(l.src || "") ? bind(l, "timer", "check", { label: "Show a bar with the time it has left" }) : null,
        l.type === "image" && /\{\{/.test(l.src || "") ? lab("When Global has none", assetSelect("image", l.placeholder || "", v => { snapshot(); l.placeholder = v; changed({ props: true }); })) : null,
        l.type === "video" ? h("div", { class: "row-gap" },
          bind(l, "tint", "text", { label: "Tint colour (e.g. {{Global!BG loop colour}})", placeholder: "(none)" })) : null,
        l.type !== "image" ? h("div", { class: "row-gap" }, bind(l, "loop", "check", { label: "Loop" }),
          l.type === "video" ? bind(l, "audio", "check", { label: "Sound (Program output)" }) : null) : null));
    }
    sections.push(animSection(l));
    props.replaceChildren(...sections);
  }
  function uniqueFieldExcept(name, layer) {
    const taken = new Set(comp.layers.filter(x => x !== layer).map(x => (x.field || "").toLowerCase()));
    let n = 2, out = name;
    while (taken.has(out.toLowerCase())) out = `${name} ${n++}`;
    return out;
  }
  function naturalSize(l) {
    const img = new Image();
    img.onload = () => { snapshot(); l.w = img.naturalWidth; l.h = img.naturalHeight; changed({ props: true }); };
    img.src = "/" + l.src;
  }

  function animSection(l) {
    l.anim = l.anim || {};
    const row = dir => {
      const a = (l.anim[dir] = l.anim[dir] || { type: "fade", dur: 300, delay: 0 });
      const set = (k, v) => { snapshot(); a[k] = v; changed({ keepList: true }); };
      return h("div", { class: "grid3" },
        lab(dir === "in" ? "In" : "Out", h("select", { onchange: e => set("type", e.target.value) },
          GFX.animTypes.map(t => h("option", { value: t, selected: a.type === t }, t)))),
        lab("ms", h("input", { type: "number", min: 0, step: 50, value: a.dur, onchange: e => set("dur", +e.target.value) })),
        lab("Delay ms", h("input", { type: "number", min: 0, step: 50, value: a.delay || 0, onchange: e => set("delay", +e.target.value) })));
    };
    return h("div", { class: "sect" }, h("h3", {}, "Animation"), row("in"), row("out"),
      h("div", { class: "row-gap", style: { marginTop: "8px" } },
        h("button", { class: "small", onclick: () => { if (root) GFX.play(root, "in"); } }, "▶ Play in")));
  }

  function renderCompProps() {
    const fields = App.fields(comp);
    props.replaceChildren(
      h("div", { class: "sect" }, h("h3", {}, "Graphic"),
        lab("Name", h("input", { value: comp.name, onchange: e => { snapshot(); comp.name = e.target.value || "Graphic"; changed({ props: true }); renderComps(); } })),
        lab("Stacking on the output", h("select", { onchange: e => { snapshot(); comp.layer = +e.target.value; changed(); } },
          [[-1, "Behind others"], [0, "Normal"], [1, "In front"], [2, "Always on top"]].map(([v, t]) => h("option", { value: v, selected: (comp.layer || 0) === v }, t)))),
        h("p", { class: "muted small" }, `${comp.layers.length} layers, ${fields.length} fields. Click a layer to change it.`)),
      h("div", { class: "sect" }, h("h3", {}, "Animation"),
        h("p", { class: "muted small" }, "Every layer has its own In and Out animation. Set them all at once:"),
        h("div", { class: "row-gap" },
          h("button", { class: "small", onclick: () => autoAnimate() }, "Auto (one after another)"),
          h("button", { class: "small", onclick: () => allAnim("fade") }, "All fade"),
          h("button", { class: "small", onclick: () => allAnim("none") }, "None"))),
      h("div", { class: "sect" }, h("h3", {}, "Shortcuts"),
        h("p", { class: "muted small" }, "Drag to move (Shift: straight, Ctrl: no snapping), handles to resize (Shift: keep shape). Arrows nudge (Shift: 10). Ctrl+D duplicates, Delete removes, Ctrl+Z / Ctrl+Shift+Z undo / redo. Alt+click picks the layer underneath.")));
  }
  function allAnim(type) {
    snapshot();
    for (const l of comp.layers) l.anim = { in: { type, dur: 300, delay: 0 }, out: { type: type === "none" ? "none" : "fade", dur: 250, delay: 0 } };
    changed();
  }
  function autoAnimate() {
    snapshot();
    const order = comp.layers.map((l, i) => i).sort((a, b) => Math.floor(comp.layers[a].x / 120) - Math.floor(comp.layers[b].x / 120) || comp.layers[a].y - comp.layers[b].y);
    order.forEach((i, n) => {
      const l = comp.layers[i];
      let type = "fade", delay = 80;
      if (l.w >= GFX.W * 0.9 && l.h >= GFX.H * 0.9) { type = "fade"; delay = 0; }
      else if (l.type === "text") { type = "slide-up"; delay = 150; }
      else if (l.w > l.h * 3) { type = "wipe-right"; delay = 0; }
      else if (l.w < 400 && l.h < 400) type = "scale";
      l.anim = { in: { type, dur: 450, delay: Math.min(700, delay + n * 12) }, out: { type: "fade", dur: 250, delay: 0 } };
    });
    changed();
  }

  App.on((s, what) => {
    renderComps();
    if (what === "assets") { if (selected) renderProps(); return; }
    adopt(false);
  });
  pages.composer = { shown() { fitStage(); adopt(!comp); } };
  window.editGraphic = id => { open(id); showTab("composer"); };
})();
