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

1. Run `python3 scripts/update_calendar.py` with `FRED_API_KEY` set only in the GitHub Actions secret environment.
2. Run `python3 scripts/build_static.py` to produce `dist/`.
3. Serve `dist/` on the configured port for Preview validation.
4. Validate JSON, route manifest, refresh behavior, stale-data preservation, and static build output.
5. Commit the Phase 1 source and generated data to canonical `main` after fetching and integrating the current remote tip.
6. Publish only when explicitly requested; the current approved Phase 1 work is saved as a checkpoint but not silently published.

## Phase 2 extension

Phase 2 adds `scripts/build_historical.py`, a single configurable pipeline that loops through every release in `data/release_config.json`. It collects historical FRED release dates for NFP, CPI, and PPI with pagination, collects the same-year FOMC dates from the Federal Reserve page, downloads Yahoo Finance `GC=F` gold futures proxy prices through pinned `yfinance`, and records the post-release reaction for each event.

The primary reaction is hourly when Yahoo provides both a last hourly observation before the release and the first observation at or after 60 minutes after the release. Older or incomplete hourly history falls back to daily close-to-close from the previous trading day to the release day. The record stores the actual observation timestamps, the measure used, the symbol, interval, retrieval time, and adjustment basis. It never calls the proxy spot XAUUSD and never mixes hourly and daily measures silently.

Phase 2 intentionally leaves `leading_indicators` and `model_score` null with an explicit Phase 3 note. It builds the historical reaction database only; it does not generate a BUY, SELL, or UNSURE signal yet.
