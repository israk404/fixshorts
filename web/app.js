"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
const STAGES = ["Read", "Write", "Review", "Videos", "Done"];
const BUSY = ["queued", "reading", "writing", "approved", "rendering"];
const KIND = { hook: "Problem", why: "Why it happens", avoid: "Avoid", cta: "Your turn" };

let ICONS = {};
let LOGOS = {};
let state = { jobs: [], reddit: "unknown", ready: 0 };
let selected = null;
let detail = null;
let editing = null;
let dirty = false;
let lastSeen = "";
let settingsData = null;
let voicesData = null;
let balance = null;

// ---------- helpers ----------

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "value") el.value = v;
    else if (k === "checked") el.checked = !!v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function icon(name) {
  const span = h("span", { class: "ti", "aria-hidden": "true" });
  if (ICONS[name]) span.textContent = String.fromCodePoint(ICONS[name]);
  return span;
}

async function api(method, url, body) {
  const res = await fetch(url, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const type = res.headers.get("content-type") || "";
  const data = type.includes("json") ? await res.json() : await res.blob();
  if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
  return data;
}

let toastTimer;
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), 4200);
}

function words(text) {
  return text.replace("{LINK}", "The link is in the description.").trim().split(/\s+/).filter(Boolean).length;
}

function money(v) {
  if (!v) return "";
  return v < 0.01 ? `$${v.toFixed(4)}` : `$${v.toFixed(3)}`;
}

function shortUrl(url) {
  if (url === "sample") return "Sample post";
  if (!url) return "";
  try {
    const u = new URL(url);
    const parts = u.pathname.split("/").filter(Boolean);
    const i = parts.indexOf("comments");
    return i >= 0 && parts[i + 2] ? parts[i + 2].replace(/_/g, " ") : u.hostname + u.pathname;
  } catch (e) {
    return url;
  }
}

// ---------- stage track ----------

function track(job, big = false) {
  const el = h("div", { class: "track" + (big ? " big" : ""), role: "img",
                        "aria-label": `Step ${job.stage + 1} of 5: ${job.label}` });
  const done = job.status === "done";
  const fill = h("span", { class: "fill" });
  fill.style.width = `${(done ? 4 : job.stage) * 20}%`;
  el.append(fill);
  STAGES.forEach((name, i) => {
    let cls = "pad";
    if (done || i < job.stage) cls += " done";
    else if (i === job.stage) {
      if (job.failed) cls += " fault";
      else if (["review", "skipped", "duplicate"].includes(job.status)) cls += " wait";
      else cls += " now" + (["reading", "writing", "rendering"].includes(job.status) ? " busy" : "");
    }
    el.append(h("div", { class: cls }, h("i"), h("span", { text: name })));
  });
  return el;
}

// ---------- top bar ----------

function renderStatus() {
  const s = $("#status");
  s.replaceChildren();
  const r = state.reddit;
  if (r === "logged_in") s.append(h("span", { class: "chip ok", text: "Reddit: logged in" }));
  else if (r === "waiting_login") s.append(h("span", { class: "chip warn", text: "Reddit: waiting for you to log in" }));
  else if (r === "checking") s.append(h("span", { class: "chip", text: "Reddit: checking" }));
  else if (r === "logged_out") s.append(h("span", { class: "chip bad" }, "Reddit: not logged in ",
    h("button", { type: "button", onclick: redditLogin, text: "Log in" })));
  else s.append(h("span", { class: "chip", text: "Reddit: unknown" }));

  if (balance && balance.amount !== undefined) {
    const cls = balance.available === false || parseFloat(balance.amount) < 0.2 ? "chip warn" : "chip ok";
    s.append(h("span", { class: cls, text: `DeepSeek balance: ${balance.currency === "USD" ? "$" : ""}${balance.amount}${balance.currency === "USD" ? "" : " " + balance.currency}` }));
  }
  if (state.peak_until) s.append(h("span", { class: "chip warn", text: `Peak AI prices until ${state.peak_until}` }));
  $("#login-banner").hidden = r !== "logged_out";
}

// ---------- queue ----------

