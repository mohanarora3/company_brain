/* Last Day web app. Vanilla JS, no build step. Talks to lastday/server.py. */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x) => `${Math.round((x || 0) * 100)}%`;
const LABEL = { critical: "Critical", at_risk: "At risk", covered: "Covered", unknown: "Unscored" };
const SOURCE = { hr_pg: "HR (Postgres)", slack: "Slack", jira: "Jira", github: "GitHub", docs: "Wiki", pagerduty: "PagerDuty", hmem: "H-MEM", written: "Written down" };

const AGENTS = {
  "Orchestrator": { color: "#6B7785", does: "runs the rounds" },
  "Cartographer": { color: "#2A8C9E", does: "reads the Zetaris catalog" },
  "Resolver": { color: "#3D63C9", does: "links accounts to people" },
  "Planner": { color: "#8A4FBF", does: "plans and delegates" },
  "Investigator": { color: "#2E7A64", does: "runs federated probes" },
  "Analyst": { color: "#B4800B", does: "scores knowledge share" },
  "Critic": { color: "#C2362B", does: "challenges every label" },
  "Risk officer": { color: "#D0602A", does: "escalates by deadline" },
  "Successor scout": { color: "#4C9A3B", does: "finds who takes over" },
  "Archivist": { color: "#1F4F99", does: "Meterless memory" },
  "Writer": { color: "#7A6A58", does: "handover and interview" },
  "Ask": { color: "#2A8C9E", does: "answers successors" },
};
const ROUND_TITLE = (r) => r === 0 ? "Setup: catalog, identities, memory"
  : r === 1 ? "Round 1: where they show up"
  : r === 2 ? "Round 2: ownership from systems of record"
  : `Round ${r}: the Critic's requests`;

const S = {
  status: null, people: [], asOf: null, eid: null, person: null,
  runId: null, snap: null, events: [], queue: [], pacer: null, streaming: false, tab: "trace",
  areas: {}, agentCounts: {}, answers: {}, lastRound: -1, skip: false,
};

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  let body = {};
  try { body = await r.json(); } catch { /* empty body */ }
  if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
  return body;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.remove("show"), 3600);
}

function flaps(n, cls = "") {
  const s = String(Math.abs(n)).padStart(2, "0");
  return `<span class="flaps ${cls}" aria-hidden="true">${[...s].map((d) => `<span class="tile">${d}</span>`).join("")}</span>`;
}

