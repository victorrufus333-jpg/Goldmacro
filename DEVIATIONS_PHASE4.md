# Gold Macro Signal — Phase 4 Deviations Report

Generated after the Phase 4 implementation checks.

## What works

The site now includes Track Record and Release Detail views. Calendar rows link to release details, which show the signal state, score, FRED vintage cutoff, indicator evidence, post-release reaction, and historical N/win-rate context.

The public ledger is split into three generated files:

- `data/locked_signals.json` contains only live signals captured during `locked_pre_release`.
- `data/track_record.json` appends a locked signal only after a completed reaction is available and grades it WIN, LOSS, or UNSURE-skipped.
- `data/chained_cases.json` pairs consecutive immutable records within 45 days and reports separate chain N and win rate.

Existing records are never rewritten. A locked-signal conflict for an existing event ID stops the capture script instead of silently changing history. Historical Phase 3 reconstructions are deliberately excluded from the public ledger.

The daily workflow now refreshes the calendar, historical gold reactions, and signals, then runs lock capture, post-release grading, and chain generation. A separate lightweight workflow runs at four UTC times to cover the one-hour lock window for 08:30 ET BLS releases and 14:00 ET FOMC releases across New York daylight-saving schedules. When no lock is captured, it restores generated timestamp files and avoids a noisy commit.

## Current result

The public ledger is currently empty: zero live locked snapshots, zero immutable track-record entries, and zero chained cases. This is expected because the existing 13 upcoming records are `candidate_before_lock`, and the 39 historical records are `historical_reconstruction`. The system does not backfill them into the immutable public record.

The empty state is displayed clearly on the Track Record page. It is not presented as a 0% win rate and it is not substituted with the Phase 3 reconstructed statistics.

## Remaining deviations

A live locked record will only be captured when GitHub Actions starts successfully inside the final 60-minute window. GitHub-hosted schedules can be delayed, so the workflow also supports manual dispatch. If the workflow misses the window, no public record is created; the system prefers an empty ledger to an invented lock timestamp.

Automatic post-release grading depends on the historical gold reaction pipeline successfully obtaining a usable `GC=F` reaction. Missing or flat reactions remain UNSURE-skipped. The gold source remains the free COMEX futures proxy, not spot XAUUSD.

The release-detail view currently supports the query form `?view=release&id=...` and declares the dynamic `/release/:id` route for compatible static hosts. A dedicated Methodology page, production deployment integration, and more extensive ledger filtering remain later work.

## Phone-friendly owner steps

1. Keep `FRED_API_KEY` in the GitHub Actions repository secret only.
2. Use the daily **Refresh macro calendar and signals** workflow for the normal refresh.
3. Let the scheduled **Capture locked pre-release signal** workflow run; use manual dispatch only when you understand that a manual run outside the lock window will not create a public record.
4. Open **Track Record** to distinguish immutable live calls from Phase 3 research reconstructions.
5. Open a calendar event to inspect its Release Detail evidence before relying on any result.

## References

[1]: https://fred.stlouisfed.org/docs/api/fred/series_observations.html "FRED series observations API documentation"
[2]: https://fred.stlouisfed.org/docs/api/fred/realtime_period.html "FRED real-time periods and vintage dates"
[3]: https://finance.yahoo.com/quote/GC=F/history "Yahoo Finance GC=F historical data"