function renderQueue() {
  const list = $("#queue");
  list.replaceChildren();
  $("#queue-empty").hidden = state.jobs.length > 0;
  for (const job of state.jobs) {
    const meta = job.failed ? job.error || job.label : job.message && BUSY.includes(job.status) ? job.message : job.label;
    const flags = job.status === "review" && job.attention.length
      ? h("div", { class: "flags" }, job.attention.map((a) => h("span", { class: "flag", text: a }))) : null;
    const li = h("li", { class: `job ${job.status}${job.id === selected ? " active" : ""}` },
      h("button", { class: "pick", type: "button", onclick: () => select(job.id), "aria-current": job.id === selected ? "true" : null },
        h("span", { class: "title", text: job.title || shortUrl(job.url) }),
        track(job),
        h("span", { class: "meta" }, h("span", { class: "state", text: meta }),
          h("span", { text: job.status === "rendering" ? `${Math.round(job.progress * 100)}%` : money(job.cost_usd) })),
        flags));
    list.append(li);
  }
  const btn = $("#approve-all");
  btn.hidden = !state.ready;
  btn.textContent = `Approve all ready (${state.ready})`;
}

async function poll() {
  try {
    state = await api("GET", "/api/state");
  } catch (e) {
    $("#status").replaceChildren(h("span", { class: "chip bad", text: "The app stopped. Start it again with start.bat." }));
    return;
  }
  renderStatus();
  renderQueue();
  if (!selected) return;
  const job = state.jobs.find((j) => j.id === selected);
  if (!job) { selected = null; detail = null; showWelcome(); return; }
  const sig = `${job.status}|${job.message}|${Math.round(job.progress * 100)}|${job.error}`;
  if (sig === lastSeen) return;
  const statusChanged = !detail || detail.status !== job.status;
  lastSeen = sig;
  if (statusChanged) {
    if (dirty && detail && detail.status === "review") return; // keep your unsaved edits
    loadDetail(selected);
  } else if (BUSY.includes(job.status)) {
    updateWorking(job);
  }
}

async function select(id) {
  if (dirty && !confirm("You have unsaved changes. Leave without saving?")) return;
  dirty = false;
  selected = id;
  renderQueue();
  await loadDetail(id);
}

async function loadDetail(id) {
  try {
    detail = await api("GET", `/api/jobs/${id}`);
  } catch (e) {
    toast(e.message);
    return;
  }
  dirty = false;
  renderDetail();
}

function showWelcome() {
  $("#detail").replaceChildren(h("div", { class: "welcome" },
    h("h2", { text: "Pick a job from the queue" }),
    h("p", { class: "muted", text: "Jobs that are ready for review are marked in gold." })));
}

// ---------- detail views ----------

function head(d) {
  const sub = [];
  if (d.url && d.url !== "sample") sub.push(h("a", { href: d.url, target: "_blank", rel: "noopener", text: "Source post" }));
  else sub.push("Sample post");
  if (d.cost_usd) sub.push(`, AI cost ${money(d.cost_usd)}`);
  const actions = h("div", { class: "head-actions" },
    h("button", { class: "btn small ghost", type: "button", onclick: openFolder }, icon("folder"), "Open folder"),
    !BUSY.includes(d.status) || d.status === "queued" || d.status === "approved"
      ? h("button", { class: "btn small ghost danger", type: "button", onclick: removeJob }, icon("trash"), "Delete") : null);
  return h("div", { class: "detail-head" },
    h("div", {}, h("h2", { text: d.title || shortUrl(d.url) }), h("p", { class: "sub" }, sub)), actions);
}

function renderDetail() {
  const d = detail;
  const box = $("#detail");
  box.replaceChildren(head(d));
  if (d.status === "review") box.append(...editor(d));
  else if (d.status === "done") box.append(...results(d));
  else if (d.status === "failed") box.append(...failed(d));
  else if (d.status === "skipped") box.append(...skipped(d));
  else if (d.status === "duplicate") box.append(...duplicate(d));
  else box.append(working(d));
}

