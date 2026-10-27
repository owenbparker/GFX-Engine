// The Camera Control Room: every player's cam at once, each one's camera
// set from here (white balance, exposure, gain, zoom...).
//
// The cams are the SCC Player Cam app on the players' PCs, connected to the
// League / VALORANT HUD. This page talks to each HUD's cam hub like the HUD's
// own overlay does: it gets each cam's picture peer to peer (WebRTC, small),
// and sends the cam {type: "camctl"} messages; Player Cam sets its camera
// and answers with what the camera has and is set to ("camstate"). The cams
// keep their settings (on their own PC), so this page holds none of them,
// apart from the saved lighting looks (settings camera_looks).
"use strict";

(function cameras() {
  const ME = "ccr" + Math.random().toString(16).slice(2, 15);
  const PORTS = { lol: 8777, valorant: 8778 };
  const GAME_NAMES = { lol: "League HUD", valorant: "VALORANT HUD" };
  const hubs = {};   // HUD address -> { base, game, note, polling }
  const cams = {};   // "address|id" -> { hub, id, info, pc, video, tile, state, asked }
  let selected = null, active = false, listTimer = 0;

  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const isLocal = host => /^(127\.|localhost$|::1$)/.test(host || "");
  async function hubPost(base, path, body) {
    const r = await fetch(base + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await r.json().catch(() => null);
    if (!r.ok || !data || data.error) throw new Error((data && data.error) || r.status);
    return data;
  }
  const savedAddresses = () => { try { return JSON.parse(localStorage.getItem("ccr-huds") || "[]"); } catch (e) { return []; } };

  // The HUDs: the ones connected to this engine, and any added by hand.
  function hudBases() {
    const out = {};
    const feeds = (App.state && App.state.data && App.state.data.feeds) || {};
    for (const [name, f] of Object.entries(feeds)) {
      if (!PORTS[f.game] || f.age > 30) continue;
      const host = isLocal(f.from) ? location.hostname : f.from;
      out[`http://${host}:${PORTS[f.game]}`] = name;
    }
    for (const a of savedAddresses()) out[a] = out[a] || a.replace(/^https?:\/\//, "");
    return out;
  }

  // --- talking to each HUD's cam hub ---------------------------------------------
  async function pollHub(hub) {
    let registered = false;
    while (active && hubs[hub.base] === hub) {
      try {
        const r = await hubPost(hub.base, "/api/cam/poll", { id: ME, wait: registered ? 20 : 0 });
        registered = true;
        for (const m of r.messages || []) {
          const cam = cams[`${hub.base}|${m.from}`];
          if (!cam) continue;
          if (m.type === "answer" && cam.pc && cam.pc.signalingState === "have-local-offer")
            await cam.pc.setRemoteDescription({ type: "answer", sdp: unhide(m.sdp, m.ip, new URL(hub.base).hostname) }).catch(() => dropVideo(cam));
          else if (m.type === "camstate") { cam.state = m; drawTile(cam); if (selected === cam.key) drawSide(); }
          else if (m.type === "bye") dropVideo(cam);
        }
      } catch (e) { registered = false; await sleep(2000); }
    }
  }

  function send(cam, data) {
    return hubPost(cam.hub.base, "/api/cam/send", { to: cam.id, from: ME, data }).catch(() => {});
  }

  async function listAll() {
    const bases = hudBases();
    for (const base of Object.keys(hubs)) if (!bases[base]) dropHub(base);
    const seen = new Set();
    await Promise.all(Object.entries(bases).map(async ([base, name]) => {
      let hub = hubs[base];
      if (!hub) {
        hub = hubs[base] = { base, name, game: "", note: "" };
        pollHub(hub);
      }
      try {
        const r = await hubPost(base, "/api/cam/list", {});
        hub.game = r.game || hub.game;
        hub.name = GAME_NAMES[hub.game] || name;
        hub.note = "";
        for (const c of r.cams || []) {
          const key = `${base}|${c.id}`;
          seen.add(key);
          const cam = cams[key] || (cams[key] = { key, hub, id: c.id, asked: 0 });
          cam.info = c;
          const stuck = cam.pc && cam.pc.connectionState !== "connected" && Date.now() - cam.started > 10000;
          if (stuck) dropVideo(cam);
          if (!cam.pc) connect(cam);
          if (!cam.state && Date.now() - cam.asked > 4000) { cam.asked = Date.now(); send(cam, { type: "camctl", get: true }); }
        }
      } catch (e) {
        hub.note = /not found|null|403/i.test(e.message) ? `${name}: update it for the Camera Control Room` : `${name}: can't reach it at ${base}`;
        for (const key of Object.keys(cams)) if (cams[key].hub === hub) seen.add(key);   // (keep them through a blip)
      }
    }));
    for (const key of Object.keys(cams)) if (!seen.has(key)) dropCam(key);
    drawGrid();
  }

  function dropHub(base) {
    for (const key of Object.keys(cams)) if (cams[key].hub.base === base) dropCam(key);
    delete hubs[base];
  }
  function dropVideo(cam) {
    if (cam.pc) { try { cam.pc.close(); } catch (e) { /* closed */ } }
    cam.pc = null;
  }
  function dropCam(key) {
    const cam = cams[key];
    if (!cam) return;
    dropVideo(cam);
    send(cam, { type: "bye" });
    if (cam.tile) cam.tile.remove();
    delete cams[key];
    if (selected === key) { selected = null; drawSide(); }
  }

  function gathered(pc) {
    if (pc.iceGatheringState === "complete") return Promise.resolve();
    return new Promise(resolve => {
      pc.addEventListener("icegatheringstatechange", () => { if (pc.iceGatheringState === "complete") resolve(); });
      setTimeout(resolve, 2500);
    });
  }
  // WebRTC hides each PC's address behind a random "<id>.local" name, which only
  // resolves on that PC's own network: a cam on another network (VLAN) never
  // connects. The HUD passes on where each message came from (m.ip), and that
  // address goes in place of the hidden one.
  function unhide(sdp, ip, hubHost) {
    if (ip && /^(127\.|::1$|::ffff:127\.)/.test(ip)) ip = /^localhost$/i.test(hubHost) ? "127.0.0.1" : hubHost;
    if (!sdp || !ip || !/^\d+\.\d+\.\d+\.\d+$/.test(ip)) return sdp;
    return sdp.replace(/^(a=candidate:\S+ \d+ \S+ \d+ )\S+\.local( \d+ typ host)/gm, `$1${ip}$2`);
  }

  async function connect(cam) {
    const pc = cam.pc = new RTCPeerConnection({ iceServers: [] });
    cam.started = Date.now();
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = e => {
      const v = tile(cam).querySelector("video");
      v.srcObject = e.streams[0] || new MediaStream([e.track]);
      v.play().catch(() => {});
    };
    pc.onconnectionstatechange = () => {
      if (["failed", "closed"].includes(pc.connectionState) && cam.pc === pc) cam.pc = null;   // (again on the next listing)
      drawTile(cam);
    };
    try {
      await pc.setLocalDescription(await pc.createOffer());
      await gathered(pc);
      // preview: Player Cam sends this page a smaller picture than the HUD's.
      await send(cam, { type: "offer", sdp: pc.localDescription.sdp, preview: true });
    } catch (e) { dropVideo(cam); }
  }

  function start() {
    if (active) return;
    active = true;
    listAll();
    listTimer = setInterval(listAll, 3000);
  }
  function stop() {
    if (!active) return;
    active = false;
    clearInterval(listTimer);
    for (const base of Object.keys(hubs)) dropHub(base);
    drawGrid();
  }
  // Only while the page is open (the cams send their pictures to it).
  setInterval(() => (App.tab === "cameras" && !document.hidden ? start() : stop()), 1000);

  // --- the grid -------------------------------------------------------------------
  const camName = cam => {
    const i = cam.info || {};
    return [i.team, i.name].filter(Boolean).join(" ") || "Player cam";
  };
  const camModel = cam => ((cam.state && cam.state.label) || (cam.info && cam.info.label) || "").replace(/\s*\([0-9a-f]{4}:[0-9a-f]{4}\)\s*$/i, "");

  function tile(cam) {
    if (!cam.tile) {
      cam.tile = h("button", { class: "cr-cam", onclick: () => { selected = cam.key; drawGrid(); drawSide(); } },
        h("video", { autoplay: true, muted: true, playsInline: true }),
        h("div", { class: "cr-cam-info" }, h("b", {}), h("span", { class: "muted" })),
        h("span", { class: "cr-badge" }));
    }
    return cam.tile;
  }
  function drawTile(cam) {
    const t = tile(cam);
    t.classList.toggle("sel", selected === cam.key);
    t.querySelector("b").textContent = camName(cam);
    t.querySelector(".cr-cam-info span").textContent = camModel(cam);
    const live = cam.pc && cam.pc.connectionState === "connected";
    const badge = t.querySelector(".cr-badge");
    badge.textContent = !live ? "Connecting…" : !cam.state && Date.now() - cam.asked > 3000 ? "Update Player Cam" : "";
    badge.hidden = !badge.textContent;
  }
  // "VALORANT HUD (192.168.2.40)": the HUDs this page is getting the cams from.
  const watching = () => Object.values(hubs).map(x => `${x.name} (${x.base.replace(/^https?:\/\/|:\d+$/g, "")})`).join(", ");
  function drawGrid() {
    const grid = $("#cr-grid");
    const list = Object.values(cams).sort((a, b) => (a.hub.name + (a.info.seat || "") + camName(a)).localeCompare(b.hub.name + (b.info.seat || "") + camName(b)));
    const notes = Object.values(hubs).map(x => x.note).filter(Boolean);
    $("#cr-note").textContent = notes.join(" · ") || (!Object.keys(hubs).length
      ? "No League or VALORANT HUD is connected to this engine. Connect one (its GFX Engine page), or add its address."
      : `${watching()}: ` + (list.length ? `${list.length} cam${list.length === 1 ? "" : "s"}`
        : "no player cams connected to it yet (players open SCC Player Cam and press Connect to HUD)."));
    for (const cam of list) { drawTile(cam); if (cam.tile.parentNode !== grid || grid.children[list.indexOf(cam)] !== cam.tile) grid.insertBefore(cam.tile, grid.children[list.indexOf(cam)] || null); }
    for (const el of [...grid.children]) if (!list.some(c => c.tile === el)) el.remove();
    if (selected && !cams[selected]) selected = null;
    if (!selected && list.length) { selected = list[0].key; drawSide(); }
  }

  // --- one cam's settings ---------------------------------------------------------
  // What's changed here is sent every 120 ms while a slider's dragged, and
  // shown as set for a moment after (the cam's answers can lag behind).
  const HOLD = 1500;
  function change(cam, key, want) {
    cam.pending = cam.pending || {};
    cam.pending[key] = { ...(cam.pending[key] || {}), ...want };
    cam.mine = cam.mine || {};
    cam.mine[key] = { ...(cam.mine[key] || {}), ...want, at: Date.now() };
    clearTimeout(cam.settle);
    cam.settle = setTimeout(() => { if (selected === cam.key) drawSide(); }, HOLD + 50);   // (then as the cam says)
    if (!cam.flush) cam.flush = setTimeout(() => {
      const set = cam.pending;
      cam.pending = {};
      cam.flush = 0;
      send(cam, { type: "camctl", set });
    }, 120);
  }
  // A control as the cam last said, or as set here just now.
  function shown(cam, c) {
    const mine = (cam.mine || {})[c.key];
    if (!mine || Date.now() - mine.at > HOLD) return c;
    return { ...c, ...(mine.value !== undefined ? { value: mine.value } : {}), ...(mine.auto !== undefined && c.auto !== null ? { auto: mine.auto } : {}) };
  }
  const fmt = (c, v) => c.options ? ((c.options.find(o => o[0] === v) || [])[1] || v)
    : c.key === "zoom" && c.digital ? `${Number(v).toFixed(2)}x` : String(Math.round(Number(v) * 100) / 100);

  function controlRow(cam, c) {
    const value = h("span", { class: "muted small" }, fmt(c, c.value));
    let input;
    if (c.options) {
      input = h("select", { onchange: e => change(cam, c.key, { value: Number(e.target.value), auto: false }) },
        c.options.map(([v, label]) => h("option", { value: v, selected: v === c.value }, label)));
    } else {
      input = h("input", { type: "range", min: c.min, max: c.max, step: c.step, value: c.value, disabled: c.auto === true,
        oninput: e => { value.textContent = fmt(c, e.target.value); change(cam, c.key, { value: Number(e.target.value), auto: false }); } });
    }
    input.dataset.key = c.key;
    const auto = c.auto === null ? null : h("label", { class: "row-gap small" },
      h("input", { type: "checkbox", checked: c.auto, onchange: e => { input.disabled = e.target.checked; change(cam, c.key, { auto: e.target.checked }); } }), "Auto");
    return h("div", { class: "cr-ctl" },
      h("div", { class: "cr-ctl-head" }, h("span", {}, c.label, c.digital ? h("span", { class: "muted small" }, " (digital)") : null), value, auto),
      input);
  }

  function drawSide() {
    const side = $("#cr-side");
    const cam = selected && cams[selected];
    // (not while a slider's held: the cam's answer would fight it)
    if (cam && side.dataset.cam === cam.key && side.contains(document.activeElement) && document.activeElement.dataset.key
        && document.activeElement.matches(":active")) return;
    side.dataset.cam = cam ? cam.key : "";
    side.innerHTML = "";
    if (!cam) { side.append(h("div", { class: "muted cr-empty" }, "Pick a cam to set it.")); return; }
    side.append(h("div", { class: "panel-head" }, h("b", {}, camName(cam)), h("span", { class: "muted small" }, camModel(cam))));
    const body = h("div", { class: "cr-side-body" });
    side.append(body);
    if (!cam.state) {
      body.append(h("p", { class: "muted" }, Date.now() - cam.asked > 3000
        ? "This cam's Player Cam can't be set from here: update SCC Player Cam on that PC (Check for updates)."
        : "Asking the cam what it can do…"));
      return;
    }
    const controls = cam.state.controls || [];
    for (const [group, title] of [["light", "Lighting"], ["framing", "Framing"]]) {
      const rows = controls.filter(c => c.group === group);
      if (!rows.length) continue;
      body.append(h("h4", {}, title), ...rows.map(c => controlRow(cam, shown(cam, c))));
      if (group === "light" && rows.some(c => c.key === "gain")) {
        const exp = rows.find(c => c.key === "exposure");
        if (exp && shown(cam, exp).auto)
          body.append(h("p", { class: "muted small" }, "With Exposure on Auto the camera sets its own gain: moving Gain turns Exposure Auto off."));
      }
    }
    if (!controls.length) {
      // Why not: what the browser and the camera's driver said.
      const why = cam.state.why || {};
      body.append(h("p", { class: "muted" }, "Player Cam on this PC can't reach any of this camera's settings."),
        h("p", { class: "muted small" }, `Browser (${why.agent || "?"}): ${(why.browser || []).join(", ") || "no camera settings"}. `
          + (cam.state.app ? `Camera driver: ${why.driver || "no settings"}.` : "Opened in a browser, not the Player Cam app, so the driver isn't asked."),
          " Close any other app using the camera (Logi Tune, G HUB, Camera, OBS) and reopen Player Cam."));
    }
    const same = Object.values(cams).filter(o => o !== cam && o.state && camModel(o) === camModel(cam));
    body.append(h("div", { class: "cr-actions" },
      h("button", { class: "small", onclick: () => send(cam, { type: "camctl", reset: true }) }, "Reset camera"),
      h("button", { class: "small", disabled: !same.length, title: "The same lighting on every other " + camModel(cam),
        onclick: () => { const set = lighting(cam); for (const o of same) send(o, { type: "camctl", set }); toast(`Copied to ${same.length} cam${same.length === 1 ? "" : "s"}`); } },
        `Copy lighting to all ${camModel(cam) || "cams like it"} (${same.length})`)));
    if (cam.state.controls && !cam.state.app)
      body.append(h("p", { class: "muted small" }, "Opened in a browser, not the Player Cam app: gain and some other settings need the app."));
  }

  // A cam's lighting now: {key: {value, auto}}.
  function lighting(cam) {
    const set = {};
    for (const c of (cam.state && cam.state.controls) || []) if (c.group === "light") set[c.key] = c.auto === null ? { value: c.value } : { value: c.value, auto: c.auto };
    return set;
  }

  // --- lighting looks: every cam's lighting, saved under a name ---------------------
  const looks = () => (App.state && App.state.camera_looks) || [];
  const camId = cam => `${(cam.state && cam.state.pc) || ""}|${camModel(cam)}`;
  function drawLooks() {
    const sel = $("#cr-looks"), names = looks().map(l => l.name);
    if (sel.dataset.sig === names.join("\n")) return;
    sel.dataset.sig = names.join("\n");
    const was = sel.value;
    sel.innerHTML = "";
    sel.append(...(names.length ? names.map(n => h("option", { value: n }, n)) : [h("option", { value: "" }, "None saved")]));
    if (names.includes(was)) sel.value = was;
    $("#cr-recall").disabled = $("#cr-delete").disabled = !names.length;
  }
  App.on((s, what) => { if (what === "state") drawLooks(); });
  async function saveLooks(list) { await api("/api/camera-looks", { looks: list }); }
  $("#cr-save").addEventListener("click", async () => {
    const withState = Object.values(cams).filter(c => c.state);
    if (!withState.length) return toast("No cams to save the lighting of", true);
    const name = (prompt("Save every cam's lighting as (e.g. Stage lights, Daylight):", $("#cr-looks").value || "") || "").trim();
    if (!name) return;
    const look = { name, cams: Object.fromEntries(withState.map(c => [camId(c), lighting(c)])) };
    await saveLooks([...looks().filter(l => l.name !== name), look]);
    $("#cr-looks").dataset.sig = "";
    setTimeout(() => ($("#cr-looks").value = name), 300);
    toast(`Saved "${name}" (${withState.length} cam${withState.length === 1 ? "" : "s"})`);
  });
  $("#cr-recall").addEventListener("click", () => {
    const look = looks().find(l => l.name === $("#cr-looks").value);
    if (!look) return;
    let n = 0;
    for (const cam of Object.values(cams)) {
      const set = cam.state && look.cams[camId(cam)];
      if (set) { send(cam, { type: "camctl", set }); n++; }
    }
    toast(n ? `"${look.name}" on ${n} cam${n === 1 ? "" : "s"}` : `None of these cams were in "${look.name}"`, !n);
  });
  $("#cr-delete").addEventListener("click", async () => {
    const name = $("#cr-looks").value;
    if (name && confirm(`Delete the lighting "${name}"?`)) await saveLooks(looks().filter(l => l.name !== name));
  });
  $("#cr-add").addEventListener("click", () => {
    const typed = (prompt("A League or VALORANT HUD's address (e.g. 192.168.2.40:8778), or blank to forget the ones added:",
                          savedAddresses().map(a => a.replace(/^https?:\/\//, "")).join(", ")) ?? null);
    if (typed === null) return;
    const list = typed.split(/[,\s]+/).filter(Boolean).map(t => {
      try { const u = new URL(/^https?:\/\//.test(t) ? t : "http://" + t); return `http://${u.hostname}:${u.port || 8777}`; } catch (e) { return ""; }
    }).filter(Boolean);
    try { localStorage.setItem("ccr-huds", JSON.stringify(list)); } catch (e) { /* private window */ }
    if (active) listAll();
  });

  pages.cameras = { shown() { drawLooks(); drawGrid(); drawSide(); start(); } };
})();
