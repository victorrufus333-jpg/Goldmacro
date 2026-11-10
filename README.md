# Gold Macro Signal

A free, calendar-driven research site for US macro releases that may matter to gold. Phase 3 adds a configurable research signal engine while keeping missing or underpowered data as UNSURE.

## What Phase 1 and Phase 2 do

The site watches four release types: NFP (Employment Situation), CPI, PPI, and FOMC. It shows the next verified release, calendar events in New York time and Lagos time, and the health of each data source.

If a source is missing or fails, the site says so. It does not fill gaps with sample numbers or estimated dates.

Phase 2 adds a historical reaction database for the configured release window. It uses Yahoo Finance through pinned `yfinance` and the `GC=F` COMEX gold-futures symbol as a clearly labeled free proxy, not spot XAUUSD. Hourly data is used when both sides of the 60-minute window are available; otherwise the record explicitly uses previous-trading-day close to release-day close. The measure is stored on every record and is never mixed silently.

The generated Phase 2 records are in `data/historical_reactions.json`. The source limitations and exact run results are in `DEVIATIONS_PHASE2.md`.

Phase 3 verifies and retrieves FRED indicator series with vintage dates. It calculates configured votes for NFP, CPI, PPI, and FOMC, then returns BUY, SELL, or UNSURE. BUY requires score `>= 2`, SELL requires score `<= -2`, at least three usable votes, and no more than 40% missing or stale indicators. Upcoming records are candidates before the final 60-minute lock and become locked only during that pre-release window. Historical records are reconstructions, not a licensed real-time consensus feed.

Phase 3 also records a research-only grade against the measured `GC=F` reaction. `N` counts only BUY/SELL cases with a non-flat reaction; UNSURE-skipped cases are shown separately and are not treated as losses. The generated signal file is `data/signals.json`; the Phase 3 source and scoring limitations are in `DEVIATIONS_PHASE3.md`.

Phase 4 adds **Track Record** and **Release Detail** views. Only a signal captured while `locked_pre_release` can enter `data/locked_signals.json`; existing snapshots are never rewritten. After a completed release has a usable reaction, `scripts/update_track_record.py` appends a WIN, LOSS, or UNSURE-skipped record to `data/track_record.json`. `data/chained_cases.json` keeps separate statistics for consecutive immutable records within the configured 45-day gap.

Final hardening adds the **Methodology** page and Track Record filters for all, NFP, CPI, PPI, and FOMC. The live ledger and reconstructed research archive are deliberately separate.

## Owner setup from a phone

1. Open the repository on GitHub in the GitHub mobile app or your phone browser.
2. Open **Settings → Secrets and variables → Actions → New repository secret**.
3. Create a secret named `FRED_API_KEY` and paste your free FRED API key as the value. Do not put the key in a tracked file.
4. Open **Actions → Refresh macro calendar → Run workflow** once to test the refresh. The schedule then runs daily.
5. Open the deployed site and tap **Status**. A green source means the latest fetch worked. A yellow source means the last known data was kept while the source was stale. A grey source means no verified data is available yet.

## Phone-editable fallback files

- `data/fomc_dates.json` is the manual FOMC fallback. Edit only verified dates from the Federal Reserve calendar. Each entry needs a `date` in `YYYY-MM-DD`, a `time_et`, a `label`, and a `source_url`.
- `data/release_config.json` holds release names, verified FRED release IDs, official URLs, and release times. Do not change IDs unless you verify them through the FRED API or official FRED documentation.
- `data/calendar.json` and `data/status.json` are generated files. Do not hand-edit them to make a source look healthy.

## Local checks

```bash
python3 scripts/update_calendar.py
python3 -m pip install -r requirements.txt
python3 scripts/build_historical.py
python3 scripts/build_signals.py
python3 scripts/capture_locked_signals.py
python3 scripts/update_track_record.py
python3 scripts/build_chains.py
python3 scripts/build_static.py
python3 -m http.server 3000 --directory dist
```

A missing `FRED_API_KEY` is expected on a fresh checkout. In that case the pipeline keeps prior BLS data and marks FRED unavailable. The Federal Reserve calendar can still populate if its public page is reachable. Phase 2 starts with the current calendar year because the free FRED release-date endpoint is broad and paginated; change `history.start_date` in `data/release_config.json` only when a longer window is worth the additional fetch time.

## Current phase boundary

Final hardening is complete in the repository. A public production URL still requires connecting this repository to GitHub Pages, Netlify, or Cloudflare Pages. The ledger starts empty until a real signal passes through the live lock window; historical reconstructions are never backfilled into it. `GC=F` remains a gold-futures proxy, not spot XAUUSD.

## Disclaimer

Educational research tool. Not financial advice. Past win rates do not guarantee future results.
