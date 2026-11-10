# Gold Macro Signal — Phase 1 Outcomes

## Phase 1 — Repository setup and calendar health

### Static project shell and phone-first navigation
- [x] The site is mobile-first, fast, readable on a small phone screen, and dark theme by default.
- [x] The Phase 1 site provides Home, Calendar, and Status views; later Release detail, Track Record, and Methodology views remain marked unavailable until later phases.
- [x] All times displayed by the calendar are shown in both WAT (Africa/Lagos) and ET (New York).
- [x] Every page carries: “Educational research tool. Not financial advice. Past win rates do not guarantee future results.”

### Release configuration and verified sources
- [x] The system defines NFP, CPI, PPI, and FOMC in one shared configuration file so adding a release does not require changing pipeline code.
- [x] The primary source for BLS release dates is the FRED API release-dates endpoint, using the free API key stored as the GitHub secret `FRED_API_KEY`.
- [x] The verified FRED release IDs used in Phase 1 are Employment Situation 50, Consumer Price Index 10, and Producer Price Index 46, supported by the official FRED release list documentation.
- [x] Standard release times are NFP, CPI, and PPI at 8:30 AM ET, and FOMC statement at 2:00 PM ET.
- [x] FOMC dates are parsed from the Federal Reserve published meeting calendar; if parsing fails, the system falls back to `data/fomc_dates.json` and flags the fallback on Status.

### Refresh automation and data honesty
- [x] A daily GitHub Action refreshes the calendar, and a manual workflow dispatch is available.
- [x] The refresh pipeline commits updated JSON back to the repository only when files change.
- [x] If a source fails, old source-specific data is kept and marked stale; empty results are not published.
- [x] No invented, estimated, placeholder, or sample values are presented as real data.
- [x] Every calendar source record exposes source URL/name and last-checked or source-updated metadata.

### Phase boundary and reporting
- [x] Signal generation, indicator votes, historical win rate, backtesting, locking, grading, track record, and chaining are not implemented in Phase 1 and are labeled as unavailable rather than simulated.
- [x] Phase 1 includes a phone-friendly README explaining how to add `FRED_API_KEY`, edit manual files, and check Status.
- [x] A Phase 1 Deviations report records what worked, failed, and remains unavailable.

## Phase 2 and later — intentionally open

- [x] Historical gold reaction database for all four releases through one configurable pipeline driven by `data/release_config.json`; adding a release must not require a code-path fork.
- [x] Each historical record stores release date, leading-indicator placeholder state, model-score placeholder state, and what gold did afterward without inventing unavailable values.
- [x] Gold reaction uses free Yahoo Finance data with the source, symbol, retrieval time, interval, adjustment basis, and history limitations recorded.
- [x] Primary reaction is the move from the last price before release to the price 60 minutes later when hourly data is available; otherwise the record explicitly uses daily close-to-close on release day as the fallback, without mixing measures silently.
- [x] The Phase 2 Status page shows history-source health and the reaction database state.
- [ ] Indicator votes, signal engine, thresholds, historical win rate, N, UNSURE logic, and one-hour locking.
- [ ] Full website pages, immutable pre-release signal track record, automatic grading, and hourly release-day automation.
- [ ] Release chaining with separate chained-case win rates.
