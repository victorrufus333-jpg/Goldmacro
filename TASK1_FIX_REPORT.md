# Task 1 Fix Report — 2027 Calendar Coverage

Date: 2026-11-14

## Result

Task 1 is complete. The calendar now automatically combines:

- FRED release-date data with pagination and descending ordering.
- Official BLS schedule pages for future NFP, CPI, and PPI dates.
- The Federal Reserve FOMC calendar, with the existing manual fallback.

No future dates are hardcoded into the calendar pipeline, and there is no one-year calendar filter that removes 2027.

## Live refresh result

The authenticated refresh completed successfully.

- Total generated calendar events: 58
- FRED records fetched: 3
- Official BLS schedule records parsed: 42
- Federal Reserve meetings parsed: 16
- 12-month coverage status: `ok`

Verified 2027 records now present:

- NFP: 12 dates, from 2027-01-08 through 2027-12-03
- CPI: 12 dates, from 2027-01-13 through 2027-12-10
- PPI: 12 dates, from 2027-01-14 through 2027-12-15
- FOMC: 8 meeting dates, from 2027-01-27 through 2027-11-17

The exact generated source details are in `data/status.json` and the event records are in `data/calendar.json`.

## Implemented changes

### FRED pagination

`scripts/update_calendar.py` now:

- Requests FRED in descending release-date order.
- Follows the API `count`, `limit`, and `offset` fields.
- Records the number of pages fetched in source metadata.
- Does not treat the first 1,000 all-release rows as the complete calendar.

### Official BLS schedules

The pipeline now fetches and parses the official pages:

- https://www.bls.gov/schedule/news_release/empsit.htm
- https://www.bls.gov/schedule/news_release/cpi.htm
- https://www.bls.gov/schedule/news_release/ppi.htm

The parser uses Python’s standard library only. It retries transient fetch failures and extracts the published release date from the schedule table. The source is shown separately as `BLS schedules` on the Status page.

When the same release date exists in both sources, FRED provenance is retained. BLS supplies future dates that FRED has not yet published through the tested API response.

### 12-month coverage check

A new `calendar_coverage` status entry checks every release type for at least one verified date within the next 365 days. If any lane has no date, the status becomes `failure` and identifies the missing release type. The Status page displays this check.

## Validation completed

- Python compilation passed for `scripts/update_calendar.py` and `scripts/build_static.py`.
- JavaScript syntax check passed for `site/app.js`.
- Focused table-parser and coverage-failure unit checks passed.
- Live FRED, BLS, and Federal Reserve refresh passed.
- All four release types have verified 2027 dates.
- Static build completed successfully with 23 files/directories.
- Status, calendar, and generated JSON outputs were rebuilt.

## Honest limitations

- FRED did not provide the 2027 BLS dates in the tested release-date response. Those dates are therefore sourced from the official BLS schedules and labeled accordingly.
- BLS pages may change their HTML layout or temporarily reject requests. The pipeline retries, marks the BLS source unavailable/stale when necessary, keeps prior verified BLS events when available, and exposes the failure on Status.
- The refresh workflow will regenerate Phase 3 signals after the calendar refresh. This Task 1 change does not silently fabricate signals for newly discovered future dates.

## Task boundary

Task 2 has not started. The next task is the confidence/conviction research extension: reliability statistics, correlation and p-values, data-derived weights, similar-case analysis, walk-forward validation, and confidence calibration. It requires separate approval after this Task 1 report.