function working(d) {
  const pct = Math.round((d.progress || 0) * 100);
  const msg = d.status === "queued" ? "Waiting for its turn." : d.status === "approved" ? "Approved. Waiting for the video maker." : d.message || d.label;
  return h("div", { class: "working", id: "working" },
    track(d, true),
    h("div", { class: "bigbar", "aria-hidden": "true" }, h("span", { style: `width:${d.status === "rendering" ? pct : 0}%` })),
    h("p", { class: "msg", id: "working-msg", text: d.status === "rendering" ? `${msg} ${pct}%` : msg }));
}

function updateWorking(job) {
  const w = $("#working");
  if (!w) return loadDetail(job.id);
  const pct = Math.round(job.progress * 100);
  $(".bigbar span", w).style.width = `${job.status === "rendering" ? pct : 0}%`;
  $("#working-msg").textContent = job.status === "rendering" ? `${job.message || job.label} ${pct}%` : job.message || job.label;
}

function failed(d) {
  const hasScript = !!d.script;
  return [h("div", { class: "block" },
    h("h3", { text: "This job stopped" }),
    h("p", { class: "error", text: d.error || "Unknown error." }),
    h("div", { class: "row" },
      h("button", { class: "btn primary", type: "button", onclick: () => retry({}) }, hasScript ? "Try making the videos again" : "Try again"),
      d.post && d.post.title ? h("button", { class: "btn", type: "button", onclick: () => retry({ reread: true }) }, "Read the page again") : null,
      hasScript ? h("button", { class: "btn", type: "button", onclick: backToReview }, "Edit the script") : null))];
}

function skipped(d) {
  return [h("div", { class: "block" },
    h("h3", { text: "The AI didn't think this post makes a good video" }),
    h("p", { text: (d.script && d.script.reject_reason) || d.message }),
    h("div", { class: "row" },
      h("button", { class: "btn", type: "button", onclick: () => retry({ rewrite: true }) }, "Write again anyway"),
      h("button", { class: "btn danger", type: "button", onclick: removeJob }, "Delete")))];
}

function duplicate(d) {
  return [h("div", { class: "block" },
    h("h3", { text: "You've used this post before" }),
    h("p", { text: d.message }),
    h("p", { class: "muted", text: "Nothing was sent to the AI, so this cost nothing." }),
    h("div", { class: "row" },
      h("button", { class: "btn", type: "button", onclick: () => retry({}) }, "Make it anyway"),
      h("button", { class: "btn danger", type: "button", onclick: removeJob }, "Delete")))];
}

// ---------- review editor ----------

