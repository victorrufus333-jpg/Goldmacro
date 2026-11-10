# Gold Macro Signal

A free, calendar-driven research site for US macro releases that may matter to gold. Phase 1 provides verified release-date collection and source health. It does **not** issue a trading signal yet.

## What Phase 1 and Phase 2 do

The site watches four release types: NFP (Employment Situation), CPI, PPI, and FOMC. It shows the next verified release, calendar events in New York time and Lagos time, and the health of each data source.

If a source is missing or fails, the site says so. It does not fill gaps with sample numbers or estimated dates.

Phase 2 adds a historical reaction database for the configured release window. It uses Yahoo Finance through pinned `yfinance` and the `GC=F` COMEX gold-futures symbol as a clearly labeled free proxy, not spot XAUUSD. Hourly data is used when both sides of the 60-minute window are available; otherwise the record explicitly uses previous-trading-day close to release-day close. The measure is stored on every record and is never mixed silently.

The generated Phase 2 records are in `data/historical_reactions.json`. The source limitations and exact run results are in `DEVIATIONS_PHASE2.md`.

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
python3 scripts/build_static.py
python3 -m http.server 3000 --directory dist
```

A missing `FRED_API_KEY` is expected on a fresh checkout. In that case the pipeline keeps prior BLS data and marks FRED unavailable. The Federal Reserve calendar can still populate if its public page is reachable. Phase 2 starts with the current calendar year because the free FRED release-date endpoint is broad and paginated; change `history.start_date` in `data/release_config.json` only when a longer window is worth the additional fetch time.

## Phase boundary

Signals, leading indicators, historical gold reactions, win rates, locking, grading, track record, and release chaining are intentionally not available in Phase 1. They will only be added after the earlier phase has been reviewed.

## Disclaimer

Educational research tool. Not financial advice. Past win rates do not guarantee future results.
