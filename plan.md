# Gold Macro Signal — Phase 1 Plan

## Scope

Phase 1 delivers repository setup, a static mobile-first dashboard, a calendar refresh pipeline for NFP/CPI/PPI/FOMC, a manual FOMC fallback, and a source-health Status page. Later signal, indicator, backtest, track-record, locking, grading, and chaining features remain explicitly unavailable until their later phases.

The implementation uses only standard-library Python for the refresh and static build steps. The site is plain HTML, CSS, and JavaScript so it can be deployed to a free static host and served from a phone-managed GitHub repository without a database, login, paid API, or paid hosting.

## Data and automation

- `data/release_config.json` defines all four release types, verified FRED release IDs for the BLS releases, official source URLs, release times, and timezone rules.
- `scripts/update_calendar.py` fetches FRED release dates when `FRED_API_KEY` is present, parses the official Federal Reserve FOMC calendar, converts each verified event into ET and WAT timestamps, and writes JSON atomically.
- A failed source never replaces the prior source-specific events with an empty list. The corresponding source is marked stale or unavailable in `data/status.json`.
- `data/fomc_dates.json` is an editable fallback containing verified FOMC dates from the official calendar. Its use is visible on the Status page.
- `.github/workflows/refresh-calendar.yml` runs daily and can be started manually. It commits changed JSON only when the refresh succeeds or changes source-health metadata.
- `scripts/build_static.py` copies the site and data into `dist/` and creates route copies needed by static hosts.

## Site design

### Candidate directions

- **Neo-terminal atlas** — 0.08 probability: a dense, high-contrast research terminal with gold signal accents.
- **Quiet Swiss macro** — 0.05 probability: a restrained editorial system with large type and calm information blocks.
- **Noir observatory** — 0.07 probability: a dark observatory interface with thin rules and luminous data points.

### Chosen direction: Neo-terminal atlas

- **Design Movement:** Bloomberg-terminal clarity filtered through contemporary brutalist web design.
- **Core Principles:** data before decoration; strong hierarchy on small screens; visibly sourced values; calm warnings instead of false certainty.
- **Color Philosophy:** near-black graphite provides a low-glare research surface; warm gold is reserved for verified macro context; mint and red identify status without implying a trade recommendation in Phase 1.
- **Layout Paradigm:** a vertical signal rail with one primary “next release” block, then narrow source lanes and a horizontally scrollable event strip rather than a centered dashboard grid.
- **Signature Elements:** thin gold calibration rules, tiny uppercase source labels, and monospaced timestamp readouts.
- **Interaction Philosophy:** every interaction reveals provenance or freshness; unavailable data is a first-class state, not hidden behind a disabled-looking control.
- **Animation:** only short opacity and translate transitions for route changes and countdown refreshes; no looping motion that suggests market urgency.
- **Typography System:** `Inter` for compact interface copy with system fallbacks; `IBM Plex Mono` for timestamps, source IDs, and status labels.
- **Brand Essence:** a pre-release macro research instrument for gold watchers who want the model’s limits in view; precise, candid, watchful.
- **Brand Voice:** headlines are direct and time-aware; microcopy names the evidence boundary. Example lines: “The next verified release.” and “No source, no signal.”
- **Wordmark & Logo:** `XAU / MACRO` set as a split wordmark with a gold calibration slash, paired with a small four-point release marker.
- **Signature Brand Color:** `#D6A84F`, a muted assay-gold used only for provenance and verified macro context.

## Project structure

```text
.
├── .github/workflows/refresh-calendar.yml  # daily and manual refresh
├── data/
│   ├── release_config.json                  # release definitions and source URLs
│   ├── fomc_dates.json                      # phone-editable fallback calendar
│   ├── calendar.json                         # generated merged events
│   └── status.json                           # generated source-health state
├── scripts/
│   ├── update_calendar.py                    # FRED/Fed fetch, parse, validate, write
│   └── build_static.py                       # assemble deployable dist/
├── site/
│   ├── index.html                            # app shell and Phase 1 views
│   ├── app.js                                # route, calendar, status rendering
│   └── styles.css                            # mobile-first visual system
├── plan.md
├── TODO.md
└── README.md
```

