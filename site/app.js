const RELEASE_ORDER = ["nfp", "cpi", "ppi", "fomc"];
const SOURCE_LABELS = {
  fred_releases: "FRED API",
  federal_reserve_fomc: "Federal Reserve",
  fred_history: "FRED history",
  fomc_history: "Fed history",
  gold_price_hourly: "Yahoo hourly",
  gold_price_daily: "Yahoo daily",
  historical_reactions: "Reaction database",
};
const SOURCE_URLS = {
  fred_releases: "https://api.stlouisfed.org/fred/releases/dates",
  federal_reserve_fomc: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  fred_history: "https://api.stlouisfed.org/fred/releases/dates",
  fomc_history: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  gold_price_hourly: "https://finance.yahoo.com/quote/GC=F/history",
  gold_price_daily: "https://finance.yahoo.com/quote/GC=F/history",
  historical_reactions: "./data/historical_reactions.json",
};

const app = document.querySelector("#app");
let calendar = { events: [], source_status: {}, generated_at: null };
let status = { sources: {}, generated_at: null };
let countdownTimer;

function esc(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  }[char]));
}

function formatDate(value, timeZone = "Africa/Lagos") {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone, weekday: "short", month: "short", day: "numeric", year: "numeric",
  }).format(new Date(value));
}

function formatTime(value, timeZone = "Africa/Lagos") {
  if (!value) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone, hour: "2-digit", minute: "2-digit", hour12: true, timeZoneName: "short",
  }).format(new Date(value));
}

function timePair(event) {
  return `<div class="time-pair"><span>${esc(formatTime(event.times?.et, "America/New_York"))}</span><span>${esc(formatTime(event.times?.wat, "Africa/Lagos"))}</span></div>`;
}

function sourceBadge(sourceKey, state) {
  const label = SOURCE_LABELS[sourceKey] || sourceKey || "Unknown source";
  const tone = state === "ok" ? "ok" : state === "fallback" ? "fallback" : state === "stale" ? "stale" : "off";
  return `<span class="source-badge ${tone}"><i></i>${esc(label)} · ${esc(state || "unavailable")}</span>`;
}

function pageLink(view, label) {
  return `<a class="nav-link" data-view="${view}" href="./?view=${view}">${label}</a>`;
}

function nav(view) {
  return `<nav class="nav" aria-label="Primary navigation">
    ${pageLink("home", "Overview")}
    ${pageLink("calendar", "Calendar")}
    ${pageLink("status", "Status")}
  </nav>`;
}

function phaseNotice() {
  return `<aside class="phase-notice"><span class="phase-number">01</span><div><strong>Calendar layer only</strong><p>Signals, indicators, win rates, historical gold reactions, locking, grading, and chaining are not available in this phase. No trade call is being generated.</p></div><span class="notice-mark">/ /</span></aside>`;
}

function sourceSummary() {
  const sourceList = Object.entries(status.sources || {});
  const healthy = sourceList.filter(([, item]) => item.state === "ok").length;
  const total = sourceList.length;
  return `<div class="source-summary"><span class="summary-label">SOURCE HEALTH</span><strong>${healthy}/${total || 2} verified</strong><span class="summary-detail">Last checked ${status.generated_at ? formatDate(status.generated_at, "Africa/Lagos") : "not yet"}</span></div>`;
}

function nextEvent() {
  const now = Date.now();
  return [...(calendar.events || [])].filter((event) => new Date(event.times?.et || event.date).getTime() >= now - 60 * 60 * 1000).sort((a, b) => new Date(a.times?.et || a.date) - new Date(b.times?.et || b.date))[0];
}

