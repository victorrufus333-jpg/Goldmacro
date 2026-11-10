const RELEASE_ORDER = ["nfp", "cpi", "ppi", "fomc"];
const SOURCE_LABELS = {
  fred_releases: "FRED API",
  federal_reserve_fomc: "Federal Reserve",
  fred_history: "FRED history",
  fomc_history: "Fed history",
  gold_price_hourly: "Yahoo hourly",
  gold_price_daily: "Yahoo daily",
  historical_reactions: "Reaction database",
  fred_indicators: "FRED indicators",
  signal_engine: "Signal engine",
};
const SOURCE_URLS = {
  fred_releases: "https://api.stlouisfed.org/fred/releases/dates",
  federal_reserve_fomc: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  fred_history: "https://api.stlouisfed.org/fred/releases/dates",
  fomc_history: "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
  gold_price_hourly: "https://finance.yahoo.com/quote/GC=F/history",
  gold_price_daily: "https://finance.yahoo.com/quote/GC=F/history",
  historical_reactions: "./data/historical_reactions.json",
  fred_indicators: "https://api.stlouisfed.org/fred/series/observations",
  signal_engine: "./data/signals.json",
};

const app = document.querySelector("#app");
let calendar = { events: [], source_status: {}, generated_at: null };
let status = { sources: {}, generated_at: null };
let signals = { records: [], summary: {} };
let reactionHistory = { records: [] };
let trackRecord = { records: [], summary: {} };
let chainedCases = { records: [], summary: {} };
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
    ${pageLink("track", "Track Record")}
    ${pageLink("methodology", "Methodology")}
    ${pageLink("status", "Status")}
  </nav>`;
}

function phaseNotice() {
  return `<aside class="phase-notice"><span class="phase-number">03</span><div><strong>Signal engine / pre-release research</strong><p>Signals use configurable FRED indicator votes and a one-hour pre-release lock. Historical scores use FRED vintage dates and remain research reconstructions, not guaranteed real-time consensus backtests.</p></div><span class="notice-mark">/ /</span></aside>`;
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

function signalFor(event) {
  return (signals.records || []).find((item) => item.event_id === event?.id);
}

function signalClass(signal) {
  return signal?.signal === "BUY" ? "buy" : signal?.signal === "SELL" ? "sell" : "unsure";
}

function trackRecordLabel(signal) {
  const context = signal?.historical_context;
  if (!context) return "historical track record unavailable";
  return context.N ? `${Number(context.win_rate).toFixed(1)}% historical · N ${context.N}` : "historical N 0 · no graded cases";
}

function releaseStrip() {
  const byType = Object.fromEntries(RELEASE_ORDER.map((id) => [id, []]));
  for (const event of calendar.events || []) {
    if (byType[event.release_type]) byType[event.release_type].push(event);
  }
  return `<div class="release-strip">${RELEASE_ORDER.map((id) => {
    const event = byType[id].find((item) => new Date(item.times?.et || item.date) >= new Date());
    const label = id === "fomc" ? "FOMC" : id.toUpperCase();
    const signal = signalFor(event);
    return `<div class="release-cell"><span class="cell-label">${label}</span>${event ? `<strong>${esc(formatDate(event.times.et))}</strong><small>${esc(formatTime(event.times.et, "America/New_York"))} ET</small>${signal ? `<span class="signal-pill ${signalClass(signal)}">${esc(signal.signal)}</span>` : ""}` : `<strong class="muted">NOT AVAILABLE</strong><small>Awaiting verified source</small>`}</div>`;
  }).join("")}</div>`;
}

function eventRow(event, compact = false) {
  const sourceKey = event.source?.kind === "manual_fallback" ? "federal_reserve_fomc" : event.source?.kind === "fred_api" ? "fred_releases" : event.release_type === "fomc" ? "federal_reserve_fomc" : "fred_releases";
  const state = status.sources?.[sourceKey]?.state || "unavailable";
  const signal = signalFor(event);
  return `<article class="event-row ${compact ? "compact" : ""}">
    <div class="event-date"><span>${esc(formatDate(event.times?.et || event.date, "America/New_York"))}</span><small>${esc(event.date)}</small></div>
    <div class="event-name"><span class="event-label">${esc(event.label)}</span><strong><a class="event-detail-link" href="./?view=release&id=${encodeURIComponent(event.id)}" data-view="release" data-release-id="${esc(event.id)}">${esc(event.name)}</a></strong><small>${esc(event.raw_label || "Verified release date")}</small></div>
    <div class="event-time"><span>ET ${esc(formatTime(event.times?.et, "America/New_York"))}</span><span>WAT ${esc(formatTime(event.times?.wat, "Africa/Lagos"))}</span></div>
    <div class="event-source">${sourceBadge(sourceKey, state)}${signal ? `<span class="signal-pill ${signalClass(signal)}">${esc(signal.signal)}</span><small class="signal-state">${esc(signal.lock_state.replaceAll("_", " "))}</small>` : ""}<a href="${esc(event.source?.url || SOURCE_URLS[sourceKey])}" target="_blank" rel="noreferrer">source ↗</a></div>
  </article>`;
}

function homeView() {
  const event = nextEvent();
  const signal = signalFor(event);
  return `${nav("home")}${phaseNotice()}${sourceSummary()}
    <section class="hero-grid">
      <div class="hero-copy"><p class="eyebrow">PRE-RELEASE MACRO MONITOR / XAUUSD</p><h1>The next verified release.</h1><p class="lede">A source-first calendar for the events that move the gold conversation. Dates are collected before the release; nothing is inferred when a source is missing.</p></div>
      <div class="next-card ${event ? "has-event" : "empty"}">
        <div class="card-top"><span>NEXT RELEASE</span><span class="lock-label">PHASE 3 / ${esc(signal?.lock_state?.replaceAll("_", " ") || "SIGNAL ENGINE")}</span></div>
        ${event ? `<div class="next-type">${esc(event.label)} <span>/</span> ${esc(event.name)}</div><div class="countdown" data-countdown>${esc(countdown(event))}</div><div class="next-meta"><span>${esc(formatDate(event.times?.et, "America/New_York"))}</span>${timePair(event)}</div><div class="signal-callout ${signalClass(signal)}"><strong>${esc(signal?.signal || "UNSURE")}</strong><span>${esc(signal ? `${signal.lock_state.replaceAll("_", " ")} · score ${signal.model_score ?? "—"} · ${trackRecordLabel(signal)}` : "No signal record is available; the engine stays UNSURE.")}</span></div>` : `<div class="empty-title">No verified upcoming release data</div><p class="empty-copy">The dashboard will not invent dates. Add the FRED API key in GitHub Actions, or inspect Status for the exact source condition.</p>`}
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
  const sourceKeys = ["fred_releases", "federal_reserve_fomc", "fred_history", "fomc_history", "gold_price_hourly", "gold_price_daily", "historical_reactions", "fred_indicators", "signal_engine"];
  return `${nav("status")}<section class="page-heading"><p class="eyebrow">DATA PROVENANCE</p><h1>Status</h1><p>Health is reported per source. Stale means the last known data was kept after a failed refresh; unavailable means no verified records exist.</p></section><div class="status-grid">${sourceKeys.map((key) => {
    const item = status.sources?.[key] || { name: SOURCE_LABELS[key], state: "unavailable", detail: "No status has been recorded yet.", records: 0 };
    const sourceUrl = item.url || SOURCE_URLS[key];
    return `<article class="status-card ${esc(item.state)}"><div class="status-card-top">${sourceBadge(key, item.state)}<span class="status-count">${esc(item.records || 0)} records</span></div><h2>${esc(item.name || SOURCE_LABELS[key])}</h2><p>${esc(item.detail)}</p><dl><div><dt>LAST CHECKED</dt><dd>${item.last_checked ? esc(formatDate(item.last_checked, "Africa/Lagos")) : "Not recorded"}</dd></div><div><dt>MODE</dt><dd>${esc(item.mode || "—")}</dd></div></dl><a class="source-link" href="${esc(sourceUrl)}" target="_blank" rel="noreferrer">Open official source ↗</a></article>`;
  }).join("")}</div><section class="method-note"><span class="notice-mark">/ /</span><div><p class="eyebrow">HONESTY CHECK</p><h2>Missing data stays missing.</h2><p>Every vote carries its FRED vintage and observation date. A stale, missing, conflicting, or underpowered score becomes UNSURE. Historical reconstructions are labeled separately from live pre-release locks.</p></div></section>`;
}

