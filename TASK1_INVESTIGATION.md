# Task 1 Investigation — 2027 NFP, CPI, and PPI Dates

Investigation date: 2026-11-14

No project code, data, or workflows were changed during this investigation.

## 1. What I found

The root cause is confirmed: the current FRED calendar request is not a reliable future-calendar source for these three BLS release lanes, and the current implementation also uses a bounded, ascending all-release response without pagination.

The current code at `scripts/update_calendar.py:108-118` sends the FRED **plural** endpoint `/fred/releases/dates` with:

- `include_release_dates_with_no_data=true`
- `realtime_start=today`
- `realtime_end=next year December 31`
- `limit=1000`
- `order_by=release_date`
- `sort_order=asc`
- no `offset` pagination

The official FRED documentation says the plural endpoint returns dates for **all releases**, and that `include_release_dates_with_no_data=true` includes future dates when the source has published them. It also documents a maximum `limit` of 1000 and an `offset` parameter. See [FRED release-dates API documentation](https://fred.stlouisfed.org/docs/api/fred/releases_dates.html).

Two separate problems are therefore present:

1. The current ascending first page stops at the first 1,000 rows. The response reported `count=1332`, so rows beyond the first page are omitted. The second page contains later dates, proving pagination matters.
2. Even after using descending order or the second page, the 2027 rows returned by the all-release endpoint are for other FRED releases such as Ramp AI Index, Database of Global Economic Indicators, Manufactured Housing Survey, and others—not release IDs 50, 10, or 46. The `release_id` query parameter supplied to the plural endpoint did not filter that endpoint’s response.

The FRED release-specific endpoint was also tested. It returned only one known future date for Employment Situation, `2026-12-04`, and no 2027 dates. This means FRED had not exposed the 2027 BLS dates through the tested release-date API response at the time of investigation.

There is no current code filter that explicitly removes 2027. `fred_events()` does not filter by year after parsing. The `realtime_end` bound includes 2027. The `history.start_date` setting in `data/release_config.json` is used by the historical reaction pipeline, not by the calendar parser. FOMC works separately because it is parsed from the Federal Reserve calendar with `years={current year, current year + 1}`.

## 2. Raw FRED evidence

The API key is intentionally redacted. The requests below are the exact requests used, with only the secret value replaced by `[REDACTED]`.

### Current implementation shape — all-release endpoint

```text
https://api.stlouisfed.org/fred/releases/dates?api_key=[REDACTED]&file_type=json&realtime_start=2026-11-14&realtime_end=2027-12-31&include_release_dates_with_no_data=true&limit=1000&order_by=release_date&sort_order=asc
```

Raw response metadata:

```json
{
  "count": 1332,
  "offset": 0,
  "limit": 1000,
  "order_by": "release_date",
  "sort_order": "asc"
}
```

The first page contained zero rows dated in 2027 for release IDs 50, 10, or 46.

### Same all-release endpoint, descending order

```text
https://api.stlouisfed.org/fred/releases/dates?api_key=[REDACTED]&file_type=json&realtime_start=2026-11-14&realtime_end=2027-12-31&include_release_dates_with_no_data=true&limit=1000&order_by=release_date&sort_order=desc
```

Raw response metadata:

```json
{
  "count": 1332,
  "offset": 0,
  "limit": 1000,
  "order_by": "release_date",
  "sort_order": "desc"
}
```

This response contained 37 rows dated in 2027, but none had release IDs 50, 10, or 46. The 2027 rows were other releases, including Ramp AI Index, Database of Global Economic Indicators, Manufactured Housing Survey, Texas Employment Data, and others.

### All-release endpoint, second page

```text
https://api.stlouisfed.org/fred/releases/dates?api_key=[REDACTED]&file_type=json&realtime_start=2026-11-14&realtime_end=2027-12-31&include_release_dates_with_no_data=true&limit=1000&offset=1000&order_by=release_date&sort_order=asc
```

Raw response metadata:

```json
{
  "count": 1332,
  "offset": 1000,
  "limit": 1000,
  "order_by": "release_date",
  "sort_order": "asc"
}
```

This page contained 37 rows dated in 2027, but again none had release IDs 50, 10, or 46.

### Release-specific endpoint — Employment Situation

```text
https://api.stlouisfed.org/fred/release/dates?api_key=[REDACTED]&file_type=json&release_id=50&realtime_start=2026-11-14&realtime_end=2027-12-31&include_release_dates_with_no_data=true&limit=1000&order_by=release_date&sort_order=desc
```

Raw response:

```json
{
  "realtime_start": "2026-11-14",
  "realtime_end": "2027-12-31",
  "order_by": "release_date",
  "sort_order": "desc",
  "count": 1,
  "offset": 0,
  "limit": 1000,
  "release_dates": [
    {
      "release_id": 50,
      "date": "2026-12-04"
    }
  ]
}
```

The equivalent release-specific requests for CPI (`release_id=10`) and PPI (`release_id=46`) also returned `count=1` and no 2027 date in the response.

## 3. Official BLS evidence

The official BLS schedules show that 2027 dates are already published.

### Employment Situation / NFP

Source: [BLS Employment Situation schedule](https://www.bls.gov/schedule/news_release/empsit.htm)

- December 2026 reference month: January 8, 2027
- January 2027: February 5, 2027
- February 2027: March 5, 2027
- March 2027: April 2, 2027
- April 2027: May 7, 2027
- May 2027: June 4, 2027
- June 2027: July 2, 2027
- July 2027: August 6, 2027
- August 2027: September 3, 2027
- September 2027: October 8, 2027
- October 2027: November 5, 2027
- November 2027: December 3, 2027

### CPI

Source: [BLS Consumer Price Index schedule](https://www.bls.gov/schedule/news_release/cpi.htm)

- December 2026 reference month: January 13, 2027
- January 2027: February 11, 2027
- February 2027: March 10, 2027
- March 2027: April 13, 2027
- April 2027: May 12, 2027
- May 2027: June 10, 2027
- June 2027: July 14, 2027
- July 2027: August 11, 2027
- August 2027: September 14, 2027
- September 2027: October 14, 2027
- October 2027: November 10, 2027
- November 2027: December 10, 2027

### PPI

Source: [BLS Producer Price Index schedule](https://www.bls.gov/schedule/news_release/ppi.htm)

- December 2026 reference month: January 14, 2027
- January 2027: February 12, 2027
- February 2027: March 12, 2027
- March 2027: April 14, 2027
- April 2027: May 13, 2027
- May 2027: June 11, 2027
- June 2027: July 15, 2027
- July 2027: August 10, 2027
- August 2027: September 10, 2027
- September 2027: October 15, 2027
- October 2027: November 12, 2027
- November 2027: December 15, 2027

All three BLS schedules list the standard release time as 08:30 AM ET.

## 4. What I changed

Nothing. This was the required investigation-first step. No source files, generated data, configuration, or deployed site were modified.

## 5. What is not done or not possible yet

The fix has not been implemented because the supplied instructions require stopping after Task 1 investigation and waiting for owner approval.

A complete fix needs a source strategy decision in the next step. The evidence supports using the official BLS schedule as the future-date source for NFP, CPI, and PPI, while retaining FRED for the historical/release-date data path where appropriate. If the implementation keeps FRED as primary, it must still handle pagination and explicitly report that FRED has not published the 2027 BLS dates in the tested endpoint response.

The requested 12-month coverage check has not been added yet because it belongs to the Task 1 fix step.

## 6. Deviations

None. No implementation was performed.

## 7. Owner action

Reply `approved` to authorize the Task 1 fix. The next step will implement the evidence-based future-date handling, remove the year limitation, add the 12-month coverage check, run tests, and report the resulting files and outputs. Task 2 will not start until a separate `approved` reply after the Task 1 report.
