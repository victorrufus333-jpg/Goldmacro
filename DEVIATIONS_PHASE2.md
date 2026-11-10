# Phase 2 Deviations Report

## What works

The historical pipeline is shared across NFP, CPI, PPI, and FOMC. It loops through `data/release_config.json` rather than maintaining a separate code path per release. FRED BLS release dates are paginated and normalized into the same event shape as Federal Reserve FOMC dates.

The output database is `data/historical_reactions.json`. Each record stores the release identity and time, null leading-indicator/model-score fields with a Phase 3 note, the gold reaction, the exact measure used, source symbol, source URL, retrieval time, interval, and adjustment basis.

Hourly reaction logic uses the last Yahoo hourly Close timestamped before the release and the first hourly Close timestamped at or after release plus 60 minutes. The daily fallback uses the previous available New York trading-day Close to the release-day Close. The two measures are never merged under one unlabeled field.

## Phase 2 run results

The configured window is 2026-01-01 through the refresh date. The run created 39 records: 11 NFP, 10 CPI, 11 PPI, and 7 FOMC. FRED returned 32 BLS records across 9 paginated API pages. The Federal Reserve parser returned 7 historical FOMC events.

Yahoo Finance through `yfinance` returned 13,730 hourly `GC=F` rows and 219 daily rows. All 39 current-window records used the hourly primary measure because the events fall within Yahoo’s approximately 730-day hourly history limit. The daily fallback is implemented and covered by a deterministic unit test; it will be used automatically when a longer history is configured or hourly observations are missing.

## Deviations from the prompt

The free Yahoo symbol `XAUUSD=X` returned no usable price data in this run. Phase 2 therefore uses `GC=F`, Yahoo’s COMEX gold futures front-month symbol, as a clearly labeled gold-price proxy. This is not spot XAUUSD and must not be described as spot data. A future phase may add a second free source only if it can be verified reliably without silently changing the historical basis.

The initial history window is the current calendar year. This keeps the broad, paginated FRED release-date endpoint bounded on a free tier. The window is configurable in `data/release_config.json`; extending it increases API requests and may add older records that use the daily fallback.

Leading indicators and model scores remain null by design. Phase 2 builds the reaction database only; Phase 3 will add the indicator pipeline and signal score.

No live website URL or user GitHub repository is claimed. The project remains in Manus-managed Git and has not been published.

## References

- [FRED release dates API documentation](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html)
- [Federal Reserve FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
- [Yahoo Finance GC=F history](https://finance.yahoo.com/quote/GC=F/history)
