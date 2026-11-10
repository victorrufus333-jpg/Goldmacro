# Gold Macro Signal — Phase 3 Deviations Report

Generated after the successful Phase 3 run on 2026-11-10.

## What works

The Phase 3 engine now retrieves 15 verified FRED indicator series through the series-observations endpoint. It requests vintage-date output and uses the calendar day before each historical release as the information cutoff. For upcoming events, it uses the latest completed provider day rather than requesting a future FRED vintage.

The configured rules cover NFP, CPI, PPI, and FOMC. Each vote records the series ID, label, method, lookback, threshold, direction, observation date, prior observation, delta, vintage date, staleness, units, and source URL. The engine does not forward-fill a missing observation.

The score engine returns BUY at score `>= 2`, SELL at score `<= -2`, and UNSURE when fewer than three votes are usable, more than 40% of the configured indicators are missing or stale, or the score does not clear either threshold. Upcoming events expose `candidate_before_lock`; the signal becomes `locked_pre_release` only inside the final 60 minutes before the release and becomes `released` afterward.

Historical records now contain leading-indicator votes, model score, signal, vintage date, signal state, grade, and historical context. The generated files are `data/signals.json` and the updated `data/historical_reactions.json`.

## Phase 3 run results

The run retrieved all 15 of 15 configured indicator series with no source errors. It built 39 historical reconstructions and 13 upcoming records. Across all 52 records, the signal distribution was 22 BUY, 3 SELL, and 27 UNSURE. The 13 upcoming records are all still before their lock windows at the time of this run.

For the 39 historical records, the result was 19 BUY, 2 SELL, and 18 UNSURE. Grading against the existing 60-minute `GC=F` reaction produced 9 WIN, 12 LOSS, and 18 UNSURE-skipped cases. UNSURE-skipped cases are excluded from `N`; they are not counted as losses.

The historical research context by release type is:

- CPI: `N=9`, 3 wins, 6 losses, 33.3% win rate, 1 skipped.
- PPI: `N=8`, 5 wins, 3 losses, 62.5% win rate, 3 skipped.
- NFP: `N=4`, 1 win, 3 losses, 25.0% win rate, 7 skipped.
- FOMC: `N=0`, no win rate reported, 7 skipped. The configured FOMC rules did not produce a directional BUY or SELL that cleared the thresholds in this window.

The next current calendar candidate at run time was CPI with BUY, score 3, and historical context `N=9` with a 33.3% research win rate. It was not locked yet. Candidate signals can change before the final 60-minute lock.

## Indicator verification deviations

The suggested series IDs that were valid and used include `PAYEMS`, `UNRATE`, `CES0500000003`, `ICSA`, `JTSJOL`, `CPIAUCSL`, `CPILFESL`, `DCOILWTICO`, `GASREGW`, `PCEPI`, `PCEPILFE`, and `FEDFUNDS`. Phase 3 also uses verified current series `PPIFIS`, `PPIFES`, `IR`, `DGS2`, and `SOFR`.

The candidate ID `PPIFGS` was found but is discontinued with observations ending in 2015, so it was not used. The candidate `IMPUSCC1` failed the FRED series lookup; a FRED search identified `IR` — Import Price Index, All Commodities — as the current series used for the import-price rule. These substitutions are recorded here instead of being silent.

## Limitations and remaining deviations

The rules are transparent heuristics, not a fitted or independently validated trading model. Thresholds and gold-bias directions are configuration choices. The current grades are research statistics over the available 2026 window and are not proof of future performance.

FRED vintage dates reduce revision leakage, but they do not provide a licensed real-time economist-consensus feed or guarantee that the exact release-time information set is reconstructed. The prior-day cutoff is deliberately conservative and may omit information published earlier on the same release day.

Gold grading uses Yahoo `GC=F`, a COMEX gold-futures front-month proxy, because free Yahoo `XAUUSD=X` data was unavailable in Phase 2. It is not spot XAUUSD and should not be presented as spot performance.

The public immutable track record, automatic post-release grading commit, complete release-detail pages, methodology page, release chaining, and production GitHub deployment remain later phases. This Phase 3 output is generated JSON and a phone-friendly dashboard, not financial advice.

## Phone-friendly owner steps

1. Keep `FRED_API_KEY` only in the GitHub Actions repository secret. Never paste it into `data/release_config.json` or another tracked file.
2. Run the daily workflow from the GitHub mobile app or phone browser when you want a fresh calendar, history, and signal snapshot.
3. Open the site and check **Status**. `FRED indicators` and `Signal engine` should be green before relying on any candidate signal.
4. Treat `UNSURE` as a real outcome. Do not edit JSON to force a BUY or SELL.
5. Remember that a candidate signal is not locked until the final 60 minutes before the verified release time.

## References

[1]: https://fred.stlouisfed.org/docs/api/fred/series_observations.html "FRED series observations API documentation"
[2]: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html "FRED real-time periods and vintage dates"
[3]: https://finance.yahoo.com/quote/GC=F/history "Yahoo Finance GC=F historical data"