function countdown(event) {
  if (!event) return "—";
  const diff = new Date(event.times?.et || event.date).getTime() - Date.now();
  if (diff <= 0) return "IN PROGRESS";
  const hours = Math.floor(diff / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  const seconds = Math.floor((diff % 60000) / 1000);
  return `${String(Math.max(0, hours)).padStart(2, "0")}h ${String(minutes).padStart(2, "0")}m ${String(seconds).padStart(2, "0")}s`;
}

function releaseStrip() {
  const byType = Object.fromEntries(RELEASE_ORDER.map((id) => [id, []]));
  for (const event of calendar.events || []) {
    if (byType[event.release_type]) byType[event.release_type].push(event);
  }
  return `<div class="release-strip">${RELEASE_ORDER.map((id) => {
    const event = byType[id].find((item) => new Date(item.times?.et || item.date) >= new Date());
    const label = id === "fomc" ? "FOMC" : id.toUpperCase();
    return `<div class="release-cell"><span class="cell-label">${label}</span>${event ? `<strong>${esc(formatDate(event.times.et))}</strong><small>${esc(formatTime(event.times.et, "America/New_York"))} ET</small>` : `<strong class="muted">NOT AVAILABLE</strong><small>Awaiting verified source</small>`}</div>`;
  }).join("")}</div>`;
}

function eventRow(event, compact = false) {
  const sourceKey = event.source?.kind === "manual_fallback" ? "federal_reserve_fomc" : event.source?.kind === "fred_api" ? "fred_releases" : event.release_type === "fomc" ? "federal_reserve_fomc" : "fred_releases";
  const state = status.sources?.[sourceKey]?.state || "unavailable";
  return `<article class="event-row ${compact ? "compact" : ""}">
    <div class="event-date"><span>${esc(formatDate(event.times?.et || event.date, "America/New_York"))}</span><small>${esc(event.date)}</small></div>
    <div class="event-name"><span class="event-label">${esc(event.label)}</span><strong>${esc(event.name)}</strong><small>${esc(event.raw_label || "Verified release date")}</small></div>
    <div class="event-time"><span>ET ${esc(formatTime(event.times?.et, "America/New_York"))}</span><span>WAT ${esc(formatTime(event.times?.wat, "Africa/Lagos"))}</span></div>
    <div class="event-source">${sourceBadge(sourceKey, state)}<a href="${esc(event.source?.url || SOURCE_URLS[sourceKey])}" target="_blank" rel="noreferrer">source ↗</a></div>
  </article>`;
}

function homeView() {
  const event = nextEvent();
  return `${nav("home")}${phaseNotice()}${sourceSummary()}
    <section class="hero-grid">
      <div class="hero-copy"><p class="eyebrow">PRE-RELEASE MACRO MONITOR / XAUUSD</p><h1>The next verified release.</h1><p class="lede">A source-first calendar for the events that move the gold conversation. Dates are collected before the release; nothing is inferred when a source is missing.</p></div>
      <div class="next-card ${event ? "has-event" : "empty"}">
        <div class="card-top"><span>NEXT RELEASE</span><span class="lock-label">PHASE 1 / NO SIGNAL</span></div>
        ${event ? `<div class="next-type">${esc(event.label)} <span>/</span> ${esc(event.name)}</div><div class="countdown" data-countdown>${esc(countdown(event))}</div><div class="next-meta"><span>${esc(formatDate(event.times?.et, "America/New_York"))}</span>${timePair(event)}</div><div class="not-available"><strong>Signal not available</strong><span>Indicator and outcome layers begin in a later phase.</span></div>` : `<div class="empty-title">No verified upcoming release data</div><p class="empty-copy">The dashboard will not invent dates. Add the FRED API key in GitHub Actions, or inspect Status for the exact source condition.</p>`}
      </div>
    </section>
    <section class="section-block"><div class="section-heading"><div><p class="eyebrow">ALL FOUR RELEASE LANES</p><h2>This week at a glance</h2></div><a class="text-link" data-view="calendar" href="./?view=calendar">Open calendar →</a></div>${releaseStrip()}</section>
    <section class="section-block"><div class="section-heading"><div><p class="eyebrow">RECENTLY VERIFIED</p><h2>Upcoming timeline</h2></div></div><div class="event-list">${(calendar.events || []).filter((item) => new Date(item.times?.et || item.date) >= new Date(Date.now() - 86400000)).slice(0, 4).map((item) => eventRow(item, true)).join("") || `<div class="empty-panel">No upcoming calendar records are available yet.</div>`}</div></section>`;
}

function calendarView() {
  const events = [...(calendar.events || [])].sort((a, b) => new Date(a.times?.et || a.date) - new Date(b.times?.et || b.date));
  return `${nav("calendar")}${phaseNotice()}<section class="page-heading"><p class="eyebrow">VERIFIED EVENT STREAM</p><h1>Macro calendar</h1><p>Every displayed date comes from FRED or the Federal Reserve fallback file. The model does not attempt to fill missing BLS dates.</p></section><div class="calendar-key"><span><i class="key-dot fred"></i>FRED release date</span><span><i class="key-dot fed"></i>Federal Reserve calendar</span><span><i class="key-dot fallback"></i>manual fallback</span></div><section class="event-list full-list">${events.map((item) => eventRow(item)).join("") || `<div class="empty-panel">No verified calendar records are available. Check Status for the source reason.</div>`}</section>`;
}

function statusView() {
  const sourceKeys = ["fred_releases", "federal_reserve_fomc", "fred_history", "fomc_history", "gold_price_hourly", "gold_price_daily", "historical_reactions"];
  return `${nav("status")}<section class="page-heading"><p class="eyebrow">DATA PROVENANCE</p><h1>Status</h1><p>Health is reported per source. Stale means the last known data was kept after a failed refresh; unavailable means no verified records exist.</p></section><div class="status-grid">${sourceKeys.map((key) => {
    const item = status.sources?.[key] || { name: SOURCE_LABELS[key], state: "unavailable", detail: "No status has been recorded yet.", records: 0 };
    const sourceUrl = item.url || SOURCE_URLS[key];
    return `<article class="status-card ${esc(item.state)}"><div class="status-card-top">${sourceBadge(key, item.state)}<span class="status-count">${esc(item.records || 0)} records</span></div><h2>${esc(item.name || SOURCE_LABELS[key])}</h2><p>${esc(item.detail)}</p><dl><div><dt>LAST CHECKED</dt><dd>${item.last_checked ? esc(formatDate(item.last_checked, "Africa/Lagos")) : "Not recorded"}</dd></div><div><dt>MODE</dt><dd>${esc(item.mode || "—")}</dd></div></dl><a class="source-link" href="${esc(sourceUrl)}" target="_blank" rel="noreferrer">Open official source ↗</a></article>`;
  }).join("")}</div><section class="method-note"><span class="notice-mark">/ /</span><div><p class="eyebrow">HONESTY CHECK</p><h2>Missing data stays missing.</h2><p>Phase 1 never shows a guessed date, a placeholder value, or a signal dressed up as research. The next phase cannot begin until the calendar layer remains reliable.</p></div></section>`;
}

function getView() {
  const query = new URLSearchParams(window.location.search).get("view");
  if (query && ["home", "calendar", "status"].includes(query)) return query;
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path.endsWith("/calendar")) return "calendar";
  if (path.endsWith("/status")) return "status";
  return "home";
}

function render() {
  const view = getView();
  app.innerHTML = view === "calendar" ? calendarView() : view === "status" ? statusView() : homeView();
  document.querySelectorAll("[data-view]").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === view);
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const next = link.dataset.view;
      history.pushState({}, "", `./?view=${next}`);
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
  if (countdownTimer) clearInterval(countdownTimer);
  if (view === "home" && nextEvent()) {
    countdownTimer = setInterval(() => {
      const target = document.querySelector("[data-countdown]");
      if (target) target.textContent = countdown(nextEvent());
    }, 1000);
  }
}

async function loadData() {
  try {
    const [calendarResponse, statusResponse] = await Promise.all([fetch("./data/calendar.json", { cache: "no-store" }), fetch("./data/status.json", { cache: "no-store" })]);
    if (!calendarResponse.ok || !statusResponse.ok) throw new Error("generated JSON is not available");
    calendar = await calendarResponse.json();
    status = await statusResponse.json();
  } catch (error) {
    calendar = { events: [], source_status: {}, generated_at: null };
    status = { sources: {}, generated_at: null, load_error: error.message };
  }
  render();
}

window.addEventListener("popstate", render);
loadData();