## Build and delivery workflow

1. Run `python3 scripts/update_calendar.py`, `python3 scripts/build_historical.py`, and `python3 scripts/build_signals.py` with `FRED_API_KEY` set only in the GitHub Actions secret environment.
2. Run `python3 scripts/build_static.py` to produce `dist/`.
3. Serve `dist/` on the configured port for Preview validation.
4. Validate JSON, route manifest, source health, vintage cutoff, signal lock state, stale-data preservation, and static build output.
5. Commit the intended source and generated data to canonical `main` after fetching and integrating the current remote tip.
6. Publish only when explicitly requested; checkpointing and publication remain separate.

## Phase 2 extension

Phase 2 adds `scripts/build_historical.py`, a single configurable pipeline that loops through every release in `data/release_config.json`. It collects historical FRED release dates for NFP, CPI, and PPI with pagination, collects the same-year FOMC dates from the Federal Reserve page, downloads Yahoo Finance `GC=F` gold futures proxy prices through pinned `yfinance`, and records the post-release reaction for each event.

The primary reaction is hourly when Yahoo provides both a last hourly observation before the release and the first observation at or after 60 minutes after the release. Older or incomplete hourly history falls back to daily close-to-close from the previous trading day to the release day. The record stores the actual observation timestamps, the measure used, the symbol, interval, retrieval time, and adjustment basis. It never calls the proxy spot XAUUSD and never mixes hourly and daily measures silently.

Phase 2 intentionally leaves `leading_indicators` and `model_score` null with an explicit Phase 3 note. It builds the historical reaction database only; it does not generate a BUY, SELL, or UNSURE signal yet.

## Phase 3 extension

Phase 3 adds verified FRED series metadata and rules to `data/release_config.json` and implements `scripts/build_signals.py`. The engine requests FRED `output_type=2` observations by vintage date, uses the day before each release as the historical cutoff, and never forward-fills a missing series. Each rule has a method, lookback, threshold, gold-bias direction, source series, units, observation date, staleness check, and vote.

The engine sums BUY/SELL/neutral votes. It returns BUY only at score `>= 2`, SELL only at score `<= -2`, and UNSURE when fewer than three votes are usable, more than 40% are missing/stale, or the score does not clear a threshold. Upcoming records expose a candidate signal before the lock, a locked signal during the final 60 minutes before release, and a released state after the event. Historical records are labeled `historical_reconstruction` and carry the revised-data/consensus limitation beside the score.

## Phase 4 extension

Phase 4 keeps a strict distinction between reconstructed history and live public calls. `scripts/capture_locked_signals.py` appends only signals observed in the `locked_pre_release` state to `data/locked_signals.json`; it refuses an existing-event conflict. `scripts/update_track_record.py` joins those snapshots to completed gold reactions and appends immutable WIN, LOSS, or UNSURE-skipped entries to `data/track_record.json`. `scripts/build_chains.py` pairs consecutive immutable records within 45 days and reports chain statistics separately.

The static client adds Track Record and Release Detail views. Empty public-ledger states are displayed as empty rather than backfilled with historical reconstructions. The daily workflow performs full refresh and grading; a lightweight lock-window workflow runs at four UTC times to cover the 08:30 ET BLS and 14:00 ET FOMC windows across daylight-saving schedules without committing generated timestamp noise when no live lock is captured.

## Final hardening extension

The client adds a Methodology page and Track Record filters for all release types, while keeping immutable live records and historical reconstructions in separate sections. The build declares all page routes in `manus-routes.json` and copies static view entry points for GitHub Pages-style hosting. Production publication remains an external handoff because the project is still bound to the Manus canonical repository and no user-owned GitHub, Netlify, or Cloudflare destination is connected.