function eventById(id) {
  return (calendar.events || []).find((item) => item.id === id);
}

function signalById(id) {
  return (signals.records || []).find((item) => item.event_id === id);
}

function historyById(id) {
  return (reactionHistory.records || []).find((item) => item.event_id === id);
}

function currentReleaseId() {
  const queryId = new URLSearchParams(window.location.search).get("id");
  if (queryId) return queryId;
  const match = window.location.pathname.match(/\/release\/([^/]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

function releaseDetailView() {
  const id = currentReleaseId();
  const event = eventById(id);
  const signal = signalById(id);
  const historical = historyById(id);
  const record = (trackRecord.records || []).find((item) => item.event_id === id);
  const title = event?.name || signal?.release_name || historical?.release_name || "Release detail";
  const label = event?.label || signal?.release_label || historical?.release_label || "RELEASE";
  const indicators = signal?.leading_indicators || historical?.leading_indicators || [];
  const reaction = historical?.price_reaction || record?.reaction;
  const context = signal?.historical_context || historical?.historical_context || record?.historical_context_at_lock;
  const badge = signal ? `<span class="signal-pill ${signalClass(signal)}">${esc(signal.signal)}</span>` : record ? `<span class="signal-pill ${signalClass(record)}">${esc(record.signal)}</span>` : `<span class="signal-pill unsure">UNSURE</span>`;
  return `${nav("release")}<section class="page-heading"><p class="eyebrow">RELEASE DETAIL / ${esc(label)}</p><h1>${esc(title)}</h1><p>${event ? `${esc(formatDate(event.times?.et || event.date, "America/New_York"))} · ${esc(formatTime(event.times?.et, "America/New_York"))} ET · ${esc(formatTime(event.times?.wat, "Africa/Lagos"))} WAT` : "No verified calendar record is available for this ID."}</p></section>
    <section class="detail-grid"><article class="detail-card"><div class="detail-card-top"><span class="eyebrow">SIGNAL STATE</span>${badge}</div><h2>${esc(signal?.lock_state?.replaceAll("_", " ") || record?.grade || historical?.signal_state || "Not recorded")}</h2><p>${esc(signal?.reason || record?.grade_reason || historical?.signal_reason || "This release has no live locked record.")}</p><dl><div><dt>SCORE</dt><dd>${esc(signal?.model_score ?? record?.model_score ?? historical?.model_score ?? "—")}</dd></div><div><dt>VINTAGE</dt><dd>${esc(signal?.data_vintage || record?.data_vintage || historical?.signal_data_vintage || "—")}</dd></div><div><dt>HISTORICAL N</dt><dd>${esc(context?.N ?? "—")}</dd></div><div><dt>WIN RATE</dt><dd>${context?.win_rate == null ? "—" : `${Number(context.win_rate).toFixed(1)}%`}</dd></div></dl></article><article class="detail-card"><div class="detail-card-top"><span class="eyebrow">POST-RELEASE REACTION</span><span class="status-count">${esc(reaction?.measure || "not graded")}</span></div><h2>${esc(record?.grade || historical?.grade || "UNSURE-skipped")}</h2><p>${reaction ? `Direction ${esc(reaction.direction || "—")} · return ${reaction.return_pct == null ? "—" : `${Number(reaction.return_pct).toFixed(3)}%`}` : "A reaction is only added after the release and a usable gold observation."}</p><a class="source-link" href="./?view=track">Open immutable track record ↗</a></article></section>
    <section class="section-block detail-section"><div class="section-heading"><div><p class="eyebrow">INDICATOR EVIDENCE</p><h2>Votes at the cutoff</h2></div><span class="status-count">${esc(signal?.data_vintage || historical?.signal_data_vintage || "No vintage")}</span></div><div class="indicator-list">${indicators.map((item) => `<article class="indicator-row"><div><strong>${esc(item.series_id)}</strong><span>${esc(item.label || "Indicator")}</span></div><div><span class="indicator-value">${item.value == null ? "—" : esc(item.value)}</span><small>${esc(item.vote_label || item.status || "unavailable")} · ${esc(item.observation_date || "no observation")}</small></div></article>`).join("") || `<div class="empty-panel">No indicator votes are recorded for this release.</div>`}</div></section>`;
}

function trackRecordView() {
  const summary = trackRecord.summary || {};
  const records = trackRecord.records || [];
  const chainSummary = chainedCases.summary || {};
  return `${nav("track")}<section class="page-heading"><p class="eyebrow">PUBLIC LEDGER / APPEND-ONLY</p><h1>Track record</h1><p>Only signals captured during a live pre-release lock can enter this ledger. Historical reconstructions remain separate research data.</p></section><section class="metric-grid"><div class="metric-card"><span>WIN RATE</span><strong>${summary.win_rate == null ? "—" : `${Number(summary.win_rate).toFixed(1)}%`}</strong><small>N ${esc(summary.N || 0)}</small></div><div class="metric-card"><span>WINS</span><strong>${esc(summary.wins || 0)}</strong><small>Directional cases</small></div><div class="metric-card"><span>LOSSES</span><strong>${esc(summary.losses || 0)}</strong><small>Directional cases</small></div><div class="metric-card"><span>SKIPPED</span><strong>${esc(summary.skipped || 0)}</strong><small>UNSURE / no reaction</small></div></section><section class="section-block"><div class="section-heading"><div><p class="eyebrow">IMMUTABLE RECORDS</p><h2>Locked calls</h2></div><span class="status-count">${records.length} records</span></div>${records.length ? `<div class="event-list">${records.map((item) => `<article class="event-row compact"><div class="event-date"><span>${esc(item.release_date)}</span><small>${esc(item.release_type)}</small></div><div class="event-name"><strong><a class="event-detail-link" href="./?view=release&id=${encodeURIComponent(item.event_id)}" data-view="release" data-release-id="${esc(item.event_id)}">${esc(item.release_name || item.event_id)}</a></strong><small>${esc(item.signal)} · locked ${esc(item.locked_at || "—")}</small></div><div class="event-time"><span>${esc(item.grade)}</span><span>${item.reaction?.return_pct == null ? "—" : `${Number(item.reaction.return_pct).toFixed(3)}%`}</span></div><div class="event-source"><span class="signal-pill ${item.grade === "WIN" ? "buy" : item.grade === "LOSS" ? "sell" : "unsure"}">${esc(item.grade)}</span></div></article>`).join("")}</div>` : `<div class="empty-panel">No live signal has completed the full lock-and-reaction cycle yet. This is an honest empty ledger, not a reconstructed backtest.</div>`}</section><section class="section-block"><div class="section-heading"><div><p class="eyebrow">CHAINED CASES</p><h2>Separate chain statistics</h2></div><span class="status-count">N ${esc(chainSummary.N || 0)}</span></div><p class="detail-copy">A chain pairs consecutive immutable locked records within the configured gap. It is directional only when both component records have WIN or LOSS grades; UNSURE-skipped cases remain visible.</p></section>`;
}

function trackFilter() {
  const value = new URLSearchParams(window.location.search).get("type");
  return RELEASE_ORDER.includes(value) ? value : "all";
}

function trackRecordViewFinal() {
  const filter = trackFilter();
  const summary = trackRecord.summary || {};
  const records = (trackRecord.records || []).filter((item) => filter === "all" || item.release_type === filter);
  const research = (signals.records || []).filter((item) => item.mode === "historical_reconstruction" && (filter === "all" || item.release_type === filter));
  const chainSummary = chainedCases.summary || {};
  const filterLinks = [{id: "all", label: "All"}, ...RELEASE_ORDER.map((id) => ({id, label: id.toUpperCase()}))].map((item) => `<a class="filter-link ${filter === item.id ? "active" : ""}" href="./?view=track&type=${item.id}" data-view="track" data-track-filter="${item.id}">${item.label}</a>`).join("");
  const liveRows = records.length ? `<div class="event-list">${records.map((item) => `<article class="event-row compact"><div class="event-date"><span>${esc(item.release_date)}</span><small>${esc(item.release_type)}</small></div><div class="event-name"><strong><a class="event-detail-link" href="./?view=release&id=${encodeURIComponent(item.event_id)}" data-view="release">${esc(item.release_name || item.event_id)}</a></strong><small>${esc(item.signal)} · locked ${esc(item.locked_at || "—")}</small></div><div class="event-time"><span>${esc(item.grade)}</span><span>${item.reaction?.return_pct == null ? "—" : `${Number(item.reaction.return_pct).toFixed(3)}%`}</span></div><div class="event-source"><span class="signal-pill ${item.grade === "WIN" ? "buy" : item.grade === "LOSS" ? "sell" : "unsure"}">${esc(item.grade)}</span></div></article>`).join("")}</div>` : `<div class="empty-panel">No immutable live records match this filter. Historical reconstructions are not inserted into this ledger.</div>`;
  const researchRows = research.length ? `<div class="event-list">${research.slice(0, 12).map((item) => `<article class="event-row compact"><div class="event-date"><span>${esc(item.release_date)}</span><small>${esc(item.release_type)}</small></div><div class="event-name"><strong><a class="event-detail-link" href="./?view=release&id=${encodeURIComponent(item.event_id)}" data-view="release">${esc(item.release_name || item.event_id)}</a></strong><small>historical reconstruction · vintage ${esc(item.data_vintage || "—")}</small></div><div class="event-time"><span>${esc(item.signal)}</span><span>score ${esc(item.model_score ?? "—")}</span></div><div class="event-source"><span class="signal-pill ${signalClass(item)}">${esc(item.grade || "UNSURE-skipped")}</span></div></article>`).join("")}</div>` : `<div class="empty-panel">No research reconstruction matches this filter.</div>`;
  return `${nav("track")}<section class="page-heading"><p class="eyebrow">PUBLIC LEDGER / ARCHIVE FILTER</p><h1>Track record</h1><p>Immutable live calls and Phase 3 historical reconstructions are displayed in separate sections. A blank public ledger is an honest result.</p></section><div class="filter-links" aria-label="Track record filters">${filterLinks}</div><section class="metric-grid"><div class="metric-card"><span>LIVE WIN RATE</span><strong>${summary.win_rate == null ? "—" : `${Number(summary.win_rate).toFixed(1)}%`}</strong><small>N ${esc(summary.N || 0)}</small></div><div class="metric-card"><span>WINS</span><strong>${esc(summary.wins || 0)}</strong><small>Immutable live cases</small></div><div class="metric-card"><span>LOSSES</span><strong>${esc(summary.losses || 0)}</strong><small>Immutable live cases</small></div><div class="metric-card"><span>CHAIN N</span><strong>${esc(chainSummary.N || 0)}</strong><small>Separate chained cases</small></div></section><section class="section-block"><div class="section-heading"><div><p class="eyebrow">IMMUTABLE RECORDS</p><h2>Locked calls</h2></div><span class="status-count">${records.length} records</span></div>${liveRows}</section><section class="section-block"><div class="section-heading"><div><p class="eyebrow">RESEARCH ARCHIVE</p><h2>Historical reconstructions</h2></div><span class="status-count">${research.length} shown</span></div>${researchRows}<p class="detail-copy">These records use historical FRED vintages and the free GC=F proxy. They are research context, not immutable public calls and not a guarantee of future results.</p></section>`;
}

function methodologyView() {
  return `${nav("methodology")}<section class="page-heading"><p class="eyebrow">METHOD / CONFIGURATION</p><h1>Methodology</h1><p>Gold Macro Signal is a source-first educational research tool. It refuses to fill missing inputs with guesses.</p></section><section class="method-grid"><article class="method-card"><span class="eyebrow">01 / CALENDAR</span><h2>Release timing</h2><p>NFP, CPI, and PPI use verified FRED release dates at 8:30 AM ET. FOMC uses the Federal Reserve calendar at 2:00 PM ET. Every page shows ET and WAT.</p></article><article class="method-card"><span class="eyebrow">02 / VOTES</span><h2>Indicator rules</h2><p>Each release has configured FRED series, lookbacks, native-unit thresholds, and a gold-bias direction. Every vote carries its vintage and observation date.</p></article><article class="method-card"><span class="eyebrow">03 / SIGNAL</span><h2>BUY / SELL / UNSURE</h2><p>BUY requires score at least 2. SELL requires score at most -2. Fewer than three usable votes, over 40% missing or stale inputs, a tie, or an uncleared threshold returns UNSURE.</p></article><article class="method-card"><span class="eyebrow">04 / LOCK</span><h2>Pre-release integrity</h2><p>A candidate can change before the final 60 minutes. Inside that window the signal is locked. Historical reconstructions use the day-before-release FRED vintage and are never inserted into the public ledger.</p></article><article class="method-card"><span class="eyebrow">05 / REACTION</span><h2>Gold measurement</h2><p>The primary reaction is the last hourly GC=F close before release to the first hourly close at or after 60 minutes. If hourly data is unavailable, the record uses daily close-to-close and says so.</p></article><article class="method-card"><span class="eyebrow">06 / TRACK RECORD</span><h2>N and win rate</h2><p>N counts only live locked BUY/SELL calls with a non-flat post-release reaction. UNSURE-skipped cases remain visible but are excluded from directional win rate. Existing records are never rewritten.</p></article></section><section class="method-note"><span class="notice-mark">/ /</span><div><p class="eyebrow">LIMITS</p><h2>Research, not advice.</h2><p>FRED vintages are not a licensed real-time consensus feed. GC=F is a COMEX futures proxy, not spot XAUUSD. Thresholds are transparent heuristics and are not independently validated for future performance.</p></div></section>`;
}

function getView() {
  const query = new URLSearchParams(window.location.search).get("view");
  if (query && ["home", "calendar", "status", "track", "release", "methodology"].includes(query)) return query;
  const path = window.location.pathname.replace(/\/+$/, "");
  if (path.endsWith("/calendar")) return "calendar";
  if (path.endsWith("/status")) return "status";
  if (path.endsWith("/track-record")) return "track";
  if (path.endsWith("/methodology")) return "methodology";
  if (path.includes("/release/")) return "release";
  return "home";
}

function render() {
  const view = getView();
  app.innerHTML = view === "calendar" ? calendarView() : view === "status" ? statusView() : view === "track" ? trackRecordViewFinal() : view === "release" ? releaseDetailView() : view === "methodology" ? methodologyView() : homeView();
  document.querySelectorAll("[data-view]").forEach((link) => {
    link.classList.toggle("active", link.dataset.view === view);
    link.addEventListener("click", (event) => {
      event.preventDefault();
      const next = link.dataset.view;
      const filter = link.dataset.trackFilter ? `&type=${encodeURIComponent(link.dataset.trackFilter)}` : "";
      history.pushState({}, "", `./?view=${next}${filter}`);
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
    const [calendarResponse, statusResponse, signalsResponse, historyResponse, trackResponse, chainsResponse] = await Promise.all([fetch("./data/calendar.json", { cache: "no-store" }), fetch("./data/status.json", { cache: "no-store" }), fetch("./data/signals.json", { cache: "no-store" }), fetch("./data/historical_reactions.json", { cache: "no-store" }), fetch("./data/track_record.json", { cache: "no-store" }), fetch("./data/chained_cases.json", { cache: "no-store" })]);
    if (!calendarResponse.ok || !statusResponse.ok) throw new Error("generated JSON is not available");
    calendar = await calendarResponse.json();
    status = await statusResponse.json();
    signals = signalsResponse.ok ? await signalsResponse.json() : { records: [], summary: {} };
    reactionHistory = historyResponse.ok ? await historyResponse.json() : { records: [] };
    trackRecord = trackResponse.ok ? await trackResponse.json() : { records: [], summary: {} };
    chainedCases = chainsResponse.ok ? await chainsResponse.json() : { records: [], summary: {} };
  } catch (error) {
    calendar = { events: [], source_status: {}, generated_at: null };
    status = { sources: {}, generated_at: null, load_error: error.message };
    signals = { records: [], summary: {} };
    reactionHistory = { records: [] };
    trackRecord = { records: [], summary: {} };
    chainedCases = { records: [], summary: {} };
  }
  render();
}

window.addEventListener("popstate", render);
loadData();