function editor(d) {
  editing = structuredClone(d.script);
  const s = editing;
  const out = [];

  // What the AI says
  const conf = { high: "High confidence", medium: "Medium confidence: check carefully", low: "Low confidence: check every step" };
  out.push(h("div", { class: "block" },
    h("h3", { text: "What the AI says" }),
    h("div", { class: "verdict" }, h("span", { class: `conf ${s.confidence}`, text: conf[s.confidence] }),
      s.device ? h("span", { class: "muted", text: `For ${s.device}` }) : null),
    s.risk_flags.length ? h("div", {}, h("p", { class: "muted", text: "Risks the video mentions:" }),
      h("ul", { class: "notes risk" }, s.risk_flags.map((t) => h("li", { text: t })))) : null,
    s.review_notes.length ? h("div", {}, h("p", { class: "muted", text: "Notes for you:" }),
      h("ul", { class: "notes" }, s.review_notes.map((t) => h("li", { text: t })))) : null,
    h("div", { id: "rules" }, rulesView(d.problems || []))));

  // Script
  const segBox = h("div", {});
  let fix = 0;
  s.segments.forEach((seg) => {
    if (seg.kind === "fix") fix += 1;
    const name = seg.kind === "fix" ? `Fix ${fix}` : KIND[seg.kind];
    const count = h("span", { class: "count", text: `${words(seg.narration)} words` });
    segBox.append(h("div", { class: "seg" },
      h("div", { class: `kind ${seg.kind}`, text: name }),
      h("div", { class: "fields" },
        h("label", { text: "Headline on screen" }),
        h("input", { value: seg.headline, oninput: (e) => { seg.headline = e.target.value; touch(); } }),
        h("label", { text: "Small text on screen (menu path like Settings › Display, or a tip)" }),
        h("input", { value: seg.detail, oninput: (e) => { seg.detail = e.target.value; touch(); } }),
        h("label", { text: "What the voice says" }),
        h("textarea", { rows: 3, value: seg.narration, oninput: (e) => { seg.narration = e.target.value; count.textContent = `${words(seg.narration)} words`; touch(); updateTotal(); } }),
        count,
        seg.kind === "fix" ? h("label", { text: "Logo for this step (optional, for a fix that uses a brand's tool or site)" }) : null,
        seg.kind === "fix" ? logoPicker(seg.logo || "", (v) => { seg.logo = v; touch(); }) : null)));
  });
  out.push(h("div", { class: "block" },
    h("h3", { text: "Script" }),
    h("p", { class: "lead", text: "{LINK} is spoken as \"The link is in the description\" in the full video and \"The link is in the full video\" in the Short." }),
    segBox, h("p", { class: "total", id: "total" })));

  // Links
  out.push(h("div", { class: "block" },
    h("h3", { text: "Links in the description" }),
    h("p", { class: "lead", text: "Ticked links go into the full video's description. Open any link marked \"Check this site\" before you approve." }),
    h("div", { class: "links", id: "links-box" }),
    h("div", { class: "row" }, h("button", { class: "btn small", type: "button", onclick: addLink }, "Add a link"))));

  // Thumbnail
  const glyph = h("span", { class: "glyph", "aria-hidden": "true" });
  const setGlyph = () => (glyph.textContent = ICONS[s.icon] ? String.fromCodePoint(ICONS[s.icon]) : "");
  setGlyph();
  const iconSel = h("select", { onchange: (e) => { s.icon = e.target.value; setGlyph(); touch(); } },
    Object.keys(ICONS).filter((n) => !n.startsWith("brand-") && n !== "device-nintendo").sort()
      .map((n) => h("option", { value: n, text: n.replace(/-/g, " "), selected: n === s.icon ? "selected" : null })));
  out.push(h("div", { class: "block" },
    h("h3", { text: "Thumbnail" }),
    h("div", { class: "thumb-edit" },
      h("div", {}, h("label", { text: "Big words (2 to 4)" }),
        h("input", { value: s.thumbnail_text, maxlength: 28, oninput: (e) => { s.thumbnail_text = e.target.value; touch(); } })),
      h("div", {}, h("label", { text: "Problem icon" }), h("div", { class: "icon-pick" }, glyph, iconSel))),
    h("label", { text: "Brand logo (thumbnail, problem cards and the full video's side panel)" }),
    logoPicker(s.logo || "", (v) => { s.logo = v; touch(); })));

  // Upload details
  const u = s.upload;
  const titles = h("div", { class: "titles" }, u.titles.map((t, i) => h("div", { class: "title-opt" },
    h("input", { type: "radio", name: "title-choice", checked: i === (s.title_choice || 0), "aria-label": `Use title ${i + 1}`,
                 onchange: () => { s.title_choice = i; touch(); } }),
    h("input", { value: t, oninput: (e) => { u.titles[i] = e.target.value; touch(); } }))));
  out.push(h("div", { class: "block" },
    h("h3", { text: "Upload details" }),
    h("label", { text: "Title (pick one)" }), titles,
    h("label", { text: "Description (links and hashtags are added automatically)" }),
    h("textarea", { rows: 5, value: u.description, oninput: (e) => { u.description = e.target.value; touch(); } }),
    h("label", { text: "Tags (separated by commas)" }),
    h("input", { value: u.tags.join(", "), oninput: (e) => { u.tags = e.target.value.split(",").map((x) => x.trim()).filter(Boolean); touch(); } }),
    h("label", { text: "Hashtags (#shorts is added to the Short)" }),
    h("input", { value: u.hashtags.join(" "), oninput: (e) => { u.hashtags = e.target.value.split(/\s+/).filter(Boolean); touch(); } }),
    h("label", { text: "Pinned comment" }),
    h("input", { value: u.pinned_comment, oninput: (e) => { u.pinned_comment = e.target.value; touch(); } })));

  out.push(h("div", { class: "actions" },
    h("span", { class: "dirty-note", id: "dirty-note" }),
    h("span", { class: "spacer" }),
    h("button", { class: "btn ghost", type: "button", onclick: rewrite, text: "Write again" }),
    h("button", { class: "btn", type: "button", onclick: save, text: "Save changes" }),
    h("button", { class: "btn primary", type: "button", onclick: approve, text: "Approve and make videos" })));

  setTimeout(() => { renderLinks(); updateTotal(); }, 0);
  return out;
}

