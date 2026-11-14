#!/usr/bin/env python3
"""Refresh verified release dates while preserving old data on source failure."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG_PATH = DATA / "release_config.json"
CALENDAR_PATH = DATA / "calendar.json"
STATUS_PATH = DATA / "status.json"
FOMC_FALLBACK_PATH = DATA / "fomc_dates.json"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
USER_AGENT = "GoldMacroSignal/1.0 (calendar refresh; contact owner through repository)"


class SourceError(RuntimeError):
    pass


def read_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def fetch_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=45) as response:
                if response.status < 200 or response.status >= 300:
                    raise SourceError(f"HTTP {response.status}")
                return response.read()
        except Exception as exc:  # urllib errors are deliberately rendered as source status, not hidden.
            last_error = exc
            if attempt < 2:
                continue
    raise SourceError(str(last_error)) from last_error


def fetch_json(url: str) -> dict:
    try:
        return json.loads(fetch_bytes(url).decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise SourceError(f"invalid JSON response: {exc}") from exc


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SourceError(f"invalid release date: {value}") from exc


def event_record(release: dict, event_date: date, *, source_name: str, source_url: str, source_kind: str, raw_label: str | None = None) -> dict:
    et_zone = ZoneInfo("America/New_York")
    wat_zone = ZoneInfo("Africa/Lagos")
    time_text = release["release_time_et"]
    hour, minute = (int(part) for part in time_text.split(":", 1))
    local_et = datetime(event_date.year, event_date.month, event_date.day, hour, minute, tzinfo=et_zone)
    return {
        "id": f"{release['id']}-{event_date.isoformat()}",
        "release_type": release["id"],
        "label": release["label"],
        "name": release["name"],
        "date": event_date.isoformat(),
        "time_et": time_text,
        "times": {
            "et": local_et.isoformat(),
            "wat": local_et.astimezone(wat_zone).isoformat(),
        },
        "source": {
            "name": source_name,
            "url": source_url,
            "kind": source_kind,
        },
        "raw_label": raw_label or release["name"],
    }


def fred_events(config: dict, now: date) -> tuple[list[dict], dict]:
    key = os.environ.get("FRED_API_KEY", "").strip()
    source = config["sources"]["fred_releases"]
    if not key:
        raise SourceError("FRED_API_KEY is not configured")

    params = {
        "api_key": key,
        "file_type": "json",
        "realtime_start": now.isoformat(),
        "realtime_end": f"{now.year + 1}-12-31",
        "include_release_dates_with_no_data": "true",
        "limit": "1000",
        "order_by": "release_date",
        "sort_order": "desc",
    }
    rows: list[dict] = []
    offset = 0
    page_count = 0
    while True:
        page_params = {**params, "offset": str(offset)}
        payload = fetch_json(source["url"] + "?" + urllib.parse.urlencode(page_params))
        page = payload.get("release_dates")
        if not isinstance(page, list):
            raise SourceError("FRED response has no release_dates list")
        rows.extend(item for item in page if isinstance(item, dict))
        page_count += 1
        count_value = payload.get("count")
        total = int(count_value) if isinstance(count_value, (int, str)) else len(rows)
        limit_value = params["limit"]
        page_limit = int(limit_value) if isinstance(limit_value, str) else 1000
        if not page or len(rows) >= total or len(page) < page_limit:
            break
        offset += len(page)

    releases = [item for item in config["releases"] if item["source_key"] == "fred_releases"]
    by_id = {int(item["fred_release_id"]): item for item in releases}
    events: list[dict] = []
    for row in rows:
        try:
            release_id_value = row.get("release_id")
            release = by_id.get(int(release_id_value)) if isinstance(release_id_value, (int, str)) else None
            if not release or not row.get("date"):
                continue
            event_date = parse_iso_date(str(row["date"]))
            events.append(event_record(release, event_date, source_name=source["name"], source_url=source["url"], source_kind="fred_api", raw_label=str(row.get("release_name") or release["name"])))
        except (TypeError, ValueError, SourceError):
            continue

    if not events:
        raise SourceError("FRED returned no verified NFP, CPI, or PPI release dates; prior data kept")
    return events, {"records": len(events), "pages": page_count, "request_url": source["url"]}


class TableParser(HTMLParser):
    """Collect table cell text without adding a third-party parser dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(re.sub(r"\s+", " ", unescape("".join(self._cell))).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def bls_schedule_events(config: dict) -> tuple[list[dict], dict]:
    source = config["sources"]["bls_schedules"]
    releases = {item["id"]: item for item in config["releases"] if item["id"] in {"nfp", "cpi", "ppi"}}
    date_pattern = re.compile(r"^([A-Za-z]+)\.?\s+(\d{1,2}),\s+(\d{4})$")
    month_formats = ("%b %d %Y", "%B %d %Y")
    events: list[dict] = []
    for release_id, release in releases.items():
        url = source["urls"][release_id]
        parser = TableParser()
        parser.feed(fetch_bytes(url).decode("utf-8", "replace"))
        found = 0
        for cells in parser.rows:
            if len(cells) < 3:
                continue
            match = date_pattern.match(cells[1])
            if not match:
                continue
            event_date = None
            date_text = f"{match.group(1)} {match.group(2)} {match.group(3)}"
            for date_format in month_formats:
                try:
                    event_date = datetime.strptime(date_text, date_format).date()
                    break
                except ValueError:
                    continue
            if event_date is None:
                continue
            events.append(event_record(release, event_date, source_name=source["name"], source_url=url, source_kind="bls_schedule", raw_label=cells[0]))
            found += 1
        if found == 0:
            raise SourceError(f"BLS schedule contained no recognized {release_id} dates")
    return events, {"records": len(events), "request_url": source["urls"]}


def coverage_status(config: dict, events: list[dict], now: date, checked_at: str) -> dict:
    horizon = now + timedelta(days=365)
    missing: list[str] = []
    counts: dict[str, int] = {}
    for release in config["releases"]:
        dates = {parse_iso_date(str(item["date"])) for item in events if item.get("release_type") == release["id"] and item.get("date")}
        count = sum(now <= item <= horizon for item in dates)
        counts[release["id"]] = count
        if count == 0:
            missing.append(release["label"])
    source = config["sources"]["calendar_coverage"]
    state = "failure" if missing else "ok"
    detail = f"Upcoming dates within 12 months by release: {counts}." if not missing else f"No upcoming verified date within 12 months for: {', '.join(missing)}."
    return status_record(source=source, state=state, checked_at=checked_at, detail=detail, records=sum(counts.values()), mode="automatic_check")


def strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", " ", unescape(value)).strip()


def live_fomc_events(config: dict, now: date, years: set[int] | None = None) -> tuple[list[dict], dict]:
    source = config["sources"]["federal_reserve_fomc"]
    html = fetch_bytes(source["url"]).decode("utf-8", "replace")
    years = years or {now.year, now.year + 1}
    block_pattern = re.compile(
        r'<div class="panel panel-default">\s*<div class="panel-heading"><h4><a[^>]*>\s*(20\d{2}) FOMC Meetings\s*</a></h4></div>(.*?)(?=<div class="panel panel-default">|\Z)',
        re.S,
    )
    pair_pattern = re.compile(
        r'<div[^>]*class="[^"]*fomc-meeting__month[^"]*"[^>]*>.*?<strong>\s*([^<]+?)\s*</strong>.*?'
        r'<div[^>]*class="[^"]*fomc-meeting__date[^"]*"[^>]*>\s*([^<]+?)\s*</div>',
        re.S,
    )
    month_numbers = {name: number for number, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
    fomc_release = next(item for item in config["releases"] if item["id"] == "fomc")
    events: list[dict] = []
    for year_text, block in block_pattern.findall(html):
        year = int(year_text)
        if year not in years:
            continue
        for month_text, range_text in pair_pattern.findall(block):
            month = month_numbers.get(strip_tags(month_text))
            days = [int(item) for item in re.findall(r"\d+", range_text)]
            if not month or not days:
                continue
            event_date = date(year, month, days[-1])
            events.append(event_record(fomc_release, event_date, source_name=source["name"], source_url=source["url"], source_kind="federal_reserve_live", raw_label=f"{strip_tags(month_text)} {range_text.strip()} {year}"))
    if not events:
        raise SourceError("Federal Reserve page did not yield a recognized FOMC meeting table")
    return events, {"records": len(events), "request_url": source["url"]}


def fallback_fomc_events(config: dict) -> tuple[list[dict], dict]:
    source = config["sources"]["federal_reserve_fomc"]
    fallback = read_json(FOMC_FALLBACK_PATH, {})
    dates = fallback.get("dates") if isinstance(fallback, dict) else None
    if not isinstance(dates, list) or not dates:
        raise SourceError("data/fomc_dates.json has no dates")
    release = next(item for item in config["releases"] if item["id"] == "fomc")
    events: list[dict] = []
    for row in dates:
        if not isinstance(row, dict) or not row.get("date"):
            continue
        try:
            event_date = parse_iso_date(str(row["date"]))
            release_copy = dict(release)
            release_copy["release_time_et"] = str(row.get("time_et") or release["release_time_et"])
            events.append(event_record(release_copy, event_date, source_name=source["name"], source_url=str(row.get("source_url") or source["url"]), source_kind="manual_fallback", raw_label=str(row.get("label") or release["name"])))
        except SourceError:
            continue
    if not events:
        raise SourceError("data/fomc_dates.json has no valid dates")
    return events, {"records": len(events), "request_url": source["url"], "fallback_file": "data/fomc_dates.json"}


def status_record(*, source: dict, state: str, checked_at: str, detail: str, records: int = 0, mode: str | None = None) -> dict:
    record = {
        "name": source["name"],
        "url": source["url"],
        "state": state,
        "last_checked": checked_at,
        "records": records,
        "detail": detail,
    }
    if mode:
        record["mode"] = mode
    return record


def main() -> int:
    config = read_json(CONFIG_PATH, {})
    if not isinstance(config, dict) or not config.get("releases"):
        print("release_config.json is missing or invalid", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    today = now.date()
    checked_at = now.isoformat()
    old_calendar = read_json(CALENDAR_PATH, {})
    if not isinstance(old_calendar, dict):
        old_calendar = {}
    raw_events = old_calendar.get("events")
    old_events: list[dict] = [item for item in raw_events if isinstance(item, dict)] if isinstance(raw_events, list) else []
    events_by_source = {
        "fred_releases": [item for item in old_events if item.get("source", {}).get("kind") == "fred_api"],
        "bls_schedules": [item for item in old_events if item.get("source", {}).get("kind") == "bls_schedule"],
        "federal_reserve_fomc": [item for item in old_events if item.get("release_type") == "fomc"],
    }
    sources = config["sources"]
    source_status: dict[str, dict] = {}

    try:
        events, info = fred_events(config, today)
        events_by_source["fred_releases"] = events
        source_status["fred_releases"] = status_record(source=sources["fred_releases"], state="ok", checked_at=checked_at, detail=f"Fetched {info['records']} verified release-date records from FRED.", records=info["records"], mode="live")
    except SourceError as exc:
        had_old = bool(events_by_source["fred_releases"])
        source_status["fred_releases"] = status_record(source=sources["fred_releases"], state="stale" if had_old else "unavailable", checked_at=checked_at, detail=f"{exc}. {'Prior FRED events were kept.' if had_old else 'No FRED events are available.'}", records=len(events_by_source["fred_releases"]), mode="unavailable")

    try:
        events, info = bls_schedule_events(config)
        events_by_source["bls_schedules"] = events
        source_status["bls_schedules"] = status_record(source=sources["bls_schedules"], state="ok", checked_at=checked_at, detail=f"Parsed {info['records']} official BLS NFP, CPI, and PPI schedule records.", records=info["records"], mode="live")
    except SourceError as exc:
        had_old = bool(events_by_source["bls_schedules"])
        source_status["bls_schedules"] = status_record(source=sources["bls_schedules"], state="stale" if had_old else "unavailable", checked_at=checked_at, detail=f"{exc}. {'Prior BLS schedule events were kept.' if had_old else 'No BLS schedule events are available.'}", records=len(events_by_source["bls_schedules"]), mode="unavailable")

    try:
        events, info = live_fomc_events(config, today)
        events_by_source["federal_reserve_fomc"] = events
        source_status["federal_reserve_fomc"] = status_record(source=sources["federal_reserve_fomc"], state="ok", checked_at=checked_at, detail=f"Parsed {info['records']} meetings from the official Federal Reserve page.", records=info["records"], mode="live")
    except SourceError as exc:
        try:
            events, info = fallback_fomc_events(config)
            events_by_source["federal_reserve_fomc"] = events
            source_status["federal_reserve_fomc"] = status_record(source=sources["federal_reserve_fomc"], state="fallback", checked_at=checked_at, detail=f"Live calendar parsing failed: {exc}. Loaded {info['records']} dates from data/fomc_dates.json.", records=info["records"], mode="manual_fallback")
        except SourceError as fallback_exc:
            had_old = bool(events_by_source["federal_reserve_fomc"])
            source_status["federal_reserve_fomc"] = status_record(source=sources["federal_reserve_fomc"], state="stale" if had_old else "unavailable", checked_at=checked_at, detail=f"Live parsing failed: {exc}. Manual fallback failed: {fallback_exc}. {'Prior FOMC events were kept.' if had_old else 'No FOMC events are available.'}", records=len(events_by_source["federal_reserve_fomc"]), mode="unavailable")

    unique_events: dict[tuple[str, str], dict] = {}
    for event in events_by_source["bls_schedules"] + events_by_source["fred_releases"] + events_by_source["federal_reserve_fomc"]:
        key = (str(event.get("release_type", "")), str(event.get("date", "")))
        # FRED remains the preferred provenance when it has the same date; BLS fills future dates FRED has not published.
        if key not in unique_events or event.get("source", {}).get("kind") == "fred_api":
            unique_events[key] = event
    merged_events = sorted(unique_events.values(), key=lambda item: (item.get("date", ""), item.get("time_et", ""), item.get("release_type", "")))
    source_status["calendar_coverage"] = coverage_status(config, merged_events, today, checked_at)
    calendar = {
        "schema_version": 1,
        "generated_at": checked_at,
        "events": merged_events,
        "source_status": source_status,
    }
    prior_status = read_json(STATUS_PATH, {})
    prior_sources = prior_status.get("sources") if isinstance(prior_status, dict) else {}
    retained_sources = {key: value for key, value in prior_sources.items() if key not in {"fred_releases", "bls_schedules", "federal_reserve_fomc", "calendar_coverage"}} if isinstance(prior_sources, dict) else {}
    status = {
        "schema_version": 1,
        "generated_at": checked_at,
        "sources": {**retained_sources, **source_status},
    }
    write_json_atomic(CALENDAR_PATH, calendar)
    write_json_atomic(STATUS_PATH, status)
    print(json.dumps({"generated_at": checked_at, "events": len(merged_events), "sources": source_status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
