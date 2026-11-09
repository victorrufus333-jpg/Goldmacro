# Phase 1 Deviations Report

## What works

The static mobile-first site is implemented with Home, Calendar, and Status views. It displays ET and WAT times, keeps the Phase 1 boundary visible, and carries the required educational disclaimer. The route manifest is served at `/manus-routes.json`, and the static build produces `dist/` with route copies for `/calendar/` and `/status/`.

The shared calendar configuration contains all four requested release types. NFP, CPI, and PPI use the same FRED release-date pipeline with verified release IDs. FOMC uses the same event-normalization path and converts the second day of each published meeting range into the 2:00 PM ET statement event.

The GitHub Actions workflow runs daily and supports manual dispatch. Source failures preserve prior source-specific records and make the source stale or unavailable instead of publishing an empty replacement. JSON writes are atomic.

## Source results in this Phase 1 run

The Federal Reserve calendar fetch and parser worked. It produced 16 calendar records covering the published 2026 and 2027 meeting schedules, with ET and WAT timestamps.

FRED was not queried because `FRED_API_KEY` is not configured in this environment. Therefore NFP, CPI, and PPI have no generated calendar records yet, and Status correctly shows FRED as unavailable. This is an intentional data-honesty state, not a failed implementation.

The FRED API endpoint, release IDs, and response fields were checked against the official FRED documentation. The Federal Reserve calendar markup was checked against the official calendar page.

## Deviations from the prompt

The live website URL and GitHub repository requested in the final deliverables are not claimed in Phase 1. The project is saved in Manus-managed Git, but no user GitHub repository has been connected and no publication was requested.

The FRED-backed NFP, CPI, and PPI records cannot be populated until the owner adds the free FRED API key as a GitHub Actions secret. The site intentionally shows “NOT AVAILABLE” for those lanes rather than using a fallback source or guessed dates.

Signals, leading indicators, win rates, gold-price reactions, locking, grading, track record, release detail, methodology, and chaining are not implemented because the prompt requires those to wait for later phases.

## Phone-friendly owner action

Open the repository in GitHub on the phone. Go to **Settings → Secrets and variables → Actions → New repository secret**. Add a secret named `FRED_API_KEY`. Then open **Actions → Refresh macro calendar → Run workflow**. After the run completes, open the site’s **Status** page. FRED should no longer be marked unavailable if the key is valid.

## References

- [FRED release list documentation](https://fred.stlouisfed.org/docs/api/fred/releases.html)
- [FRED release dates documentation](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html)
- [Federal Reserve FOMC calendar](https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