function logoPicker(current, onPick) {
  const img = h("img", { class: "logo-preview", alt: "" });
  const show = (slug) => { img.hidden = !slug; if (slug) img.src = `/api/logo/${slug}`; };
  const sel = h("select", { onchange: (e) => { show(e.target.value); onPick(e.target.value); } },
    h("option", { value: "", text: "No logo" }),
    Object.entries(LOGOS).sort((a, b) => a[1].title.localeCompare(b[1].title))
      .map(([slug, info]) => h("option", { value: slug, text: info.title, selected: slug === current ? "selected" : null })));
  show(current);
  return h("div", { class: "logo-pick" }, h("span", { class: "logo-box" }, img), sel);
}

function rulesView(problems) {
  if (!problems.length) return h("p", { class: "muted", text: "Rule check passed." });
  return h("div", {}, h("p", { class: "muted", text: "Rule check (you can still approve):" }),
    h("ul", { class: "notes rules" }, problems.map((p) => h("li", { text: p }))));
}

function renderLinks() {
  const box = $("#links-box");
  if (!box) return;
  box.replaceChildren();
  if (!editing.links.length) box.append(h("p", { class: "muted", text: "No links for this video." }));
  const trustText = { trusted: "Official site", check: "Check this site", blocked: "Blocked" };
  const statusText = { ok: "Opens", broken: "Doesn't open", unknown: "Couldn't check", unchecked: "Not checked yet" };
  editing.links.forEach((l, i) => {
    box.append(h("div", { class: "link-row" },
      h("input", { type: "checkbox", checked: l.use, disabled: l.trust === "blocked", "aria-label": "Use this link",
                   onchange: (e) => { l.use = e.target.checked; touch(); } }),
      h("div", {},
        h("input", { value: l.label, placeholder: "Short name, like Intel driver download", "aria-label": "Link name",
                     oninput: (e) => { l.label = e.target.value; touch(); } }),
        l.url ? h("a", { class: "url", href: l.url, target: "_blank", rel: "noopener noreferrer", text: l.url })
              : h("input", { placeholder: "https://...", "aria-label": "Link address", oninput: (e) => { l.url = e.target.value.trim(); touch(); } }),
        h("p", { class: "why", text: l.trust === "blocked" ? `Blocked: ${l.trust_reason}` : l.reason || l.trust_reason })),
      h("div", { class: "side-info" },
        h("span", { class: `trust ${l.trust}`, text: l.source === "you" && l.status === "unchecked" ? "New" : trustText[l.trust] || l.trust }),
        h("span", { text: (l.source === "ai" ? "Suggested by AI. " : "") + (statusText[l.status] || "") }),
        h("button", { class: "remove", type: "button", onclick: () => { editing.links.splice(i, 1); touch(); renderLinks(); }, text: "Remove" }))));
  });
}

function addLink() {
  editing.links.push({ url: "", label: "", use: true, reason: "Added by you", source: "you", trust: "check", trust_reason: "", status: "unchecked" });
  touch();
  renderLinks();
}

function updateTotal() {
  const el = $("#total");
  if (!el) return;
  const n = editing.segments.reduce((a, s) => a + words(s.narration), 0);
  const min = (settingsData && settingsData.values["script.min_words"]) || 100;
  const max = (settingsData && settingsData.values["script.max_words"]) || 145;
  el.textContent = `${n} words in total, about ${Math.round(n / 2.6)} seconds. Aim for ${min} to ${max}.`;
  el.className = "total" + (n < min || n > max ? " off" : "");
}

function touch() {
  dirty = true;
  const n = $("#dirty-note");
  if (n) n.textContent = "Unsaved changes";
}

