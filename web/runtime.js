// The GFX Engine player: draws graphics (compositions of layers) and plays
// them in and out, and the transitions between Preview and Program.
//
// Used by the outputs (output.html), the control panel's thumbnails and
// Composer canvas, and exported HTML graphics.
(function () {
  "use strict";
  const GFX = (window.GFX = {});
  const W = 1920, H = 1080;
  GFX.W = W; GFX.H = H;
  GFX.base = "";          // where assets/ and fonts/ are (another engine, for ?live=)

  const url = p => (!p ? "" : /^(https?:|data:|blob:)/.test(p) ? p : GFX.base + (GFX.base && !p.startsWith("/") ? "/" : "") + p);
  GFX.url = url;

  // --- fonts ------------------------------------------------------------------
  // Fonts that come with the engine, and stand-ins for broadcast fonts that
  // can't (Gotham, Trade Gothic...) until their files are added to the assets.
  const BUILTIN = [
    ["Inter", "fonts/Inter.ttf", "100 900"],
    ["Bebas Neue", "fonts/BebasNeue.ttf", "400"],
    ...[400, 500, 700, 800, 900].map(w => ["Montserrat", `fonts/Montserrat-${w}.woff2`, String(w)]),
    ...[500, 600, 700].map(w => ["Barlow Condensed", `fonts/BarlowCondensed-${w}.woff2`, String(w)]),
  ];
  GFX.builtinFonts = ["Inter", "Montserrat", "Barlow Condensed", "Bebas Neue"];
  const STANDINS = [
    [/gotham.*(black|ultra)/i, "Montserrat", 900], [/gotham.*bold/i, "Montserrat", 700],
    [/gotham.*medium/i, "Montserrat", 500], [/gotham/i, "Montserrat", 400],
    [/(trade.?gothic|tradegothic).*(cond|cn|20)/i, "Barlow Condensed", 700], [/trade.?gothic/i, "Barlow Condensed", 600],
    [/redzone|carbon|bebas|impact|anton|oswald/i, "Bebas Neue", 400],
    [/(helvetica|arial|roboto|sf.?pro|segoe).*(black|heavy)/i, "Inter", 900],
    [/(helvetica|arial|roboto|sf.?pro|segoe).*bold/i, "Inter", 700],
  ];
  let assetFonts = new Set();
  let fontStyle = null;
  GFX.loadFonts = function (fonts) {
    fonts = fonts || [];
    const key = JSON.stringify(fonts.map(f => f.path)) + GFX.base;
    if (fontStyle && fontStyle.dataset.key === key) return;
    // Each font by its PostScript name, then by its other names (its file
    // name, full name...), which a design may know it by; the first claim wins.
    const named = new Map();
    for (const f of fonts) if (f.postscript && !named.has(f.postscript.toLowerCase())) named.set(f.postscript.toLowerCase(), [f.postscript, f]);
    for (const f of fonts) for (const a of f.aliases || []) if (a && !named.has(a.toLowerCase())) named.set(a.toLowerCase(), [a, f]);
    assetFonts = new Set([...named.keys()]);
    const css = BUILTIN.map(([fam, file, weight]) =>
      `@font-face{font-family:"${fam}";src:url("${url(file)}");font-weight:${weight};font-display:block}`);
    for (const [name, f] of named.values()) css.push(`@font-face{font-family:"${cssq(name)}";src:url("${url(encodeURI(f.path))}");font-display:block}`);
    if (!fontStyle) { fontStyle = document.createElement("style"); document.head.appendChild(fontStyle); }
    fontStyle.dataset.key = key;
    fontStyle.textContent = css.join("\n");
    if (document.fonts) document.fonts.ready.then(() => GFX.refit());
  };
  const cssq = s => String(s).replace(/["\\]/g, "");
  // [font-family stack, weight] for a text layer.
  GFX.fontFor = function (layer) {
    const name = layer.font || "Inter";
    if (assetFonts.has(name.toLowerCase())) return [`"${cssq(name)}", "Inter", sans-serif`, "normal"];
    if (GFX.builtinFonts.includes(name)) return [`"${name}", "Inter", sans-serif`, layer.weight || 400];
    for (const [re, fam, weight] of STANDINS) if (re.test(name)) return [`"${cssq(name)}", "${fam}", "Inter", sans-serif`, weight];
    return [`"${cssq(name)}", "Inter", sans-serif`, layer.weight || 400];
  };
  GFX.hasFont = name => assetFonts.has(String(name || "").toLowerCase()) || GFX.builtinFonts.includes(name);

  // --- data and fields -----------------------------------------------------------
  const ctx = { tables: {} };
  GFX.setData = function (tables) { ctx.tables = tables || {}; GFX.retext(); tickRotators(); redrawBrackets(); reshow(); };
  // The engine's clock (seconds), so every output changes sponsor at the same moment.
  let clockOffset = 0;
  GFX.setClock = function (engineNow) { if (engineNow) clockOffset = engineNow * 1000 - Date.now(); };
  GFX.now = () => Date.now() + clockOffset;

  const colIndex = s => [...s.toUpperCase()].reduce((n, ch) => n * 26 + ch.charCodeAt(0) - 64, 0) - 1;
  GFX.lookup = function (rows, ref) {
    ref = ref.trim();
    let m = /^([A-Za-z]{1,3})(\d{1,5})$/.exec(ref);
    if (m) { const r = rows[+m[2] - 1]; return (r && r[colIndex(m[1])]) || ""; }
    m = /^(.*)#\s*(\d+)$/.exec(ref);
    if (m && rows.length) {
      const c = rows[0].findIndex(h => h.trim().toLowerCase() === m[1].trim().toLowerCase());
      if (c >= 0) { const r = rows[+m[2]]; return (r && r[c]) || ""; }
    }
    const row = rows.find(r => r[0] && r[0].trim().toLowerCase() === ref.toLowerCase());
    return row ? row[1] || "" : "";
  };
  const pad = n => String(n).padStart(2, "0");
  function token(t) {
    const now = new Date();
    const low = t.toLowerCase();
    if (low === "time") { const h = now.getHours() % 12 || 12; return `${pad(h)}:${pad(now.getMinutes())} ${now.getHours() < 12 ? "AM" : "PM"}`; }
    if (low === "time24") return `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    if (low === "date") return now.toLocaleDateString(undefined, { weekday: "short", month: "numeric", day: "numeric" }).toUpperCase();
    if (low === "clock") {
      // Global's clock: the time of day, or the countdown for Starting Soon / Be Right Back.
      const g = k => GFX.lookup(ctx.tables.Global || [], k);
      const mode = g("Clock mode"), until = g("Clock until");
      if (mode === "soon" || mode === "brb") return until ? token("countdown:" + until) : "00:00";
      return token("time") + (g("Clock zone") ? " " + g("Clock zone") : "");
    }
    let m = /^countdown:\s*(\d{1,2}):(\d{2})$/i.exec(t);
    if (m) {
      // To a time of day (today, or tomorrow if it's gone).
      const target = new Date(now); target.setHours(+m[1], +m[2], 0, 0);
      let s = Math.max(0, Math.round((target - now) / 1000));
      if (target < now && now - target > 12 * 3600e3) { target.setDate(target.getDate() + 1); s = Math.round((target - now) / 1000); }
      const h = Math.floor(s / 3600);
      return (h ? `${h}:${pad(Math.floor(s / 60) % 60)}` : pad(Math.floor(s / 60))) + `:${pad(s % 60)}`;
    }
    m = /^([^!]+)!(.+)$/.exec(t);
    if (m) {
      const name = Object.keys(ctx.tables).find(k => k.toLowerCase() === m[1].trim().toLowerCase());
      return name ? GFX.lookup(ctx.tables[name], m[2]) : "";
    }
    return "{{" + t + "}}";
  }
  GFX.resolve = s => String(s == null ? "" : s).replace(/\{\{\s*([^{}]+?)\s*\}\}/g, (_, t) => token(t));
  const hasTokens = s => /\{\{[^{}]+\}\}/.test(String(s || ""));
  const ticking = s => /\{\{\s*(time|time24|date|clock|countdown:[^}]*)\s*\}\}/i.test(String(s || ""));

  // What a layer shows: its field's value if set, else its own.
  GFX.content = function (layer, values) {
    const v = layer.field && values && values[layer.field] != null && values[layer.field] !== "" ? values[layer.field] : null;
    if (layer.type === "text") return v != null ? String(v) : layer.text || "";
    // (a picture or colour can come from the data too: {{Global!Left logo}})
    const own = v != null ? String(v) : (layer.type === "rect" ? layer.fill : layer.src) || "";
    if (SPONSORS.test(own)) return "{{Sponsors}}";
    // (every sponsor in a row: the list is part of the value, so a new list redraws it)
    if (STRIP.test(own)) return "{{Sponsors all}}" + GFX.sponsors().map(x => "|" + (x.white ? "w:" : "c:") + x.logo).join("");
    const out = hasTokens(own) ? GFX.resolve(own).trim() : own;
    // A picture linked to Global with nothing there yet shows the design's own.
    return !out && layer.placeholder ? layer.placeholder : out;
  };

  // --- the sponsors: one after another, each for its own seconds ---------------
  // A picture layer whose file is {{Sponsors}} shows Global's sponsors in turn.
  const SPONSORS = /^\s*\{\{\s*sponsors\s*\}\}\s*$/i;
  const STRIP = /^\s*\{\{\s*sponsors all\s*\}\}\s*$/i;
  GFX.sponsors = function () {
    return (ctx.tables.Sponsors || []).slice(1).filter(r => r[0])
      .map(r => ({ logo: r[0], secs: Math.max(1, +r[1] || 10), epoch: +r[2] || 0, white: r[3] == null || r[3] === "1" }));
  };
  // {index, left (s), secs, list} of the sponsor on now.
  GFX.sponsorNow = function (list) {
    list = list || GFX.sponsors();
    if (!list.length) return { index: -1, left: 0, secs: 0, list };
    const total = list.reduce((n, s) => n + s.secs, 0);
    let t = ((GFX.now() / 1000 - list[0].epoch) % total + total) % total;
    for (let i = 0; i < list.length; i++) {
      if (t < list[i].secs) return { index: i, left: list[i].secs - t, secs: list[i].secs, list };
      t -= list[i].secs;
    }
    return { index: list.length - 1, left: 0, secs: list[list.length - 1].secs, list };
  };
  const rotators = new Set();
  // A picture layer whose file is {{Sponsors all}}: every sponsor side by side,
  // centred, as tall as the box; each white like the design's unless the sponsor
  // is set to keep its colours (or the layer's "mono" is off).
  function sponsorStrip(layer, logos) {
    const box = el("div", "gfx-media gfx-strip", { gap: Math.round(layer.h * 0.7) + "px" });
    for (const item of logos) {
      const white = item.startsWith("w:") && layer.mono !== false, logo = item.slice(2);
      const img = el("img", "", { height: "100%", maxWidth: Math.round(layer.h * 3.2) + "px", objectFit: "contain",
        filter: white ? "brightness(0) invert(1)" : "" });
      img.src = url(encodeURI(logo));
      box.appendChild(img);
    }
    return box;
  }
  function sponsorBox(layer, opts) {
    const box = el("div", "gfx-media gfx-rot");
    box._layer = layer;
    box._opts = opts;
    if (layer.timer) box.appendChild(el("div", "gfx-rot-bar"));
    rotators.add(box);
    turn(box, true);
    return box;
  }
  function turn(box, first) {
    const layer = box._layer, now = GFX.sponsorNow();
    const logo = now.index >= 0 ? now.list[now.index].logo : layer.placeholder || "";
    const key = now.index + "|" + logo;
    const bar = box.querySelector(".gfx-rot-bar");
    if (bar) bar.style.transform = `scaleX(${now.secs ? Math.max(0, now.left / now.secs) : 0})`;
    if (box._key === key) return;
    box._key = key;
    const img = el("img", "gfx-rot-img", { objectFit: fitOf(layer.fit) });
    img.draggable = false;
    if (logo) img.src = url(encodeURI(logo));
    const old = [...box.querySelectorAll(".gfx-rot-img")];
    box.insertBefore(img, bar || null);
    if (first || box._opts.still || !old.length) { old.forEach(o => o.remove()); return; }
    // The old one lifts away, the new one rises into place.
    for (const o of old) o.animate([{ opacity: 1, transform: "none" }, { opacity: 0, transform: "translateY(-35%) scale(.92)", filter: "blur(4px)" }],
      { duration: 450, easing: EASE_OUT, fill: "forwards" }).finished.then(() => o.remove(), () => o.remove());
    img.animate([{ opacity: 0, transform: "translateY(35%) scale(.92)", filter: "blur(4px)" }, { opacity: 1, transform: "none", filter: "blur(0)" }],
      { duration: 650, delay: 200, easing: EASE, fill: "backwards" });
  }
  function tickRotators() { for (const b of rotators) { if (!b.isConnected && b._seen) rotators.delete(b); else { if (b.isConnected) b._seen = true; turn(b); } } }
  setInterval(tickRotators, 100);

  // --- building graphics -----------------------------------------------------------
  const live = new Set();   // text elements that change with time or data

  function el(tag, cls, style) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (style) Object.assign(e.style, style);
    return e;
  }

  function buildContent(layer, value, opts) {
    const t = layer.type;
    if (t === "image" && value === "{{Sponsors}}") return sponsorBox(layer, opts);
    if (t === "image" && value.startsWith("{{Sponsors all}}")) return sponsorStrip(layer, value.split("|").slice(1));
    if (t === "video" && layer.tint) return tintedVideo(layer, value, opts);
    if (t === "bracket") return bracketBox(layer);
    if (t === "image" && layer.recolor && value) {
      // A one-colour shape in another colour (from Global): the picture as a mask.
      const m = el("div", "gfx-media gfx-recolor");
      const src = `url("${url(encodeURI(value))}")`, size = { fill: "100% 100%", cover: "cover" }[layer.fit] || "contain";
      Object.assign(m.style, { webkitMaskImage: src, maskImage: src, webkitMaskSize: size, maskSize: size,
        webkitMaskRepeat: "no-repeat", maskRepeat: "no-repeat", webkitMaskPosition: "center", maskPosition: "center" });
      return m;
    }
    if (t === "image" && layer.topThird && value) {
      // Only the top third of the picture (a headshot's face), across the box.
      return el("div", "gfx-media", { backgroundImage: `url("${url(encodeURI(value))}")`, backgroundSize: "auto 300%",
        backgroundPosition: "center top", backgroundRepeat: "no-repeat" });
    }
    if (t === "image") {
      if (!value) return el("div");
      const img = el("img", "gfx-media", { objectFit: fitOf(layer.fit), objectPosition: POSITIONS[layer.position] || "" });
      img.draggable = false;
      img.src = url(encodeURI(value));
      if (layer.fit !== "fill" && !/\.(gif|svg)(\?|$)/i.test(value)) img.addEventListener("load", () => smooth(img, layer), { once: true });
      return img;
    }
    if (t === "video") {
      if (!value) return el("div");
      const v = el("video", "gfx-media", { objectFit: fitOf(layer.fit) });
      v.src = url(encodeURI(value));
      v.muted = opts.muted || !layer.audio;
      v.loop = layer.loop !== false;
      v.playsInline = true;
      v.preload = "auto";
      if (opts.still) v.addEventListener("loadeddata", () => { try { v.currentTime = Math.min(1, (v.duration || 2) / 2); } catch (e) { /* not seekable */ } }, { once: true });
      else { v.autoplay = true; v.play().catch(() => { v.muted = true; v.play().catch(() => {}); }); }
      return v;
    }
    return buildOther(layer, value, opts);
  }

  // A video in one colour (the background loop): the video in grey, the colour
  // multiplied over it; the layer's blend (screen) lets the board show through
  // its dark parts. Colour, brightness and speed can come from Global.
  function tintedVideo(layer, value, opts) {
    const box = el("div", "gfx-media gfx-tint");
    if (!value) return box;
    const v = el("video", "gfx-media", { objectFit: "cover",
      filter: `grayscale(1) brightness(${+GFX.resolve(layer.brightness ?? 1.6) || 1.6})` });
    v.src = url(encodeURI(value));
    v.muted = true; v.loop = true; v.playsInline = true; v.preload = "auto";
    const speed = Math.max(0.1, Math.min(4, +GFX.resolve(layer.speed ?? 1) || 1));
    v.addEventListener("loadedmetadata", () => { v.playbackRate = speed; });
    if (opts.still) v.addEventListener("loadeddata", () => { try { v.currentTime = 2; } catch (e) { /* */ } }, { once: true });
    else { v.autoplay = true; v.play().catch(() => {}); }
    // (the colour only once there's a picture to colour: on its own it would fill the box)
    const tint = el("div", "gfx-media", { background: GFX.resolve(layer.tint) || "#ffffff", mixBlendMode: "multiply", visibility: "hidden" });
    v.addEventListener("loadeddata", () => { tint.style.visibility = ""; });
    v.addEventListener("error", () => { v.remove(); tint.remove(); });
    box.append(v, tint);
    return box;
  }

  // --- the knockout bracket: drawn from the "Tournament" data, for 8 or 16
  // teams ({{Tournament!Top teams}}), in the layer's box. The first round's
  // slots are gold, the later ones dark, the champion's outlined; a slot shows
  // the team's logo, name and score, and the team that lost is dimmed.
  const brackets = new Set();
  function bracketBox(layer) {
    const box = el("div", "gfx-media gfx-bracket");
    box._layer = layer;
    brackets.add(box);
    drawBracket(box);
    return box;
  }
  function redrawBrackets() {
    for (const b of brackets) { if (!b.isConnected && b._seen) brackets.delete(b); else { if (b.isConnected) b._seen = true; drawBracket(b); } }
  }
  function drawBracket(box) {
    const layer = box._layer;
    const rows = (ctx.tables.Tournament || []).filter(r => /^Top /.test(r[0] || ""));
    const size = +GFX.lookup(rows, "Top teams") === 16 ? 16 : 8;
    const key = JSON.stringify([rows, layer.w, layer.h, layer.font, layer.color, layer.gold, layer.line]);
    if (box._key === key) return;
    box._key = key;
    box.textContent = "";
    const get = k => GFX.lookup(rows, k);
    const Wd = layer.w, Ht = layer.h, rounds = Math.log2(size);
    const sw = Wd * (size === 16 ? 0.17 : 0.196), cw = Wd * (size === 16 ? 0.25 : 0.278);
    const gap = (Wd - rounds * sw - cw) / rounds;
    const unit = Ht / (size / 2);
    const sh = Math.min(Ht * 0.08, unit * 0.34), g = sh / 6;
    const gold = layer.gold || "#b28a1d", dark = layer.dark || "#000b05", line = layer.line || gold;
    const [family, weight] = GFX.fontFor(layer);
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("width", Wd); svg.setAttribute("height", Ht);
    Object.assign(svg.style, { position: "absolute", left: 0, top: 0, overflow: "visible" });
    box.appendChild(svg);
    const path = d => { const p = document.createElementNS(svgNS, "path"); p.setAttribute("d", d); p.setAttribute("fill", "none");
      p.setAttribute("stroke", line); p.setAttribute("stroke-width", Math.max(2, sh / 18)); svg.appendChild(p); };
    function slot(x, y, w, hgt, team, score, fill, lost, big) {
      const s = el("div", "gfx-bk-slot", { left: x + "px", top: y + "px", width: w + "px", height: hgt + "px", background: fill,
        opacity: lost ? 0.5 : 1, fontFamily: family, fontWeight: weight, color: layer.color || "#ffffff" });
      const name = get(team), logo = get(team + " logo");
      const sq = big ? 0 : hgt * 0.67;
      if (logo) {
        const img = el("img", "gfx-bk-logo", { width: hgt * 0.8 + "px", height: hgt * 0.8 + "px", left: hgt * 0.12 + "px", top: hgt * 0.1 + "px" });
        img.src = url(encodeURI(logo));
        s.appendChild(img);
      }
      const left = logo ? hgt * 1.05 : hgt * 0.25;
      const nameBox = el("div", "gfx-bk-name", { left: left + "px", right: sq + hgt * 0.2 + "px", fontSize: hgt * (big ? 0.42 : 0.6) + "px",
        justifyContent: big ? "center" : "flex-start" });
      nameBox.textContent = name;
      s.appendChild(nameBox);
      if (!big) {
        const sc = el("div", "gfx-bk-score", { width: sq + "px", fontSize: hgt * 0.6 + "px" });
        sc.textContent = get(score);
        s.appendChild(sc);
      }
      box.appendChild(s);
      // (too long: narrower)
      requestAnimationFrame(() => { const k = nameBox.clientWidth / (nameBox.scrollWidth || 1); if (k < 1) nameBox.style.fontSize = parseFloat(nameBox.style.fontSize) * Math.max(0.5, k) + "px"; });
    }
    let centres = [];
    for (let r = 0; r < rounds; r++) {
      const n = size >> (r + 1), x = r * (sw + gap), next = [];
      for (let m = 0; m < n; m++) {
        const cy = r === 0 ? unit * (m + 0.5) : (centres[2 * m] + centres[2 * m + 1]) / 2;
        next.push(cy);
        const k = `Top R${r + 1} M${m + 1}`;
        const winner = get(r + 1 < rounds ? `Top R${r + 2} M${(m >> 1) + 1} team ${(m & 1) + 1}` : "Top champion");
        for (let t = 0; t < 2; t++) {
          const team = `${k} team ${t + 1}`;
          const lost = !!winner && !!get(team) && get(team) !== winner;
          slot(x, t ? cy + g / 2 : cy - g / 2 - sh, sw, sh, team, team + " score", r === 0 ? gold : dark, lost);
        }
        if (r + 1 === rounds) path(`M${x + sw + 4} ${cy}H${x + sw + gap - 4}`);   // (on to the champion)
      }
      if (r + 1 < rounds) {
        // The line on to where the winner goes: the next round's matches sit
        // between the two that feed them.
        for (let m = 0; m < n; m++) {
          const cy = next[m], pair = m >> 1, side = m & 1;
          const ny = (next[2 * pair] + next[2 * pair + 1]) / 2;
          const ty = side ? ny + g / 2 + sh / 2 : ny - g / 2 - sh / 2;
          const x1 = x + sw + 4, x2 = x + sw + gap - 4, xm = (x1 + x2) / 2;
          path(`M${x1} ${cy}H${xm}V${ty}H${x2}`);
        }
      }
      centres = next;
    }
    // The champion.
    const cx = rounds * (sw + gap), ch = sh * 2.4, cy = centres[0];
    const frame = el("div", "gfx-bk-champ", { left: cx + "px", top: cy - ch / 2 + "px", width: cw + "px", height: ch + "px",
      borderColor: layer.champ || "#ffc52a", borderWidth: Math.max(2, sh / 14) + "px" });
    box.appendChild(frame);
    const pad = ch * 0.1;
    slot(cx + pad, cy - ch / 2 + pad, cw - 2 * pad, ch - 2 * pad, "Top champion", "", dark, false, true);
  }

  function buildOther(layer, value, opts) {
    const t = layer.type;
    if (t === "lottie") {
      const box = el("div", "gfx-media");
      if (value && window.lottie) {
        const anim = window.lottie.loadAnimation({ container: box, renderer: "svg", loop: layer.loop !== false,
          autoplay: !opts.still, path: url(encodeURI(value)), rendererSettings: { preserveAspectRatio: layer.fit === "fill" ? "none" : layer.fit === "cover" ? "xMidYMid slice" : "xMidYMid meet" } });
        box._lottie = anim;
        if (opts.still) anim.addEventListener("DOMLoaded", () => anim.goToAndStop(Math.floor(anim.totalFrames / 2), true));
      }
      return box;
    }
    if (t === "rect") {
      return el("div", "gfx-rect", {
        background: value || "transparent", borderRadius: (layer.radius || 0) + "px",
        border: layer.strokeWidth ? `${layer.strokeWidth}px solid ${layer.stroke || "#fff"}` : "none",
      });
    }
    if (t === "text") {
      const box = el("div", "gfx-text");
      const [family, weight] = GFX.fontFor(layer);
      Object.assign(box.style, {
        fontFamily: family, fontWeight: weight, fontStyle: layer.italic ? "italic" : "normal",
        fontSize: layer.size + "px", color: layer.color,
        lineHeight: layer.lineHeight || 1.15, letterSpacing: ((layer.tracking || 0) / 1000) + "em",
        textTransform: layer.caps ? "uppercase" : "none", textAlign: layer.align || "left",
        justifyContent: { left: "flex-start", center: "center", right: "flex-end" }[layer.align || "left"],
        alignItems: { top: "flex-start", middle: "center", bottom: "flex-end" }[layer.valign || "top"],
        textShadow: layer.shadow ? "0 2px 8px rgba(0,0,0,.6)" : "none",
        fontVariant: layer.smallCaps ? "small-caps" : "normal",
      });
      const span = el("span", "gfx-t");
      box.appendChild(span);
      box._layer = layer;
      box._raw = value;
      setText(box, opts);
      if (!opts.still && (hasTokens(value))) live.add(box);
      // Fitted (and put on its baseline) once it's on the page with its real
      // size, and again whenever it's shown after being hidden.
      if (sized) sized.observe(box);
      return box;
    }
    return el("div");
  }
  const fitOf = f => ({ fill: "fill", contain: "contain", cover: "cover" }[f] || "contain");
  // Where a picture sits in its box when it doesn't fill it (a headshot stands on the bottom).
  const POSITIONS = { top: "50% 0%", bottom: "50% 100%", left: "0% 50%", right: "100% 50%" };

  // A big picture in a small box (a team's logo, say) is scaled down by the
  // browser in one step, which looks jagged: it's resampled once, smoothly, to
  // twice the size it's shown at.
  function smooth(img, layer) {
    const nw = img.naturalWidth, nh = img.naturalHeight;
    const k = layer.fit === "cover" ? Math.max(layer.w / nw, layer.h / nh) : Math.min(layer.w / nw, layer.h / nh);
    if (!nw || !nh || k * 2 >= 0.75 || !window.createImageBitmap) return;
    const w = Math.max(1, Math.round(nw * k * 2)), h = Math.max(1, Math.round(nh * k * 2));
    createImageBitmap(img, { resizeWidth: w, resizeHeight: h, resizeQuality: "high" }).then(bmp => {
      const c = document.createElement("canvas");
      c.width = w; c.height = h;
      c.getContext("2d").drawImage(bmp, 0, 0);
      bmp.close && bmp.close();
      c.toBlob(b => {
        if (!b) return;
        const u = URL.createObjectURL(b);
        img.addEventListener("load", () => URL.revokeObjectURL(u), { once: true });
        img.src = u;
      }, "image/png");
    }).catch(() => {});
  }

  function setText(box, opts) {
    const layer = box._layer;
    const text = GFX.resolve(box._raw);
    // A picture before the text (a player's flag), sized to the letters.
    const icon = layer.icon ? GFX.resolve(layer.icon).trim() : "";
    if (box._shown === text + "\u0000" + icon && !opts) return;
    box._shown = text + "\u0000" + icon;
    const span = box.firstChild;
    if (layer.scroll > 0) {
      // A ticker: the text twice in a row, sliding along forever.
      box.classList.add("gfx-scroll");
      span.textContent = "";
      const a = tickerRun(layer, text), b = tickerRun(layer, text);
      span.append(a, b);
      requestAnimationFrame(() => {
        const w = a.offsetWidth || 1;
        span.getAnimations().forEach(x => x.cancel());
        span.animate([{ transform: "translateX(0)" }, { transform: `translateX(${-w}px)` }],
          { duration: (w / layer.scroll) * 1000, iterations: Infinity });
      });
      return;
    }
    span.textContent = text;
    if (icon && text) {
      const img = el("img", "gfx-icon");
      img.src = url(encodeURI(icon));
      img.onload = () => fit(box);
      span.insertBefore(img, span.firstChild);
    }
    fit(box);
  }

  // One run of a ticker's text. With a divider, the "|" between its lines is
  // drawn as a bar in the divider's colour.
  function tickerRun(layer, text) {
    const run = el("span", "gfx-tick");
    if (!layer.divider) { run.textContent = text; return run; }
    const w = layer.dividerWidth || 6, gap = layer.dividerGap ?? Math.round(layer.size * 1.4);
    text.split(/\s*\|\s*/).forEach((part, i, all) => {
      if (part) run.appendChild(document.createTextNode(part));
      if (i < all.length - 1) run.appendChild(el("i", "gfx-div", { width: w + "px", background: layer.divider, margin: `0 ${gap}px` }));
    });
    return run;
  }

  // A layer shown only while its "show" value has something in it (and isn't 0):
  // the Schedule's matches beyond how many it shows, say.
  const showing = layer => { const v = GFX.resolve(layer.show).trim(); return !!v && v !== "0" && v.toLowerCase() !== "false"; };
  function reshow() {
    document.querySelectorAll(".gfx-L").forEach(L => {
      if (L._layer && L._layer.show) L.style.display = showing(L._layer) ? "" : "none";
      if (L._layer) restyle(L);
    });
  }
  // What a layer's look takes from the data as it changes: its colour
  // ({{Global!Caster primary}}) and where it's moved to ("dx dy scale", around
  // layer.origin on the canvas: the caster boxes, spaced out by how many there are).
  function restyle(L) {
    const layer = L._layer;
    if (layer.move) {
      const [dx, dy, sc] = GFX.resolve(layer.move).trim().split(/\s+/).map(Number);
      const o = layer.origin || [layer.x, layer.y];
      L.style.transformOrigin = `${o[0] - layer.x}px ${o[1] - layer.y}px`;
      L.style.transform = `translate(${dx || 0}px, ${dy || 0}px) scale(${sc || 1})` + (layer.rotation ? ` rotate(${layer.rotation}deg)` : "");
    }
    if (layer.recolor) { const m = L.querySelector(".gfx-recolor"); if (m) m.style.background = GFX.resolve(layer.recolor) || "#ffffff"; }
    if (layer.type === "text" && hasTokens(layer.color)) { const b = L.querySelector(".gfx-text"); if (b) b.style.color = GFX.resolve(layer.color); }
  }

  // Text from a Photoshop file sits on its baseline where Photoshop put it,
  // whatever the font's own spacing above the letters.
  function baseline(box) {
    const layer = box._layer, span = box.firstChild;
    if (!layer || !span || layer.baseline == null || layer.scroll > 0 || (layer.valign || "top") !== "top") return;
    span.style.marginTop = "";
    let mark = span.querySelector(":scope > .gfx-bl");
    if (!mark) { mark = el("i", "gfx-bl"); }
    span.insertBefore(mark, span.firstChild);
    if (!box.isConnected || !box.offsetHeight) return;
    span.style.marginTop = (layer.baseline - mark.offsetTop) + "px";
  }

  // Text that doesn't fit its box: made smaller ("shrink") or narrower ("squeeze").
  function fit(box) {
    fitSize(box);
    baseline(box);
  }
  function fitSize(box) {
    const layer = box._layer, span = box.firstChild;
    if (!layer || !span || layer.scroll > 0) return;
    span.style.transform = "";
    box.style.fontSize = layer.size + "px";
    if (!layer.fit || layer.fit === "none") return;
    const bw = box.clientWidth, bh = box.clientHeight;
    const sw = span.scrollWidth, sh = span.scrollHeight;
    if (!bw || !sw) return;
    if (layer.fit === "squeeze") {
      if (sw > bw) {
        span.style.transform = `scaleX(${bw / sw})`;
        span.style.transformOrigin = { left: "0 50%", center: "50% 50%", right: "100% 50%" }[layer.align || "left"];
      }
      return;
    }
    const k = Math.min(1, bw / sw, sh > bh * 1.05 ? bh / sh : 1);
    if (k < 1) box.style.fontSize = Math.max(layer.size * 0.25, layer.size * k * 0.99) + "px";
  }
  GFX.refit = () => document.querySelectorAll(".gfx-text").forEach(fit);
  const sized = window.ResizeObserver ? new ResizeObserver(entries => {
    for (const e of entries) if (e.contentRect.width && e.target.isConnected) fit(e.target);
  }) : null;
  // A font that finishes loading after the text was fitted: fitted again.
  if (document.fonts && document.fonts.addEventListener) document.fonts.addEventListener("loadingdone", () => GFX.refit());
  GFX.retext = () => document.querySelectorAll(".gfx-text").forEach(b => { if (hasTokens(b._raw) || hasTokens(b._layer && b._layer.icon)) setText(b); });
  setInterval(() => { for (const b of live) { if (!b.isConnected) live.delete(b); else if (ticking(b._raw)) setText(b); } }, 1000);

  // What else a layer's look takes from the data (a tinted loop's colour...).
  const extraOf = layer => layer.tint ? [layer.tint, layer.brightness, layer.speed].map(v => GFX.resolve(v ?? "")).join("|") : "";

  function buildLayer(layer, values, opts) {
    const value = GFX.content(layer, values);
    const outer = el("div", "gfx-L", {
      left: layer.x + "px", top: layer.y + "px", width: layer.w + "px", height: layer.h + "px",
      opacity: layer.opacity == null ? 1 : layer.opacity,
      transform: layer.rotation ? `rotate(${layer.rotation}deg)` : "",
      mixBlendMode: layer.blend && layer.blend !== "normal" ? layer.blend : "",
    });
    outer.dataset.id = layer.id;
    if (layer.show && !opts.showHidden && !showing(layer)) outer.style.display = "none";
    const inner = el("div", "gfx-A");
    inner.appendChild(buildContent(layer, value, opts));
    outer.appendChild(inner);
    outer._value = value;
    outer._extra = extraOf(layer);
    outer._layer = layer;
    outer._sig = JSON.stringify(layer);
    if (layer.move || layer.recolor || hasTokens(layer.color)) restyle(outer);
    return outer;
  }

  // A graphic's element. opts: {still: no playing media (thumbnails),
  // muted, showHidden: include hidden layers (Composer)}.
  GFX.buildComp = function (comp, values, opts) {
    opts = opts || {};
    const root = el("div", "gfx-comp");
    root.dataset.comp = comp.id;
    root.style.zIndex = 10 + (comp.layer || 0);
    for (const layer of comp.layers || []) {
      if (layer.visible === false && !opts.showHidden) continue;
      const L = buildLayer(layer, values, opts);
      if (layer.visible === false) L.style.visibility = "hidden";
      root.appendChild(L);
    }
    root._comp = comp;
    root._values = values;
    root._opts = opts;
    return root;
  };

  // New values (or an edited graphic) for a graphic already showing:
  // only the layers that change are rebuilt.
  GFX.updateComp = function (root, comp, values) {
    const opts = root._opts || {};
    const existing = new Map([...root.children].map(c => [c.dataset.id, c]));
    const wanted = (comp.layers || []).filter(l => l.visible !== false || opts.showHidden);
    let prev = null;
    for (const layer of wanted) {
      let L = existing.get(layer.id);
      const value = GFX.content(layer, values);
      if (!L || L._sig !== JSON.stringify(layer) || L._value !== value || L._extra !== extraOf(layer)) {
        const fresh = buildLayer(layer, values, opts);
        if (layer.visible === false) fresh.style.visibility = "hidden";
        if (L) { destroy(L); L.replaceWith(fresh); } else root.insertBefore(fresh, prev ? prev.nextSibling : root.firstChild);
        L = fresh;
      } else if (L.previousSibling !== prev && prev !== L) {
        root.insertBefore(L, prev ? prev.nextSibling : root.firstChild);
      }
      existing.delete(layer.id);
      prev = L;
    }
    for (const L of existing.values()) { destroy(L); L.remove(); }
    root._comp = comp;
    root._values = values;
    root.style.zIndex = 10 + (comp.layer || 0);
  };

  function destroy(node) {
    node.querySelectorAll(".gfx-media").forEach(m => {
      if (m._lottie) m._lottie.destroy();
      if (m.tagName === "VIDEO") { m.pause(); m.removeAttribute("src"); m.load(); }
    });
  }
  GFX.destroy = destroy;

  // --- animation -----------------------------------------------------------
  const EASE = "cubic-bezier(.2,.8,.2,1)";
  const EASE_OUT = "cubic-bezier(.6,0,.8,.3)";
  // Keyframes for an animation coming in (reversed for going out).
  function frames(type, layer) {
    const d = Math.max(40, Math.min(240, (layer.w || 300) * 0.15));
    const dv = Math.max(30, Math.min(160, (layer.h || 100) * 0.5));
    switch (type) {
      case "fade": return [{ opacity: 0 }, { opacity: 1 }];
      case "slide-left": return [{ opacity: 0, transform: `translateX(${d}px)` }, { opacity: 1, transform: "none" }];
      case "slide-right": return [{ opacity: 0, transform: `translateX(${-d}px)` }, { opacity: 1, transform: "none" }];
      case "slide-up": return [{ opacity: 0, transform: `translateY(${dv}px)` }, { opacity: 1, transform: "none" }];
      case "slide-down": return [{ opacity: 0, transform: `translateY(${-dv}px)` }, { opacity: 1, transform: "none" }];
      case "wipe-right": return [{ clipPath: "inset(0 100% 0 0)" }, { clipPath: "inset(0 0 0 0)" }];
      case "wipe-left": return [{ clipPath: "inset(0 0 0 100%)" }, { clipPath: "inset(0 0 0 0)" }];
      case "wipe-down": return [{ clipPath: "inset(0 0 100% 0)" }, { clipPath: "inset(0 0 0 0)" }];
      case "wipe-up": return [{ clipPath: "inset(100% 0 0 0)" }, { clipPath: "inset(0 0 0 0)" }];
      case "grow-x": return [{ transform: "scaleX(0)", transformOrigin: "0 50%" }, { transform: "scaleX(1)", transformOrigin: "0 50%" }];
      case "grow-y": return [{ transform: "scaleY(0)", transformOrigin: "50% 100%" }, { transform: "scaleY(1)", transformOrigin: "50% 100%" }];
      case "scale": return [{ opacity: 0, transform: "scale(.85)" }, { opacity: 1, transform: "none" }];
      case "pop": return [{ opacity: 0, transform: "scale(.6)" }, { opacity: 1, transform: "scale(1.06)", offset: .7 }, { opacity: 1, transform: "none" }];
      case "blur": return [{ opacity: 0, filter: "blur(20px)" }, { opacity: 1, filter: "blur(0)" }];
      default: return null;
    }
  }
  GFX.animTypes = ["none", "fade", "slide-left", "slide-right", "slide-up", "slide-down", "wipe-right", "wipe-left",
    "wipe-down", "wipe-up", "grow-x", "grow-y", "scale", "pop", "blur"];

  // Plays a graphic's layers in (or out). Resolves when done.
  GFX.play = function (root, dir) {
    const runs = [];
    for (const L of root.children) {
      const layer = L._layer;
      const a = (layer && layer.anim && layer.anim[dir]) || { type: "fade", dur: 300, delay: 0 };
      const f = frames(a.type, layer || {});
      const inner = L.firstChild;
      if (!f || !inner) { if (dir === "out") inner && (inner.style.opacity = 0); continue; }
      const anim = inner.animate(dir === "in" ? f : f.slice().reverse(), {
        duration: Math.max(1, +a.dur || 300), delay: Math.max(0, +a.delay || 0),
        easing: a.ease || (dir === "in" ? EASE : EASE_OUT), fill: "both" });
      runs.push(anim.finished.catch(() => {}));
    }
    return Promise.all(runs);
  };
  GFX.finish = root => root.querySelectorAll(".gfx-A").forEach(a => a.getAnimations().forEach(x => { try { x.finish(); } catch (e) { x.cancel(); } }));

  // --- a bus: the graphics on Program or Preview, kept in step with the engine --
  //
  // opts: {bus: "program" | "preview", comp: one graphic only, monitor: muted,
  //        stingers: play stinger videos (default: yes, except one-graphic outputs)}
  const KIND_RANK = { board: 0, overlay: 1, "lower third": 2 };
  GFX.Bus = class Bus {
    constructor(stage, opts) {
      this.stage = stage;
      this.opts = Object.assign({ bus: "program" }, opts || {});
      this.scene = el("div", "gfx-scene");
      stage.appendChild(this.scene);
      this.shown = new Map();     // comp id -> element
      this.leaving = new Set();
      this.seen = null;            // {rev, take, seq}
      this.stingers = new Map();   // src -> <video>, ready to go
      this.cleanup = [];
    }

    // A graphic's own output that's switched on (Outputs) always shows it,
    // with what it shows on Program (or else on Preview); switched off, nothing.
    always(state) {
      return !!this.opts.comp && ((state.global || {}).outputs_on || []).includes(this.opts.comp);
    }

    wanted(state) {
      const bus = state.live[this.opts.bus] || { on: [], values: {} };
      let on = bus.on || [];
      const comps = new Map(state.project.compositions.map(c => [c.id, c]));
      if (this.opts.comp) {
        const id = this.opts.comp, pg = state.live.program || {}, pv = state.live.preview || {};
        const values = (pg.values || {})[id] || (pv.values || {})[id] || {};
        return { ids: this.always(state) && comps.has(id) ? [id] : [], comps, values: { [id]: values } };
      }
      return { ids: on.filter(id => comps.has(id)), comps, values: bus.values || {} };
    }

    apply(state) {
      GFX.loadFonts(state.fonts);
      this.preload(state.project.transitions || []);
      const want = this.wanted(state);
      const bus = state.live[this.opts.bus] || {};
      const take = (state.live.take || {}).seq || 0;
      const first = !this.seen;
      const tookNow = !first && this.opts.bus === "program" && take !== this.seen.take;
      const t = (state.live.take || {}).transition || { type: "cut" };
      this.seen = { rev: state.rev, take, seq: bus.seq };
      if (tookNow) {
        // (one graphic's own output doesn't follow takes: it's on while switched on)
        if (!this.opts.comp) return this.transition(want, t);
      }
      return this.sync(want, first ? "cut" : this.opts.bus === "preview" ? "cut" : "update");
    }

    // Shows exactly `want`: new graphics in (with mode's effect), gone ones out,
    // the rest updated in place.
    sync(want, mode, t) {
      t = t || {};
      const ids = new Set(want.ids);
      for (const [id, root] of this.shown) {
        if (!ids.has(id)) {
          this.shown.delete(id);
          this.out(root, mode, t);
        } else {
          GFX.updateComp(root, want.comps.get(id), want.values[id] || {});
        }
      }
      for (const id of want.ids) {
        if (this.shown.has(id)) continue;
        const root = GFX.buildComp(want.comps.get(id), want.values[id] || {}, { muted: this.opts.monitor });
        this.scene.appendChild(root);
        this.shown.set(id, root);
        this.in(root, mode, t);
      }
      // Stacking: the graphic's "layer" setting, then its kind (full-page
      // boards at the back, overlays over them, lower thirds in front), then
      // its place in the list.
      want.ids.forEach((id, i) => {
        const root = this.shown.get(id), comp = want.comps.get(id);
        if (root) root.style.zIndex = 10 + (comp.layer || 0) * 1000 + (KIND_RANK[comp.kind] ?? 1) * 300 + i;
      });
    }

    in(root, mode, t) {
      if (mode === "animate") GFX.play(root, "in");
      else if (mode === "fade") root.animate([{ opacity: 0 }, { opacity: 1 }], { duration: t.dur || 500, easing: "linear" });
      else if (mode === "wipe") root.animate(wipe(t.direction, true), { duration: t.dur || 600, easing: EASE });
      requestAnimationFrame(() => root.querySelectorAll(".gfx-text").forEach(fit));
    }

    out(root, mode, t) {
      let done;
      this.leaving.add(root);
      if (mode === "animate") done = GFX.play(root, "out");
      else if (mode === "fade") done = root.animate([{ opacity: 1 }, { opacity: 0 }], { duration: t.dur || 500, easing: "linear", fill: "forwards" }).finished;
      else if (mode === "wipe") done = root.animate(wipe(t.direction, false), { duration: t.dur || 600, easing: EASE, fill: "forwards" }).finished;
      else done = Promise.resolve();
      done.catch(() => {}).then(() => { this.leaving.delete(root); destroy(root); root.remove(); });
    }

    // Ends whatever transition is still playing, at once.
    hurry() {
      for (const fn of this.cleanup.splice(0)) fn();
      for (const root of this.leaving) { destroy(root); root.remove(); }
      this.leaving.clear();
      for (const root of this.shown.values()) { root.getAnimations().forEach(a => a.finish()); GFX.finish(root); }
    }

    transition(want, t) {
      this.hurry();
      switch (t.type) {
        case "cut": return this.sync(want, "cut");
        case "fade": return this.sync(want, "fade", t);
        case "wipe": return this.sync(want, "wipe", t);
        case "animate": return this.sync(want, "animate", t);
        case "dip": {
          const cover = el("div", "gfx-cover", { background: t.color || "#000", opacity: 0 });
          this.stage.appendChild(cover);
          const half = (t.dur || 800) / 2;
          const a = cover.animate([{ opacity: 0 }, { opacity: 1 }], { duration: half, fill: "forwards" });
          const end = () => { cover.remove(); };
          this.cleanup.push(() => { this.sync(want, "cut"); end(); });
          a.finished.then(() => {
            this.cleanup = this.cleanup.filter(f => f !== end);
            this.sync(want, "cut");
            cover.animate([{ opacity: 1 }, { opacity: 0 }], { duration: half, fill: "forwards" }).finished.then(end, end);
          }, () => {});
          return;
        }
        case "stinger": return this.stinger(want, t);
        case "delay": {
          const timer = setTimeout(() => this.sync(want, "cut"), t.ms || 0);
          this.cleanup.push(() => { clearTimeout(timer); this.sync(want, "cut"); });
          return;
        }
        default: return this.sync(want, "cut");
      }
    }

    stinger(want, t) {
      if (!t.src) return this.sync(want, "cut");
      const v = this.stingerVideo(t.src);
      v.muted = !!this.opts.monitor || t.audio === false;
      v.volume = t.volume == null ? 1 : +t.volume;
      v.currentTime = 0;
      v.style.visibility = "visible";
      let swapped = false;
      const swap = () => { if (!swapped) { swapped = true; this.sync(want, "cut"); } };
      const cutAt = Math.max(0, +t.cut || 0) / 1000;
      const hide = () => { v.pause(); v.style.visibility = "hidden"; v.removeEventListener("timeupdate", tick); };
      const tick = () => { if (v.currentTime >= cutAt) swap(); };
      // timeupdate fires only ~4 times a second: a timer catches the cut on time.
      const timer = setTimeout(swap, cutAt * 1000 + 30);
      v.addEventListener("timeupdate", tick);
      v.onended = () => { swap(); hide(); };
      this.cleanup.push(() => { clearTimeout(timer); swap(); hide(); });
      const started = v.play();
      if (started) started.catch(() => { v.muted = true; v.play().catch(() => { clearTimeout(timer); swap(); hide(); }); });
    }

    stingerVideo(src) {
      let v = this.stingers.get(src);
      if (!v) {
        v = el("video", "gfx-stinger");
        v.src = url(encodeURI(src));
        v.preload = "auto";
        v.playsInline = true;
        v.muted = true;
        this.stage.appendChild(v);
        this.stingers.set(src, v);
      }
      return v;
    }

    // Stinger videos load before they're needed, so they start on the button.
    preload(transitions) {
      if (this.opts.bus !== "program" || (this.opts.comp && !this.opts.stingers)) return;
      for (const t of transitions) if (t.type === "stinger" && t.src && t.enabled !== false) this.stingerVideo(t.src);
    }
  };

  function wipe(direction, entering) {
    const from = { left: "inset(0 0 0 100%)", right: "inset(0 100% 0 0)", up: "inset(100% 0 0 0)", down: "inset(0 0 100% 0)" }[direction || "left"];
    const to = { left: "inset(0 100% 0 0)", right: "inset(0 0 0 100%)", up: "inset(0 0 100% 0)", down: "inset(100% 0 0 0)" }[direction || "left"];
    return entering ? [{ clipPath: from }, { clipPath: "inset(0 0 0 0)" }] : [{ clipPath: "inset(0 0 0 0)" }, { clipPath: to }];
  }

  // --- styles ---------------------------------------------------------------
  const css = document.createElement("style");
  css.textContent = `
    .gfx-stage{position:relative;width:${W}px;height:${H}px;overflow:hidden}
    .gfx-scene,.gfx-comp{position:absolute;inset:0;pointer-events:none}
    .gfx-L{position:absolute;box-sizing:border-box}
    .gfx-A{position:absolute;inset:0}
    .gfx-media{position:absolute;inset:0;width:100%;height:100%;display:block}
    .gfx-rect{position:absolute;inset:0;box-sizing:border-box}
    .gfx-text{position:absolute;inset:0;display:flex;white-space:pre;overflow:visible}
    .gfx-t{display:inline-block;max-width:none}
    .gfx-scroll{overflow:hidden}
    .gfx-scroll .gfx-t{display:flex;white-space:pre}
    .gfx-tick{display:inline-flex;align-items:center}
    .gfx-media.gfx-strip{display:flex;align-items:center;justify-content:center}
    .gfx-strip img{min-width:0;flex:0 1 auto}
    .gfx-icon{display:inline-block;height:.72em;width:auto;margin-right:.32em;vertical-align:baseline;border-radius:.06em}
    .gfx-div{display:inline-block;height:1.05em;flex:0 0 auto}
    .gfx-tick{padding-right:1.5em}
    .gfx-bl{display:inline-block;width:0;height:0;vertical-align:baseline}
    .gfx-rot{overflow:visible}
    .gfx-rot-img{position:absolute;inset:0;width:100%;height:100%;display:block}
    .gfx-rot-bar{position:absolute;left:0;right:0;bottom:-8px;height:3px;background:currentColor;color:#f5c518;transform-origin:0 50%;opacity:.85}
    .gfx-bracket{overflow:visible}
    .gfx-bk-slot{position:absolute;box-sizing:border-box;overflow:hidden;transition:opacity .4s}
    .gfx-bk-logo{position:absolute;object-fit:contain}
    .gfx-bk-name{position:absolute;top:0;bottom:0;display:flex;align-items:center;white-space:nowrap;text-transform:uppercase;letter-spacing:-.01em;overflow:hidden}
    .gfx-bk-score{position:absolute;right:0;top:0;bottom:0;background:#000;display:flex;align-items:center;justify-content:center}
    .gfx-bk-champ{position:absolute;box-sizing:border-box;border-style:solid}
    .gfx-cover{position:absolute;inset:0;z-index:9000}
    .gfx-stinger{position:absolute;inset:0;width:100%;height:100%;z-index:9500;visibility:hidden;object-fit:cover;pointer-events:none}
  `;
  document.head.appendChild(css);
})();