function shortDate(iso) {
  if (!iso) return "";
  const d = new Date(String(iso).slice(0, 10) + "T12:00:00Z");
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

// ------------------------------------------------------------------ status
async function loadStatus() {
  try {
    S.status = await api("/api/status");
  } catch (e) {
    $("#chips").innerHTML = `<li class="chip"><span class="dot off"></span>Server unreachable: ${esc(e.message)}</li>`;
    return;
  }
  const st = S.status, f = st.federation || {}, m = st.meterless || {};
  const zet = f.engine === "zetaris";
  const fedText = zet
    ? (f.connected ? `<b>Zetaris</b> connected (${esc(f.route)})` : `<b>Zetaris</b> not reachable`)
    : `<b>Local snapshot</b> (Zetaris not configured)`;
  const memText = m.online
    ? `<b>Meterless</b> H-MEM ${m.hmem?.memories ?? 0} memories, World Model ${m.world?.entities ?? 0} entities`
    : `<b>Meterless</b> offline`;
  const fail = (st.failing || []).length ? `<li class="chip"><span class="dot warn"></span>Simulated outage: <b>${esc(st.failing.join(", "))}</b></li>` : "";
  $("#chips").innerHTML = `
    <li class="chip" title="${esc(st.federation_error || f.error || f.label || "")}"><span class="dot ${zet ? (f.connected ? "on" : "off") : "warn"}"></span>${fedText}</li>
    <li class="chip" title="${esc(m.error || (m.pinnedCommit ? "engines @ " + m.pinnedCommit.slice(0, 12) : ""))}"><span class="dot ${m.online ? "on" : "off"}"></span>${memText}</li>
    <li class="chip"><span class="dot ${/offline/.test(st.llm) ? "warn" : "on"}"></span><b>LLM</b> ${esc(st.llm)}</li>
    <li class="chip"><span class="dot ${/local/.test(st.embeddings) ? "warn" : "on"}"></span><b>Embeddings</b> ${esc(st.embeddings)}</li>
    ${fail}`;
  $("#board-foot").innerHTML = `<p>Acme Pay (fictional), seed ${esc(st.seed)}</p>
    <p>Agents may only read. HR salary, personal email, home city and ratings are blocked by policy.</p>`;
}

// ------------------------------------------------------------------ people
async function loadPeople() {
  try {
    const out = await api("/api/people");
    S.people = out.people;
    S.asOf = out.as_of;
  } catch (e) {
    $("#dep-list").innerHTML = `<li class="dep-empty">Could not read HR: ${esc(e.message)}</li>`;
    return;
  }
  $("#asof").textContent = `As of ${shortDate(S.asOf)}`;
  renderBoard();
}

function renderBoard() {
  const deps = S.people.filter((p) => p.last_day).sort((a, b) => {
    const pa = a.days_left < 0, pb = b.days_left < 0;
    return pa - pb || (pa ? b.days_left - a.days_left : a.days_left - b.days_left);
  });
  $("#dep-list").innerHTML = deps.map((p) => {
    const past = p.days_left < 0;
    const run = p.latest_run;
    const runLine = run ? `<span class="dep-run">Last run: ${run.critical ? `<b class="crit">${run.critical} critical</b>` : "0 critical"}, ${run.at_risk ? `<b class="risk">${run.at_risk} at risk</b>` : "0 at risk"}</span>` : "";
    return `<li><button class="dep ${past ? "left" : ""}" data-eid="${esc(p.employee_id)}" aria-current="${p.employee_id === S.eid}">
      <span class="dep-name">${esc(p.full_name)}</span>
      <span class="dep-when">${flaps(p.days_left, "sm " + (past ? "past" : ""))}<span class="dep-date">${past ? "left" : "last day"} ${esc(shortDate(p.last_day))}</span></span>
      <span class="dep-role">${esc(p.title)}, ${esc(p.team)}</span>
      ${runLine}
      <span class="sr">${past ? `left ${-p.days_left} days ago` : `${p.days_left} days left`}</span>
    </button></li>`;
  }).join("") || `<li class="dep-empty">Nobody has given notice.</li>`;
  renderPeopleList();
}

function renderPeopleList() {
  const q = $("#people-search").value.trim().toLowerCase();
  const rest = S.people.filter((p) => !p.last_day && (!q || `${p.full_name} ${p.title} ${p.team}`.toLowerCase().includes(q)));
  $("#people-list").innerHTML = rest.map((p) => `<li><button data-eid="${esc(p.employee_id)}" aria-current="${p.employee_id === S.eid}">
    <span>${esc(p.full_name)}</span><small>${esc(p.team)}</small></button></li>`).join("") ||
    `<li class="dep-empty">No match.</li>`;
}

// ----------------------------------------------------------------- routing
function setHash() {
  const parts = [S.eid, S.runId, S.tab].filter(Boolean);
  const h = "#/" + parts.join("/");
  if (location.hash !== h) history.replaceState(null, "", h);
}

async function fromHash() {
  const [eid, runId, tab] = location.hash.replace(/^#\/?/, "").split("/");
  if (eid) await selectPerson(eid, runId, tab);
}

// ------------------------------------------------------------------ person
async function selectPerson(eid, runId = null, tab = null) {
  const p = S.people.find((x) => x.employee_id === eid);
  if (!p) return;
  stopStream();
  S.eid = eid; S.person = p; S.runId = null; S.snap = null; S.events = []; S.answers = {};
  $$(".dep, .people-list button").forEach((b) => b.setAttribute("aria-current", String(b.dataset.eid === eid)));
  $("#welcome").hidden = true;
  $("#person").hidden = false;
  $("#p-name").textContent = p.full_name;
  $("#p-role").textContent = `${p.title}, ${p.team}${p.employment_type === "contractor" ? " (contractor)" : ""}`;
  const cd = $("#p-countdown");
  if (p.last_day) {
    const past = p.days_left < 0;
    cd.innerHTML = `<span class="flip">${flaps(p.days_left)}</span><small>${past ? `days since they left on ${esc(shortDate(p.last_day))}` : `days until ${esc(shortDate(p.last_day))}`}</small>`;
  } else {
    cd.innerHTML = `<small>No notice given. Run it to see what the company would lose.</small>`;
  }
  const rid = runId || p.latest_run?.run_id;
  const btn = $("#run-btn");
  btn.disabled = false;
  btn.textContent = rid ? "Investigate again" : "Investigate";
  setTab(tab || "trace", false);
  if (rid) await openRun(rid, false);
  else renderEmpty();
  setHash();
  $("#main").focus({ preventScroll: true });
}

function renderEmpty() {
  $("#run-meta").textContent = "";
  const msg = `<p class="empty">No investigation yet for ${esc(S.person.full_name)}. Press <b>Investigate</b>: the agents will query every connected system,
    argue about what they find, and write a handover plan you can act on.</p>`;
  for (const id of ["trace", "handover", "interview", "evidence"]) $(`#pane-${id}`).innerHTML = msg;
  renderAsk();
  updateTabCounts();
}

function setTab(tab, push = true) {
  S.tab = tab;
  $$("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === tab)));
  $$(".panes [role=tabpanel]").forEach((p) => { p.hidden = p.dataset.pane !== tab; });
  if (push) setHash();
}

function updateTabCounts() {
  const s = S.snap;
  const n = {
    handover: s?.outputs?.handover?.areas?.length,
    interview: s?.outputs?.interview?.questions?.length,
    evidence: s?.queries?.length,
  };
  $$("#tabs button").forEach((b) => {
    const base = b.textContent.replace(/\s*\d+$/, "");
    b.innerHTML = esc(base) + (n[b.dataset.tab] ? `<span class="count">${n[b.dataset.tab]}</span>` : "");
  });
}

// --------------------------------------------------------------------- run
async function startRun() {
  if (!S.eid || S.streaming) return;
  const btn = $("#run-btn");
  btn.disabled = true;
  btn.textContent = "Investigating…";
  try {
    const out = await api("/api/runs", { method: "POST", body: JSON.stringify({ employee_id: S.eid, use_memory: $("#mem-toggle").checked }) });
    S.runId = out.run_id; S.snap = null; S.answers = {};
    setTab("trace");
    beginTrace(true);
    stream(out.run_id, true);
  } catch (e) {
    toast(`Could not start: ${e.message}`);
    btn.disabled = false;
    btn.textContent = "Investigate";
  }
}

async function openRun(runId, push = true) {
  S.runId = runId;
  try {
    S.snap = await api(`/api/runs/${runId}`);
  } catch (e) {
    toast(`Run ${runId}: ${e.message}`);
    renderEmpty();
    return;
  }
  if (S.snap.status === "running") {
    beginTrace(true);
    stream(runId, true);
  } else {
    beginTrace(false);
    stream(runId, false);
    renderAll();
  }
  if (push) setHash();
}

function beginTrace(live) {
  S.events = []; S.queue = []; S.areas = {}; S.agentCounts = {}; S.lastRound = -1; S.skip = !live;
  $("#pane-trace").innerHTML = `
    <div class="trace-grid">
      <div>
        <div class="trace-tools">
          <span id="trace-state">${live ? "Running…" : "Recorded trace"}</span>
          <label><input type="checkbox" id="only-reasoning"> Hide queries</label>
          <button class="quiet" id="replay-btn" type="button" ${live ? "hidden" : ""}>Replay at reading speed</button>
          <button class="quiet" id="skip-btn" type="button" hidden>Show all now</button>
        </div>
        <ol class="log" id="log" aria-live="off"></ol>
      </div>
      <aside class="scoreboard" aria-label="Areas as the agents see them">
        <h3>What leaves with them</h3>
        <p>Labels change as the Critic asks for more evidence.</p>
        <ul class="agents" id="agents"></ul>
        <div id="sb"></div>
      </aside>
    </div>`;
  $("#run-meta").textContent = live ? "The agents are working. Each line below is something one of them did." : "";
}

function stopStream() {
  if (S.es) { S.es.close(); S.es = null; }
  clearInterval(S.pacer); S.pacer = null;
  S.streaming = false;
}

function stream(runId, live) {
  stopStream();
  S.streaming = live;
  const es = new EventSource(`/api/runs/${runId}/events`);
  S.es = es;
  es.onmessage = (m) => { S.queue.push(JSON.parse(m.data)); };
  es.addEventListener("end", async () => {
    es.close(); S.es = null;
    if (!live) return;
    try { S.snap = await api(`/api/runs/${runId}`); } catch { /* keep trace */ }
    S.streaming = false;
    const btn = $("#run-btn");
    btn.disabled = false; btn.textContent = "Investigate again";
    S.finishedAt = Date.now();
    if (S.queue.length > 25) $("#skip-btn").hidden = false;
  });
  es.onerror = () => {
    if (es.readyState === 2) {
      S.es = null; S.streaming = false;
      const btn = $("#run-btn");
      btn.disabled = false; btn.textContent = "Investigate again";
    }
  };
  S.pacer = setInterval(drain, 40);
}

function drain() {
  if (!S.queue.length) {
    if (!S.streaming && !S.es && S.pacer) {
      clearInterval(S.pacer); S.pacer = null;
      finishTrace();
    }
    return;
  }
  const n = S.skip ? S.queue.length : (S.queue.length > 80 ? 3 : 1);
  for (let i = 0; i < n && S.queue.length; i++) renderEvent(S.queue.shift(), !S.skip);
  renderScoreboard();
}

function finishTrace() {
  $("#skip-btn").hidden = true;
  $("#replay-btn").hidden = false;
  const s = S.snap;
  if (!s) return;
  if (s.status === "error") {
    $("#trace-state").textContent = "Run failed";
    $("#run-meta").textContent = s.error || "The run failed. See the last line of the trace.";
    return;
  }
  $("#trace-state").textContent = "Recorded trace";
  const q = (s.queries || []).length;
  $("#run-meta").textContent = `Run ${s.run_id}: ${s.round} rounds, ${q} federated queries on ${s.engine === "zetaris" ? "Zetaris" : "the local snapshot"}, `
    + `${s.evidence_count} pieces of evidence, ${s.duration_s}s. ${Object.keys(s.failed_sources || {}).length ? "Some sources failed; see Evidence." : ""}`;
  renderAll();
  loadPeople();
  loadStatus();
}

function replay() {
  const evs = [...S.events];
  beginTrace(false);
  S.skip = false;
  S.queue = evs;
  $("#replay-btn").hidden = true;
  $("#skip-btn").hidden = false;
  $("#trace-state").textContent = "Replaying the recorded trace";
  clearInterval(S.pacer);
  S.pacer = setInterval(drain, 40);
}

function renderEvent(ev, fresh) {
  S.events.push(ev);
  S.agentCounts[ev.agent] = (S.agentCounts[ev.agent] || 0) + 1;
  const log = $("#log");
  if (!log) return;
  if (ev.round !== S.lastRound) {
    S.lastRound = ev.round;
    log.insertAdjacentHTML("beforeend", `<li class="round" data-round="${ev.round}">${esc(ROUND_TITLE(ev.round))}<span id="rq-${ev.round}"></span></li>`);
  }
  const a = AGENTS[ev.agent] || { color: "#888" };
  const d = ev.data || {};
  let what = esc(ev.summary);
  if (ev.kind === "query") {
    const srcs = (d.sources || []).map((s) => SOURCE[s] || s).join(" + ");
    const sample = (d.sample || []).length ? `<pre>${esc(JSON.stringify(d.sample, null, 1)).slice(0, 900)}</pre>` : "";
    what = `<details><summary>${esc(ev.summary)} <span class="rows">${esc(d.rows)} rows, ${esc(d.ms)} ms, ${esc(srcs)}</span></summary>
      <pre>${esc(d.sql)}</pre>${sample}</details>`;
    const rq = $(`#rq-${ev.round}`);
    if (rq) rq.textContent = `${S.events.filter((e) => e.round === ev.round && e.kind === "query").length} queries`;
  } else if (ev.kind === "verdict" && d.notes?.length > 1) {
    what += `<div class="muted" style="font-size:13px">${d.notes.slice(1).map(esc).join("<br>")}</div>`;
  } else if (ev.kind === "plan" && d.steps) {
    what += `<ol style="margin:4px 0 0;padding-left:20px;font-size:13.5px;color:var(--muted)">${d.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>`;
  }
  const hide = ev.kind === "query" && $("#only-reasoning")?.checked;
  log.insertAdjacentHTML("beforeend", `<li class="ev k-${esc(ev.kind)} ${fresh ? "fresh" : ""}" ${hide ? "hidden" : ""}>
    <span class="who"><i style="background:${a.color}"></i>${esc(ev.agent)}</span><div class="what">${what}</div></li>`);
  // scoreboard state from the event stream
  if (ev.agent === "Analyst" && d.areas) {
    for (const x of d.areas) {
      const cur = S.areas[x.system] || { trail: [] };
      if (cur.label && cur.label !== x.label) cur.trail.push(`${LABEL[cur.label]} to ${LABEL[x.label]} after ${x.sources.length} sources`);
      S.areas[x.system] = { ...cur, ...x };
    }
  }
  if (ev.kind === "verdict" && d.system && S.areas[d.system]) {
    const ar = S.areas[d.system];
    ar.status = d.status; ar.note = d.notes?.[0];
  }
  if (ev.kind === "escalation" && S.areas[d.system]) S.areas[d.system].escalated = true;
  if (ev.kind === "challenge" && S.areas[d.system]) { S.areas[d.system].label = "critical"; S.areas[d.system].note = ev.summary; }
  if (fresh && log.lastElementChild) {
    const wrap = log.closest(".trace-grid");
    const r = log.lastElementChild.getBoundingClientRect();
    if (wrap && r.bottom > window.innerHeight - 40 && r.top < window.innerHeight + 200) log.lastElementChild.scrollIntoView({ block: "end", behavior: "auto" });
  }
}

function renderScoreboard() {
  $("#agents").innerHTML = Object.entries(AGENTS).filter(([n]) => S.agentCounts[n]).map(([n, a]) =>
    `<li title="${esc(a.does)}"><i style="background:${a.color}"></i><b>${esc(n)}</b> ${S.agentCounts[n]}</li>`).join("");
  const areas = Object.values(S.areas).sort((a, b) => ({ critical: 0, at_risk: 1, covered: 2 }[a.label] ?? 3) - ({ critical: 0, at_risk: 1, covered: 2 }[b.label] ?? 3) || b.share - a.share);
  $("#sb").innerHTML = areas.map((a) => `<div class="sb-area ${esc(a.label)}">
      <div class="sb-top"><b>${esc(a.name || a.system)}</b><span class="label ${esc(a.label)}">${LABEL[a.label] || a.label}</span></div>
      ${shareBar(a.share, a.backup)}
      <div class="sb-trail">${a.status ? `Critic: ${esc(a.status)}. ` : ""}${esc(a.trail?.slice(-1)[0] || "")}${a.escalated ? " Escalated." : ""}</div>
    </div>`).join("") || `<p class="muted" style="font-size:13px">Scores appear after round 2.</p>`;
}

function shareBar(mine, backup) {
  const m = Math.max(0, Math.min(1, mine || 0)), b = Math.max(0, Math.min(1 - m, backup || 0));
  return `<div class="share" role="img" aria-label="${pct(m)} of the knowledge is theirs, best backup holds ${pct(b)}">
      <span class="mine" style="width:${m * 100}%"></span><span class="backup" style="width:${b * 100}%"></span></div>
    <div class="share-key"><span>Theirs ${pct(m)}</span><span>Best backup ${pct(b)}</span></div>`;
}

// -------------------------------------------------------------- render all
function renderAll() {
  if (!S.snap || S.snap.status === "error") {
    for (const id of ["handover", "interview", "evidence"]) $(`#pane-${id}`).innerHTML = `<p class="empty">This run failed: ${esc(S.snap?.error || "unknown error")}</p>`;
    return;
  }
  for (const [sys, a] of Object.entries(S.snap.answers || {})) S.answers[sys] = a;
  renderHandover();
  renderInterview();
  renderEvidence();
  renderAsk();
  updateTabCounts();
}

const cite = (id) => `<button class="cite" type="button" data-cite="${esc(id)}" title="Open the evidence">${esc(id)}</button>`;
const cites = (ids, max = 10) => ids?.length ? `<div class="cites">${ids.slice(0, max).map(cite).join("")}${ids.length > max ? `<span class="muted" style="font-size:12px;align-self:center">+${ids.length - max} more</span>` : ""}</div>` : "";

function renderHandover() {
  const s = S.snap, h = s.outputs?.handover;
  if (!h) { $("#pane-handover").innerHTML = `<p class="empty">No handover yet.</p>`; return; }
  const accepted = s.accepted || {};
  const handed = s.outputs?.handed_over || {};
  const esc_ = h.escalations?.length ? `<section class="escalate"><h3>Escalate this week</h3><ul>${h.escalations.map((e) =>
    `<li><b>${esc(e.name)}</b> (tier ${e.tier}, ${e.days_left} days left): ${e.actions.map(esc).join("; ")}</li>`).join("")}</ul></section>` : "";
  const areas = h.areas.map((a) => {
    const succ = a.successor;
    const acc = accepted[a.system] || (handed[a.system] ? { successor: handed[a.system] } : null);
    const succHtml = succ ? `<h4>Who takes over</h4><div class="successor">
        <div><b>${esc(succ.name)}</b>, ${esc(succ.title || "")}<ul>${succ.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
        ${a.other_candidates?.length ? `<p class="muted" style="font-size:13px;margin:6px 0 0">Also considered: ${a.other_candidates.map((c) => `${esc(c.name)} (${Math.round(c.score * 100)})`).join(", ")}</p>` : ""}</div>
        <div>${acc ? `<span class="accepted">Handover accepted to ${esc(acc.successor)}</span>`
          : `<button class="ghost" type="button" data-accept="${esc(a.system)}" data-succ="${esc(succ.person)}" data-name="${esc(succ.name)}">Accept handover to ${esc(succ.name.split(" ")[0])}</button>`}</div>
      </div>` : "";
    const knows = a.knows?.length ? `<h4>What they know that is not written down</h4><ul class="knows">${a.knows.map((k) =>
      `<li><q>${esc(k.text)}</q><small>${esc(k.context)} ${cite(k.cite)}</small></li>`).join("")}</ul>` : "";
    const docs = a.docs_to_fix?.length ? `<h4>Wiki pages to fix</h4>${a.docs_to_fix.map((d) => `<div class="conflict"><b>${esc(d.title)}</b>: ${esc(d.issue)}</div>`).join("")}` : "";
    const checklist = `<h4>Checklist</h4><ul class="checklist">${a.checklist.map((c, i) => {
      const key = `${s.run_id}:${a.system}:${i}`;
      return `<li><label><input type="checkbox" data-check="${esc(key)}" ${localGet(key) ? "checked" : ""}><span>${esc(c)}</span></label></li>`;
    }).join("")}</ul>`;
    const trail = `<details class="more"><summary>How the agents reached this label</summary><ul class="trail">${(a.history || []).map((x) =>
      `<li><span class="stage">${esc(stageName(x))}</span><span>${x.label ? `${esc(LABEL[x.label] || x.label)}: theirs ${pct(x.share)}, best backup ${pct(x.backup)}${x.sources?.length ? ` from ${esc(x.sources.map((y) => SOURCE[y] || y).join(", "))}` : ""}` : ""}${(x.notes || []).map(esc).join(" ")}</span></li>`).join("")}</ul></details>`;
    return `<article class="area ${esc(a.label)}" id="area-${esc(a.system)}">
      <div class="area-head"><h3>${esc(a.name)}</h3><span class="label ${esc(a.label)}">${LABEL[a.label]}</span>
        <span class="tier">Tier ${a.tier}, confidence ${pct(a.confidence)}, Critic: ${esc(a.status)}${a.escalated ? ", escalated" : ""}</span></div>
      <div style="max-width:420px">${shareBar(a.share, a.backup)}</div>
      <p class="why">${esc(a.summary || a.why)}</p>
      ${knows}${succHtml}${checklist}${docs}${cites(a.citations)}${trail}
    </article>`;
  }).join("");
  const covered = h.covered?.length ? `<h3 style="font-size:17px;font-weight:800;margin:10px 0 10px">Already covered by others</h3><ul class="covered-list">${h.covered.map((c) =>
    `<li><b>${esc(c.name)}</b>: theirs ${pct(c.share)}, backups ${esc(c.backups.join(", ") || "n/a")}</li>`).join("")}</ul>` : "";
  const problems = s.outputs?.citation_problems?.length ? `<p class="conflict">The Critic found citation problems: ${s.outputs.citation_problems.map(esc).join("; ")}</p>` : "";
  $("#pane-handover").innerHTML = `<p class="headline">${esc(h.headline)}</p>
    <div class="doc-actions"><a class="btn-link" href="/api/runs/${esc(s.run_id)}/files/handover.md" download>Download handover.md</a>
      <span class="muted" style="font-size:13px;align-self:center">Written by ${esc(h.llm)}. Every section cites the evidence behind it.</span></div>
    ${problems}${esc_}${areas || `<p class="empty">Nothing at risk: every area they touch has a backup.</p>`}${covered}`;
}

function stageName(x) {
  const st = x.stage || "";
  if (st === "init") return "Round 1";
  if (st === "provisional") return `Round ${x.round}`;
  if (st === "corroborated") return `Round ${x.round}`;
  if (st.startsWith("critic:")) return "Critic";
  if (st === "risk:override") return "Risk officer";
  if (st === "memory") return "Memory";
  if (st === "handover") return "Handover";
  return st;
}

function localGet(k) { try { return localStorage.getItem("lastday:" + k) === "1"; } catch { return false; } }
function localSet(k, v) { try { localStorage.setItem("lastday:" + k, v ? "1" : "0"); } catch { /* private mode */ } }

async function acceptHandover(btn) {
  const sys = btn.dataset.accept;
  btn.disabled = true;
  try {
    const out = await api(`/api/runs/${S.snap.run_id}/handover/${encodeURIComponent(sys)}/accept`, {
      method: "POST", body: JSON.stringify({ successor_id: btn.dataset.succ, successor_name: btn.dataset.name, by: "manager" }) });
    (S.snap.accepted ||= {})[sys] = { successor_id: btn.dataset.succ, successor: btn.dataset.name };
    const closed = (out.history || []).filter((r) => r.validTo).length;
    btn.outerHTML = `<span class="accepted">Handover accepted to ${esc(btn.dataset.name)}</span>`;
    toast(`World Model: ownership of ${sys} now points to ${btn.dataset.name}${closed ? `; ${closed} earlier edge closed, not deleted` : ""}.`);
    loadStatus();
  } catch (e) {
    btn.disabled = false;
    toast(`Not saved: ${e.message}`);
  }
}

// --------------------------------------------------------------- interview
function renderInterview() {
  const s = S.snap, iv = s.outputs?.interview;
  if (!iv?.questions?.length) { $("#pane-interview").innerHTML = `<p class="empty">No questions: nothing at risk.</p>`; return; }
  const groups = {};
  for (const q of iv.questions) (groups[q.system] ||= { area: q.area, label: q.label, qs: [] }).qs.push(q);
  const saved = Object.keys(S.answers).length;
  $("#pane-interview").innerHTML = `
    <p class="headline">${iv.questions.length} questions for ${esc(iv.person)}, built from what the agents found. Each one cites its evidence.</p>
    <div class="doc-actions"><a class="btn-link" href="/api/runs/${esc(s.run_id)}/files/interview.md" download>Download interview.md</a></div>
    <p class="muted" style="max-width:80ch">Answers go into Meterless H-MEM with provenance. H-MEM checks them against what Slack and the wiki say,
      and the next run counts them as written knowledge, so the risk drops.</p>
    <div class="rerun" id="rerun" ${saved ? "" : "hidden"}><span><b id="saved-n">${saved}</b> answers saved to memory. Run the investigation again to see the risk change.</span>
      <button class="primary" type="button" data-rerun>Investigate again</button></div>
    ${Object.entries(groups).map(([sys, g]) => `<section class="iv-area"><h3>${esc(g.area)} <span class="label ${esc(g.label)}">${LABEL[g.label]}</span></h3>
      ${g.qs.map((q) => {
        const done = S.answers[q.id];
        return `<div class="q" data-qid="${esc(q.id)}" data-system="${esc(sys)}"><p>${esc(q.text)}</p>${cites(q.cites, 5)}
          <label class="sr" for="a-${esc(q.id)}">Answer</label>
          <textarea id="a-${esc(q.id)}" placeholder="Their answer, in their words" ${done ? "readonly" : ""}>${esc(done?.answer || "")}</textarea>
          <div class="q-foot"><span class="saved">${done ? savedText(done) : ""}</span>
            ${done ? "" : `<button class="ghost" type="button" data-save="${esc(q.id)}">Save answer to memory</button>`}</div></div>`;
      }).join("")}</section>`).join("")}`;
}

function savedText(d) {
  const c = d.conflicts?.length ? ` H-MEM flagged ${d.conflicts.length} conflict${d.conflicts.length > 1 ? "s" : ""} with existing memory.` : "";
  return `Saved as ${esc(d.memory_id)}.${c}`;
}

async function saveAnswer(btn) {
  const box = btn.closest(".q");
  const qid = box.dataset.qid, system = box.dataset.system;
  const answer = $("textarea", box).value.trim();
  if (!answer) { toast("Write the answer first."); $("textarea", box).focus(); return; }
  btn.disabled = true;
  const q = S.snap.outputs.interview.questions.find((x) => x.id === qid);
  try {
    const out = await api(`/api/runs/${S.snap.run_id}/interview`, { method: "POST",
      body: JSON.stringify({ system, question: q.text, question_id: qid, answer }) });
    S.answers[qid] = { answer, memory_id: out.memory.id, conflicts: out.conflicts };
    $(".saved", box).textContent = savedText(S.answers[qid]).replace(/<[^>]+>/g, "");
    $("textarea", box).readOnly = true;
    btn.remove();
    $("#rerun").hidden = false;
    $("#saved-n").textContent = Object.keys(S.answers).length;
    if (out.conflicts?.length) {
      const c = out.conflicts[0];
      box.insertAdjacentHTML("beforeend", `<div class="conflict">Conflict found by H-MEM (${esc(c.reason || "conflict")}). The exit interview outranks the wiki in the World Model's source priority.</div>`);
    }
    toast(`Saved to H-MEM as ${out.memory.id}.`);
    loadStatus();
  } catch (e) {
    btn.disabled = false;
    toast(`Not saved: ${e.message}`);
  }
}

// ---------------------------------------------------------------- evidence
function renderEvidence() {
  const s = S.snap;
  const qs = s.queries || [];
  const failed = Object.entries(s.failed_sources || {});
  const reqs = s.requests || [];
  const ids = Object.entries(s.identities || {});
  const findings = (s.findings || []).filter((f) => f.kind === "identity_ambiguous");
  const name = (eid) => S.people.find((p) => p.employee_id === eid)?.full_name || eid;
  $("#pane-evidence").innerHTML = `
    ${failed.length ? `<section class="ev-section"><h3>Sources that failed</h3><p>Agents retried once, then continued with the other sources at lower confidence.</p>
      <ul>${failed.map(([k, v]) => `<li><b>${esc(SOURCE[k] || k)}</b>: ${esc(v)}</li>`).join("")}</ul></section>` : ""}
    <section class="ev-section"><h3>Who asked whom for what</h3>
      <p>The Critic does not accept a label on thin evidence. Each request becomes work the Planner hands to another agent in the next round.</p>
      <div class="table-wrap"><table><thead><tr><th>Request</th><th>From</th><th>Kind</th><th>Area</th><th>Why</th><th>Status</th></tr></thead><tbody>
      ${reqs.map((r) => `<tr><td class="num">${esc(r.id)}</td><td>${esc(r.by)}</td><td>${esc(r.kind.replace("_", " "))}</td><td>${esc(r.system)}</td><td>${esc(r.detail)}</td><td>${esc(r.status)}</td></tr>`).join("") || `<tr><td colspan="6">No requests.</td></tr>`}
      </tbody></table></div></section>
    <section class="ev-section"><h3>Federated queries</h3>
      <p>Every read-only statement the agents sent through ${s.engine === "zetaris" ? "Zetaris" : "the local snapshot (same qualified names as Zetaris)"}. Click a row for the SQL.</p>
      <div class="table-wrap"><table><thead><tr><th>Id</th><th>Round</th><th>Agent</th><th>Purpose</th><th>Rows</th><th>ms</th></tr></thead><tbody>
      ${qs.map((q) => `<tr class="q-row ${q.error ? "q-err" : ""}" data-q="${esc(q.id)}" tabindex="0"><td class="num">${esc(q.id)}</td><td class="num">${q.round}</td><td>${esc(q.agent)}</td>
        <td>${esc(q.purpose)}${q.error ? ` (${esc(q.error.slice(0, 80))})` : ""}</td><td class="num">${q.rows}</td><td class="num">${q.ms}</td></tr>`).join("")}
      </tbody></table></div></section>
    <section class="ev-section"><h3>One person, many accounts</h3>
      <p>The Resolver links Slack, Jira and GitHub accounts to HR employees with federated joins on email, then names, then co-activity.</p>
      ${findings.length ? findings.map((f) => `<p class="conflict">Ambiguous ${esc(SOURCE[f.source] || f.source)} account <code>${esc(f.account.slice(0, 12))}</code> (${esc(f.names.join(" / "))}):
        ${f.resolved && f.verdict?.decided ? `resolved to <b>${esc(name(f.verdict.person))}</b> by co-activity on ${esc(Object.keys(f.verdict.systems || {}).join(", "))}` : "left unattributed"}</p>`).join("") : ""}
      <div class="table-wrap"><table><thead><tr><th>Person</th><th>Slack</th><th>Jira</th><th>GitHub</th><th>PagerDuty</th></tr></thead><tbody>
      ${ids.map(([eid, m]) => `<tr><td>${esc(name(eid))}</td>${["slack", "jira", "github", "pagerduty"].map((src) => `<td style="font-size:12.5px">${(m[src] || []).map((x) =>
        `${esc(x.method)} <span class="muted">(${pct(x.confidence)})</span>`).join("<br>") || `<span class="muted">none</span>`}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div></section>
    <section class="ev-section"><h3>Written to Meterless memory</h3>
      <p>H-MEM entries this run created, each with provenance. Click one for its trust-ledger history.</p>
      <ul class="ctx">${(s.memory_log || []).slice(0, 40).map((m) => `<li><span class="n">${esc(m.id)}</span><div>${esc(m.content)}<small>${esc(m.source)}</small>
        <div class="acts"><button class="quiet" type="button" data-audit="${esc(m.id)}">Trust ledger</button></div></div></li>`).join("") || `<li>No memory writes (memory was off or the bridge was down).</li>`}</ul></section>
    <section class="ev-section"><h3>Download</h3><ul>
      <li><a href="/api/runs/${esc(s.run_id)}/files/run.json" download>run.json</a>: the whole blackboard, including every query and verdict</li>
      <li><a href="/api/runs/${esc(s.run_id)}/files/events.jsonl" download>events.jsonl</a>: the trace, one event per line</li>
      <li><a href="/api/runs/${esc(s.run_id)}/files/handover.md" download>handover.md</a>: the handover plan</li></ul></section>`;
}

function openQuery(qid) {
  const q = (S.snap?.queries || []).find((x) => x.id === qid);
  if (!q) return;
  $("#drawer-title").textContent = `Query ${q.id}`;
  $("#drawer-body").innerHTML = `<dl class="kv"><dt>Agent</dt><dd>${esc(q.agent)}</dd><dt>Purpose</dt><dd>${esc(q.purpose)}</dd>
    <dt>Engine</dt><dd>${esc(q.engine)}</dd><dt>Round</dt><dd>${q.round}</dd><dt>Rows</dt><dd>${q.rows} in ${q.ms} ms</dd>
    ${q.error ? `<dt>Error</dt><dd>${esc(q.error)}</dd>` : ""}</dl><pre>${esc(q.sql)}</pre>`;
  $("#drawer").showModal();
}

function openCite(id) {
  const ev = S.snap?.evidence?.[id];
  const q = ev ? (S.snap.queries || []).find((x) => x.id === ev.query_id) : null;
  $("#drawer-title").textContent = "Evidence";
  if (!ev) {
    $("#drawer-body").innerHTML = `<p><code>${esc(id)}</code></p><p class="muted">This citation points to a memory or wiki page rather than a single row. Ask about it on the Ask tab.</p>`;
  } else {
    $("#drawer-body").innerHTML = `<dl class="kv"><dt>Source</dt><dd>${esc(SOURCE[ev.source] || ev.source)}</dd><dt>Kind</dt><dd>${esc(ev.kind.replace("_", " "))}</dd>
      <dt>What</dt><dd>${esc(ev.title)}</dd><dt>Reference</dt><dd><code>${esc(ev.ref)}</code></dd><dt>When</dt><dd>${esc(shortDate(ev.at) || ev.at)}</dd>
      <dt>Person</dt><dd>${esc(S.people.find((p) => p.employee_id === ev.person)?.full_name || ev.person || "unattributed")}</dd>
      <dt>Area</dt><dd>${esc(ev.system)}</dd><dt>Weight</dt><dd>${esc(ev.weight)}</dd></dl>
      ${q ? `<p><b>Found by ${esc(q.id)}</b>, ${esc(q.agent)}: ${esc(q.purpose)} (${q.rows} rows, ${q.engine})</p><pre>${esc(q.sql)}</pre>` : ""}`;
  }
  $("#drawer").showModal();
}

async function openAudit(mid) {
  $("#drawer-title").textContent = `Memory ${mid}`;
  $("#drawer-body").innerHTML = `<p class="muted">Loading the trust ledger…</p>`;
  $("#drawer").showModal();
  try {
    const out = await api(`/api/memory/${encodeURIComponent(mid)}/audit`);
    const m = out.memory || {};
    $("#drawer-body").innerHTML = `<p>${esc(m.content)}</p><dl class="kv"><dt>Source</dt><dd>${esc(m.source)}</dd>
      <dt>Provenance</dt><dd>${esc(m.provenance?.label || "")} (${esc(m.provenance?.origin || "")})</dd><dt>Confidence</dt><dd>${pct(m.confidence)}</dd>
      <dt>Layer</dt><dd>${esc(m.layer)}</dd><dt>Tags</dt><dd>${esc((m.tags || []).join(", "))}</dd></dl>
      <h3 style="font-size:15px;margin:10px 0 6px">Trust ledger</h3>
      <ul class="trail">${(out.history || []).map((h) => `<li><span class="stage">${esc(new Date(h.timestamp).toLocaleString())}</span>
        <span><b>${esc(h.action)}</b> by ${esc(h.actor)}${h.details ? `: ${esc(JSON.stringify(h.details)).slice(0, 200)}` : ""}</span></li>`).join("")}</ul>`;
  } catch (e) {
    $("#drawer-body").innerHTML = `<p>Could not read the ledger: ${esc(e.message)}</p>`;
  }
}

// --------------------------------------------------------------------- ask
function renderAsk() {
  const tacit = (S.snap?.areas || []).flatMap((a) => (a.tacit || []).map((t) => t.question)).filter((q) => q && q.length > 12 && q.length < 90);
  const sugg = [...new Set(tacit)].slice(0, 5);
  const defaults = ["Why does recon run at 03:40?", "How do I rotate the Unity Bank SFTP key?", "Who should I call at Zenith Retail when something breaks?"];
  $("#pane-ask").innerHTML = `
    <p class="muted" style="max-width:80ch">For the person taking over. Answers come from Meterless memory (exit-interview answers, verified findings, tacit Slack answers)
      and a live federated search, and cite both.</p>
    <form class="ask-form" id="ask-form"><label class="sr" for="ask-q">Question</label>
      <input id="ask-q" placeholder="Ask what ${esc(S.person?.full_name?.split(" ")[0] || "they")} would have known" autocomplete="off">
      <button class="primary" type="submit">Ask</button></form>
    <div class="suggest">${(sugg.length ? sugg : defaults).map((q) => `<button type="button" data-ask="${esc(q)}">${esc(q)}</button>`).join("")}</div>
    <div id="ask-out"></div>`;
}

async function doAsk(q) {
  const out = $("#ask-out");
  out.innerHTML = `<p class="muted">Searching memory and the connected systems…</p>`;
  try {
    const r = await api("/api/ask", { method: "POST", body: JSON.stringify({ question: q }) });
    const answer = esc(r.answer).replace(/\[(\d+)\]/g, "<sup>[$1]</sup>");
    out.innerHTML = `<p class="answer">${answer}</p><p class="muted" style="font-size:13px">${esc(r.mode)}</p>
      <ul class="ctx">${r.context.map((c) => `<li><span class="n">[${c.n}]</span><div>${esc(c.text.length > 320 ? c.text.slice(0, 320) + "…" : c.text)}
        <small>${esc(c.label)}${c.score != null ? `, relevance ${c.score}` : ""}${c.question ? `. Asked: ${esc(c.question)}` : ""}</small>
        ${c.kind === "memory" ? `<div class="acts"><button class="quiet" type="button" data-audit="${esc(c.id)}">Trust ledger</button>
          <button class="quiet" type="button" data-fb="helpful" data-mid="${esc(c.id)}">Helpful</button>
          <button class="quiet" type="button" data-fb="wrong" data-mid="${esc(c.id)}">Wrong</button></div>` : ""}</div></li>`).join("")}</ul>
      <details class="more"><summary>How this was answered</summary><ul class="trail">${r.trace.map((t) => `<li><span class="stage">${esc(t.step)}</span><span>${esc(t.detail)}</span></li>`).join("")}</ul>
      ${(r.queries || []).map((x) => `<pre>${esc(x.sql)}</pre>`).join("")}</details>`;
  } catch (e) {
    out.innerHTML = `<p class="empty">Could not answer: ${esc(e.message)}</p>`;
  }
}

async function feedback(btn) {
  try {
    const m = await api("/api/memory/feedback", { method: "POST", body: JSON.stringify({ memory_id: btn.dataset.mid, kind: btn.dataset.fb }) });
    toast(`H-MEM: ${btn.dataset.mid} confidence now ${pct(m.confidence)}.`);
    btn.parentElement.querySelectorAll("[data-fb]").forEach((b) => { b.disabled = true; });
  } catch (e) {
    toast(`Feedback not saved: ${e.message}`);
  }
}

// ----------------------------------------------------------------- sources
async function openSources() {
  $("#sources").showModal();
  const body = $("#sources-body");
  body.innerHTML = `<p class="muted">Reading the federation…</p>`;
  let s;
  try { s = await api("/api/sources"); } catch (e) { body.innerHTML = `<p>${esc(e.message)}</p>`; return; }
  const zet = s.engine === "zetaris";
  body.innerHTML = `<p>${zet ? "Agents query these sources in place through Zetaris." :
      "Zetaris is not configured, so agents query a local snapshot with the same table names. Set the Zetaris variables in .env to switch."}</p>
    ${s.all_sources.map((src) => {
      const reg = zet || (s.registered || []).includes(src);
      const n = Object.entries(s.counts || {}).filter(([k]) => k.startsWith(src + ".")).map(([k, v]) => `${k.split(".")[1]} ${v}`).join(", ");
      const failing = (s.failing || []).includes(src);
      return `<div class="src"><div><h3>${esc(SOURCE[src] || src)} <span class="muted" style="font-weight:400">(${esc(src)})</span></h3>
        <p>${reg ? (n ? esc(n) + " rows" : "registered") : "Not registered yet. Register it and the Cartographer will discover it on the next run."}</p></div>
        <div class="acts">${reg ? "" : `<button class="ghost" type="button" data-register="${esc(src)}">Register</button>`}
          ${src !== "hr_pg" ? `<label class="toggle"><input type="checkbox" data-fail="${esc(src)}" ${failing ? "checked" : ""}> Simulate outage</label>` : ""}</div></div>`;
    }).join("")}
    <div class="policy"><b>Governance.</b> Agents may only run read-only statements. Blocked: ${esc(s.governance.blocked_tables.join(", "))};
      columns ${esc(s.governance.blocked_columns.join(", "))}. HR is exposed as ${esc(s.governance.hr_exposure)}.</div>
    <div id="reg-out"></div>`;
}

async function registerSource(btn) {
  btn.disabled = true;
  try {
    const out = await api(`/api/sources/${btn.dataset.register}/register`, { method: "POST" });
    $("#reg-out").innerHTML = `<p style="margin-top:14px">${esc(out.note || "")}</p>${(out.sql || []).map((x) => `<pre>${esc(x)}</pre>`).join("")}`;
    toast(out.registered ? `Registered ${out.registered.join(", ")}` : "Review the statements, then confirm.");
    loadStatus();
    setTimeout(openSources, 50);
  } catch (e) {
    btn.disabled = false;
    toast(e.message);
  }
}

async function toggleFail(input) {
  try {
    const out = await api(`/api/sources/${input.dataset.fail}/fail`, { method: "POST", body: JSON.stringify({ on: input.checked }) });
    toast(out.failing.length ? `Outage on: ${out.failing.join(", ")}. The next run will retry, then work around it.` : "All sources restored.");
    loadStatus();
  } catch (e) {
    toast(e.message);
  }
}

// ------------------------------------------------------------------ events
document.addEventListener("click", (e) => {
  const t = e.target.closest("button, a, tr.q-row");
  if (!t) return;
  if (t.matches(".dep, .people-list button")) selectPerson(t.dataset.eid);
  else if (t.id === "run-btn" || t.matches("[data-rerun]")) startRun();
  else if (t.matches("#tabs button")) setTab(t.dataset.tab);
  else if (t.id === "replay-btn") replay();
  else if (t.id === "skip-btn") { S.skip = true; }
  else if (t.id === "open-sources") openSources();
  else if (t.matches("[data-accept]")) acceptHandover(t);
  else if (t.matches("[data-save]")) saveAnswer(t);
  else if (t.matches("[data-cite]")) openCite(t.dataset.cite);
  else if (t.matches("[data-audit]")) openAudit(t.dataset.audit);
  else if (t.matches("[data-fb]")) feedback(t);
  else if (t.matches("[data-ask]")) { $("#ask-q").value = t.dataset.ask; doAsk(t.dataset.ask); }
  else if (t.matches("[data-register]")) registerSource(t);
  else if (t.matches("tr.q-row")) openQuery(t.dataset.q);
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("tr.q-row")) openQuery(e.target.dataset.q);
  if (e.target.matches("#tabs button") && (e.key === "ArrowRight" || e.key === "ArrowLeft")) {
    const tabs = $$("#tabs button");
    const i = tabs.indexOf(e.target) + (e.key === "ArrowRight" ? 1 : -1);
    const next = tabs[(i + tabs.length) % tabs.length];
    next.focus(); setTab(next.dataset.tab);
  }
});
document.addEventListener("change", (e) => {
  if (e.target.matches("[data-check]")) localSet(e.target.dataset.check, e.target.checked);
  else if (e.target.matches("[data-fail]")) toggleFail(e.target);
  else if (e.target.id === "only-reasoning") $$(".ev.k-query").forEach((li) => { li.hidden = e.target.checked; });
});
document.addEventListener("submit", (e) => {
  if (e.target.id === "ask-form") {
    e.preventDefault();
    const q = $("#ask-q").value.trim();
    if (q) doAsk(q);
  }
});
$("#people-search").addEventListener("input", renderPeopleList);
window.addEventListener("hashchange", () => {
  const [eid] = location.hash.replace(/^#\/?/, "").split("/");
  if (eid && eid !== S.eid) fromHash();
});

(async function init() {
  await Promise.all([loadStatus(), loadPeople()]);
  if (location.hash.length > 2) await fromHash();
  setInterval(loadStatus, 30000);
})();