async function save(quiet) {
  editing.links = editing.links.filter((l) => l.url);
  const res = await api("PUT", `/api/jobs/${selected}/script`, editing);
  editing.links = res.links;
  detail.problems = res.problems;
  detail.script = structuredClone(editing);
  dirty = false;
  const n = $("#dirty-note");
  if (n) n.textContent = "";
  $("#rules").replaceChildren(rulesView(res.problems));
  renderLinks();
  if (quiet !== true) toast("Saved.");
  return res;
}

async function approve() {
  try {
    if (dirty) await save(true);
    await api("POST", `/api/jobs/${selected}/approve`);
    toast("Approved. The videos are being made.");
    loadDetail(selected);
    poll();
  } catch (e) {
    toast(e.message);
  }
}

async function rewrite() {
  if (!confirm("Ask the AI to write this script again? Your edits will be replaced.")) return;
  dirty = false;
  await retry({ rewrite: true });
}

// ---------- results ----------

function results(d) {
  const f = d.files || {};
  const src = (name) => `/files/${d.id}/${name}?v=${f[name] || 0}`;
  const out = [];
  const dur = d.durations || {};
  out.push(h("div", { class: "block" },
    h("h3", { text: "Your videos" }),
    h("p", { class: "lead", text: `Short ${Math.round(dur.short || 0)} s, full video ${Math.round(dur.long || 0)} s. Voice: ${d.voice || "-"}.` }),
    h("div", { class: "results" },
      h("div", { class: "media-col" },
        f["short.mp4"] ? h("video", { class: "vshort", src: src("short.mp4"), controls: true, preload: "metadata" }) : null,
        h("span", { class: "caption", text: "Short (9:16)" })),
      h("div", { class: "media-col" },
        f["video.mp4"] ? h("video", { class: "vlong", src: src("video.mp4"), controls: true, preload: "metadata" }) : null,
        h("span", { class: "caption", text: "Full video (16:9)" }),
        f["thumbnail.jpg"] ? h("img", { class: "thumb", src: src("thumbnail.jpg"), alt: "Thumbnail for the full video" }) : null,
        h("span", { class: "caption", text: "Thumbnail" })))));

  const box = h("div", { class: "copy-group" });
  const tabs = h("div", { class: "tabs", role: "group", "aria-label": "Which video" });
  const show = (key) => {
    $$("button", tabs).forEach((b) => b.setAttribute("aria-pressed", b.dataset.key === key ? "true" : "false"));
    box.replaceChildren();
    const u = d.upload[key];
    for (const [label, value] of [["Title", u.title], ["Description", u.description], ["Tags", u.tags], ["Pinned comment", u.pinned_comment]]) {
      box.append(h("div", { class: "copy-item" },
        h("div", { class: "top" }, h("span", { text: label }),
          h("button", { class: "btn small", type: "button", onclick: () => copy(value, label) }, icon("copy"), "Copy")),
        h("pre", { text: value })));
    }
    if (key === "short") box.append(h("p", { class: "muted", text: "After both are uploaded, open the Short in YouTube Studio and set its Related video to the full video." }));
  };
  tabs.append(h("button", { class: "btn small", type: "button", "data-key": "long", onclick: () => show("long"), text: "Full video" }),
              h("button", { class: "btn small", type: "button", "data-key": "short", onclick: () => show("short"), text: "Short" }));
  if (d.upload) show("long");
  out.push(h("div", { class: "block" }, h("h3", { text: "Upload details" }), tabs, box));
  out.push(h("div", { class: "actions static" },
    h("span", { class: "spacer" }),
    h("button", { class: "btn", type: "button", onclick: backToReview, text: "Edit and make again" }),
    h("button", { class: "btn primary", type: "button", onclick: openFolder }, icon("folder"), "Open folder")));
  return out;
}

