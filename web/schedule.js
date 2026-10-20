// The Upcoming Schedule page: the matches the Schedule graphic lists, and
// how many of them it shows.
"use strict";

(function upcomingSchedule() {
  let sched = null;          // as edited here
  let pending = false;
  let last = "";
  const blank = () => ({ tournament: "", game: "", type: "", team1: "", team2: "", date: "", time: "" });
  const save = debounce(() => { pending = false; api("/api/global", { global: { schedule: sched } }); }, 400);
  const changed = () => { pending = true; save(); };
  const list = $("#s-list");

  function card(m, i) {
    const input = (k, label, attrs) => h("label", {}, label, h("input", Object.assign({ value: m[k], "data-k": k,
      oninput: e => { m[k] = e.target.value; changed(); if (k === "tournament") head.textContent = title(m, i); } }, attrs || {})));
    const title = (m, i) => `${i + 1}. ${m.tournament || "New match"}`;
    const move = d => { const j = i + d; if (j < 0 || j >= sched.matches.length) return; [sched.matches[i], sched.matches[j]] = [sched.matches[j], sched.matches[i]]; changed(); render(); };
    const head = h("b", {}, title(m, i));
    const off = i >= sched.count;
    return h("section", { class: "panel s-card" + (off ? " off" : "") },
      h("div", { class: "panel-head" }, head,
        h("span", { class: "muted small" }, off ? "Not shown" : "On the graphic"),
        h("div", { class: "spacer" }),
        h("button", { class: "ghost small", title: "Move up", disabled: i === 0, onclick: () => move(-1) }, "↑"),
        h("button", { class: "ghost small", title: "Move down", disabled: i === sched.matches.length - 1, onclick: () => move(1) }, "↓"),
        h("button", { class: "ghost small", title: "Remove", onclick: () => { sched.matches.splice(i, 1); changed(); render(); } }, "✕")),
      h("div", { class: "pad s-grid" },
        input("tournament", "Tournament name", { placeholder: "e.g. NACE VARSITY", class: "wide" }),
        input("game", "Game", { placeholder: "e.g. ROCKET LEAGUE" }),
        input("type", "Match type", { placeholder: "Optional, e.g. PLAYOFFS" }),
        input("team1", "Team 1", { list: "team-names", placeholder: "From the team list, or type one" }),
        input("team2", "Team 2", { list: "team-names", placeholder: "From the team list, or type one" }),
        input("date", "Date", { type: "date" }),
        input("time", "Time", { type: "time" })));
  }
  function render(reload) {
    if (!sched || reload) sched = JSON.parse(JSON.stringify(App.state.global.schedule || { count: 3, matches: [] }));
    $("#s-count").value = String(sched.count);
    list.replaceChildren(...(sched.matches.length ? sched.matches.map(card)
      : [h("div", { class: "empty" }, "No upcoming matches yet: + Add match.")]));
  }
  $("#s-add").addEventListener("click", () => {
    sched.matches.push(blank());
    changed();
    render();
    const cards = list.querySelectorAll(".s-card");
    cards[cards.length - 1].querySelector("input").focus();
  });
  $("#s-count").addEventListener("change", e => { sched.count = +e.target.value; changed(); render(); });

  App.on(s => {
    const sig = JSON.stringify(s.global.schedule);
    if (App.tab === "schedule" && sig !== last) {
      last = sig;
      if (!pending && !list.contains(document.activeElement)) render(true);
    }
  });
  pages.schedule = { shown() { if (App.state) { last = JSON.stringify(App.state.global.schedule); render(true); } } };
})();
