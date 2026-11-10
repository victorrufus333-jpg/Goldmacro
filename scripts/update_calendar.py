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
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            if response.status < 200 or response.status >= 300:
                raise SourceError(f"HTTP {response.status}")
            return response.read()
    except Exception as exc:  # urllib errors are deliberately rendered as source status, not hidden.
        raise SourceError(str(exc)) from exc


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
        "sort_order": "asc",
    }
    url = source["url"] + "?" + urllib.parse.urlencode(params)
    payload = fetch_json(url)
    rows = payload.get("release_dates")
    if not isinstance(rows, list):
        raise SourceError("FRED response has no release_dates list")

    releases = [item for item in config["releases"] if item["source_key"] == "fred_releases"]
    by_id = {int(item["fred_release_id"]): item for item in releases}
    events: list[dict] = []
    for row in rows:
        try:
            release = by_id.get(int(row.get("release_id")))
            if not release or not row.get("date"):
                continue
            event_date = parse_iso_date(str(row["date"]))
            events.append(event_record(release, event_date, source_name=source["name"], source_url=source["url"], source_kind="fred_api", raw_label=str(row.get("release_name") or release["name"])))
        except (TypeError, ValueError, SourceError):
            continue

    if not events:
        raise SourceError("FRED returned no verified NFP, CPI, or PPI release dates; prior data kept")
    return events, {"records": len(events), "request_url": source["url"]}


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

    merged_events = sorted(events_by_source["fred_releases"] + events_by_source["federal_reserve_fomc"], key=lambda item: (item.get("date", ""), item.get("time_et", ""), item.get("release_type", "")))
    calendar = {
        "schema_version": 1,
        "generated_at": checked_at,
        "events": merged_events,
        "source_status": source_status,
    }
    prior_status = read_json(STATUS_PATH, {})
    prior_sources = prior_status.get("sources") if isinstance(prior_status, dict) else {}
    retained_sources = {key: value for key, value in prior_sources.items() if key not in {"fred_releases", "federal_reserve_fomc"}} if isinstance(prior_sources, dict) else {}
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