async function copy(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${label} copied.`);
  } catch (e) {
    toast("Couldn't copy. Select the text and press Ctrl+C.");
  }
}

// ---------- job actions ----------

async function retry(body) {
  try {
    await api("POST", `/api/jobs/${selected}/retry`, body);
    loadDetail(selected);
    poll();
  } catch (e) {
    toast(e.message);
  }
}

async function backToReview() {
  try {
    await api("POST", `/api/jobs/${selected}/edit`);
    loadDetail(selected);
    poll();
  } catch (e) {
    toast(e.message);
  }
}

async function openFolder() {
  try { await api("POST", `/api/jobs/${selected}/open`); } catch (e) { toast(e.message); }
}

async function removeJob() {
  if (!confirm("Delete this job and its files? This can't be undone.")) return;
  try {
    await api("DELETE", `/api/jobs/${selected}`);
    selected = null;
    detail = null;
    dirty = false;
    showWelcome();
    poll();
  } catch (e) {
    toast(e.message);
  }
}

async function redditLogin() {
  try {
    await api("POST", "/api/reddit/login");
    toast("A browser window is opening. Log in to Reddit there; it closes by itself when you're done.");
    poll();
  } catch (e) {
    toast(e.message);
  }
}

async function refreshBalance() {
  try { balance = await api("GET", "/api/balance"); } catch (e) { balance = null; }
  renderStatus();
}

// ---------- settings ----------

async function openSettings() {
  const dlg = $("#settings");
  try {
    settingsData = await api("GET", "/api/settings");
    if (!voicesData) voicesData = await api("GET", "/api/voices");
  } catch (e) {
    toast(e.message);
    return;
  }
  const v = settingsData.values;
  $$("[data-setting]", dlg).forEach((el) => {
    const val = v[el.dataset.setting];
    if (el.type === "checkbox") el.checked = !!val;
    else if (el.type === "radio") el.checked = el.value === val;
    else if (val !== undefined && val !== null) el.value = val;
  });
  $("#s-key-hint").textContent = settingsData.key_set ? `(saved, ends in ${settingsData.key_hint})` : "(not set yet)";
  const kokoro = $("input[name=engine][value=kokoro]", dlg);
  kokoro.disabled = !settingsData.kokoro_available;
  $("#kokoro-note").textContent = settingsData.kokoro_available ? "(Kokoro)" : "(not installed: run setup_models.py)";
  fillVoices();
  $("#s-balance").textContent = balance && balance.amount !== undefined
    ? `Balance: ${balance.amount} ${balance.currency}` : settingsData.key_set ? "Balance: couldn't check right now." : "";
  const styles = $("#thumb-styles");
  styles.replaceChildren();
  for (const [style, name] of [["bold", "Bold"], ["split", "Problem / fixed"], ["clean", "Clean"]]) {
    styles.append(h("label", {},
      h("input", { type: "radio", name: "thumb-style", value: style, checked: v["thumbnail.style"] === style, "data-setting": "thumbnail.style" }),
      h("img", { src: `/api/thumb-preview/${style}?theme=cyan`, alt: `${name} thumbnail style` }),
      h("span", { text: name })));
  }
  $("#s-reddit").textContent = { logged_in: "The app's browser is logged in to Reddit.", logged_out: "Not logged in yet. Use a spare Reddit account.",
    waiting_login: "Waiting for you to log in in the browser window.", checking: "Checking..." }[state.reddit] || "Not checked yet.";
  $("#settings-note").textContent = "";
  dlg.showModal();
}

function fillVoices() {
  const engine = ($("input[name=engine]:checked") || {}).value || "edge";
  const sel = $("#s-voice");
  const current = engine === "edge" ? settingsData.values["voice.edge_voice"] : settingsData.values["voice.voice"];
  const list = engine === "edge" ? voicesData.edge : voicesData.kokoro.map((id) => ({ id, label: id }));
  sel.replaceChildren(...list.map((x) => h("option", { value: x.id, text: x.label, selected: x.id === current ? "selected" : null })));
  if (!list.some((x) => x.id === current) && current) sel.prepend(h("option", { value: current, text: current, selected: "selected" }));
  $("#s-rate").disabled = engine !== "edge";
}

async function saveSettings() {
  const dlg = $("#settings");
  const changes = {};
  $$("[data-setting]", dlg).forEach((el) => {
    if (el.type === "radio") { if (el.checked) changes[el.dataset.setting] = el.value; }
    else if (el.type === "checkbox") changes[el.dataset.setting] = el.checked;
    else if (el.type === "number") changes[el.dataset.setting] = parseInt(el.value, 10);
    else changes[el.dataset.setting] = el.value;
  });
  const engine = changes["voice.engine"] || "edge";
  changes[engine === "edge" ? "voice.edge_voice" : "voice.voice"] = $("#s-voice").value;
  try {
    const res = await api("POST", "/api/settings", { changes });
    settingsData.values = res.values;
    $("#settings-note").textContent = "Saved.";
    toast("Settings saved.");
  } catch (e) {
    $("#settings-note").textContent = e.message;
  }
}

async function previewVoice() {
  const engine = ($("input[name=engine]:checked") || {}).value || "edge";
  const btn = $("#preview-voice");
  btn.disabled = true;
  try {
    const blob = await api("POST", "/api/voice-preview", { engine, voice: $("#s-voice").value, rate: $("#s-rate").value });
    const audio = $("#voice-audio");
    audio.src = URL.createObjectURL(blob);
    audio.hidden = false;
    audio.play();
  } catch (e) {
    toast(e.message);
  } finally {
    btn.disabled = false;
  }
}

// ---------- start ----------

async function init() {
  try { ICONS = await api("GET", "/assets/icons.json"); } catch (e) { ICONS = {}; }
  try { LOGOS = await api("GET", "/assets/logos.json"); } catch (e) { LOGOS = {}; }
  $$("[data-icon]").forEach((el) => { if (ICONS[el.dataset.icon]) el.textContent = String.fromCodePoint(ICONS[el.dataset.icon]); });

  $("#add").addEventListener("click", async () => {
    const text = $("#links").value;
    if (!text.trim()) { $("#add-note").textContent = "Paste at least one Reddit link first."; return; }
    try {
      const res = await api("POST", "/api/links", { text, allow_repeats: $("#allow-repeats").checked });
      $("#links").value = "";
      $("#allow-repeats").checked = false;
      const note = $("#add-note");
      note.replaceChildren(`Added ${res.added.length} link${res.added.length === 1 ? "" : "s"}.` +
        (res.skipped.length ? ` Skipped ${res.skipped.length} that weren't Reddit links.` : ""));
      if (res.repeats.length) {
        note.append(h("span", { class: "repeat-head", text: ` Skipped ${res.repeats.length} you've used before:` }),
          h("ul", { class: "repeats" }, res.repeats.map((r) => h("li", { text: `${shortUrl(r.url)}, ${r.why}` }))));
      }
      if (res.added.length && !selected) select(res.added[0]);
      poll();
    } catch (e) { $("#add-note").textContent = e.message; }
  });
  $("#sample").addEventListener("click", async () => {
    const res = await api("POST", "/api/sample");
    $("#add-note").textContent = "Added the sample. It's ready for review in a moment.";
    select(res.id);
    poll();
  });
  $("#approve-all").addEventListener("click", async () => {
    if (!confirm(`Make videos for all ${state.ready} jobs that are ready for review?`)) return;
    const res = await api("POST", "/api/approve-all");
    toast(`Approved ${res.approved}. Videos are made one at a time.`);
    poll();
    if (selected) loadDetail(selected);
  });
  $$("[data-action=reddit-login]").forEach((b) => b.addEventListener("click", redditLogin));
  $("#open-settings").addEventListener("click", openSettings);
  $("#save-settings").addEventListener("click", saveSettings);
  $("#preview-voice").addEventListener("click", previewVoice);
  $$("input[name=engine]").forEach((r) => r.addEventListener("change", fillVoices));
  $("#reddit-check").addEventListener("click", async () => { await api("POST", "/api/reddit/check"); toast("Checking the Reddit login."); });
  $("#save-key").addEventListener("click", async () => {
    try {
      await api("POST", "/api/key", { key: $("#s-key").value });
      $("#s-key").value = "";
      $("#s-key-hint").textContent = "(saved)";
      toast("Key saved.");
      refreshBalance();
    } catch (e) { toast(e.message); }
  });
  window.addEventListener("beforeunload", (e) => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

  try { settingsData = await api("GET", "/api/settings"); } catch (e) { settingsData = null; }
  await poll();
  refreshBalance();
  setInterval(poll, 1500);
  setInterval(refreshBalance, 60000);
}

init();
