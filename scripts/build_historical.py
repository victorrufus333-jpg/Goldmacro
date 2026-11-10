#!/usr/bin/env python3
"""Build one historical release/reaction database for all configured releases."""
from __future__ import annotations

import json
import importlib
import os
import sys
import urllib.parse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

yf: Any = importlib.import_module("yfinance")

from update_calendar import (
    SourceError,
    event_record,
    fetch_json,
    live_fomc_events,
    parse_iso_date,
    read_json,
    write_json_atomic,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG_PATH = DATA / "release_config.json"
OUTPUT_PATH = DATA / "historical_reactions.json"
STATUS_PATH = DATA / "status.json"


def parse_config_date(value: str, field: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise SourceError(f"invalid {field}: {value}") from exc


def fred_history_events(config: dict, start: date, end: date) -> tuple[list[dict], dict]:
    """Fetch the documented FRED release-dates endpoint with bounded pagination."""
    source = config["sources"]["fred_releases"]
    key = os.environ.get("FRED_API_KEY", "").strip()
    if not key:
        raise SourceError("FRED_API_KEY is not configured")

    history_cfg = config.get("history", {})
    page_size = int(history_cfg.get("fred_page_size", 1000))
    max_pages = int(history_cfg.get("max_fred_pages", 20))
    params_base = {
        "api_key": key,
        "file_type": "json",
        "realtime_start": start.isoformat(),
        "realtime_end": end.isoformat(),
        "include_release_dates_with_no_data": "true",
        "limit": str(page_size),
        "order_by": "release_date",
        "sort_order": "asc",
    }
    target_releases = [item for item in config["releases"] if item["source_key"] == "fred_releases"]
    by_id = {int(item["fred_release_id"]): item for item in target_releases}
    rows_by_key: dict[tuple[int, str], dict] = {}
    offset = 0
    total: int | None = None
    pages = 0

    while total is None or offset < total:
        if pages >= max_pages:
            raise SourceError(f"FRED history requires more than {max_pages} pages; increase history.max_fred_pages explicitly")
        params = dict(params_base, offset=str(offset))
        url = source["url"] + "?" + urllib.parse.urlencode(params)
        payload = fetch_json(url)
        rows = payload.get("release_dates")
        if not isinstance(rows, list):
            raise SourceError("FRED historical response has no release_dates list")
        total = int(payload.get("count", offset + len(rows)))
        pages += 1
        for row in rows:
            try:
                release_id = int(row.get("release_id"))
                release = by_id.get(release_id)
                if not release or not row.get("date"):
                    continue
                event_date = parse_iso_date(str(row["date"]))
                if start <= event_date <= end:
                    rows_by_key[(release_id, event_date.isoformat())] = row
            except (TypeError, ValueError, SourceError):
                continue
        offset += len(rows)
        if not rows:
            break

    events: list[dict] = []
    for (release_id, _), row in sorted(rows_by_key.items(), key=lambda item: (item[0][1], item[0][0])):
        release = by_id[release_id]
        event_date = parse_iso_date(str(row["date"]))
        events.append(event_record(release, event_date, source_name=source["name"], source_url=source["url"], source_kind="fred_api_history", raw_label=str(row.get("release_name") or release["name"])))
    if not events:
        raise SourceError("FRED returned no historical NFP, CPI, or PPI records in the configured window")
    return events, {"records": len(events), "pages": pages, "count": total, "request_url": source["url"]}


def historical_fomc_events(config: dict, start: date, end: date) -> tuple[list[dict], dict]:
    years = set(range(start.year, end.year + 1))
    events, info = live_fomc_events(config, end, years=years)
    filtered = [event for event in events if start.isoformat() <= event["date"] <= end.isoformat()]
    if not filtered:
        raise SourceError("Federal Reserve calendar returned no FOMC events in the configured history window")
    return filtered, {**info, "records": len(filtered), "years": sorted(years)}


def close_series(frame: pd.DataFrame, symbol: str) -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype="float64")
    if isinstance(frame.columns, pd.MultiIndex):
        levels = [list(frame.columns.get_level_values(index)) for index in range(frame.columns.nlevels)]
        if symbol in levels[-1]:
            frame = frame.xs(symbol, axis=1, level=-1)
        elif symbol in levels[0]:
            frame = frame.xs(symbol, axis=1, level=0)
    if "Close" not in frame.columns:
        raise SourceError("Yahoo response has no Close column")
    close_column: Any = frame["Close"]
    series: pd.Series = pd.Series(pd.to_numeric(close_column, errors="coerce"), index=frame.index).dropna()
    index = pd.to_datetime(series.index, utc=True)
    series.index = index
    return series.sort_index()


def fetch_gold_history(config: dict, start: date, end: date) -> tuple[pd.Series, pd.Series, dict]:
    gold = config["gold_price"]
    symbol = gold["symbol"]
    retrieved_at = datetime.now(timezone.utc).isoformat()
    daily_start = (start - timedelta(days=7)).isoformat()
    daily_end = (end + timedelta(days=2)).isoformat()
    daily_frame = yf.download(symbol, start=daily_start, end=daily_end, interval=gold["daily_interval"], auto_adjust=False, actions=False, progress=False, threads=False)
    daily = close_series(daily_frame, symbol)

    hourly_days = int(gold.get("hourly_history_limit_days", 730))
    hourly_period = f"{hourly_days}d"
    hourly_frame = yf.download(symbol, period=hourly_period, interval=gold["hourly_interval"], auto_adjust=False, actions=False, progress=False, threads=False)
    hourly = close_series(hourly_frame, symbol)
    if daily.empty and hourly.empty:
        raise SourceError(f"Yahoo Finance returned no usable Close data for {symbol}")
    return hourly, daily, {
        "provider": gold["provider"],
        "symbol": symbol,
        "instrument_label": gold["instrument_label"],
        "source_url": gold["source_url"],
        "retrieved_at": retrieved_at,
        "adjustment": gold["adjustment"],
        "hourly_interval": gold["hourly_interval"],
        "daily_interval": gold["daily_interval"],
        "hourly_rows": int(len(hourly)),
        "daily_rows": int(len(daily)),
    }


def price_point(timestamp: Any, price: float) -> dict:
    return {"timestamp": timestamp.isoformat(), "price": float(price)}


def direction(change: float) -> str:
    if change > 0:
        return "up"
    if change < 0:
        return "down"
    return "flat"


def hourly_reaction(event: dict, hourly: pd.Series) -> dict | None:
    series: Any = pd.Series(hourly, dtype="float64")
    if series.empty:
        return None
    release = pd.Timestamp(event["times"]["et"]).tz_convert("UTC")
    target = release + pd.Timedelta(minutes=60)
    before = series[series.index < release]
    after = series[series.index >= target]
    if before.empty or after.empty:
        return None
    pre_time, pre_price = pd.Timestamp(before.index[-1]), float(before.iloc[-1])
    post_time, post_price = pd.Timestamp(after.index[0]), float(after.iloc[0])
    change = post_price - pre_price
    return {
        "measure": "hourly_60m",
        "definition": "Last Yahoo hourly Close timestamped before the release to the first Yahoo hourly Close timestamped at or after release + 60 minutes.",
        "pre_release": price_point(pre_time, pre_price),
        "post_release": price_point(post_time, post_price),
        "change": change,
        "return_pct": (change / pre_price * 100) if pre_price else None,
        "direction": direction(change),
        "interval": "1h",
    }


def daily_reaction(event: dict, daily: pd.Series) -> dict | None:
    series: pd.Series = pd.Series(daily, dtype="float64")
    if series.empty:
        return None
    release_date = date.fromisoformat(event["date"])
    local: Any = series.tz_convert("America/New_York")
    by_date: dict[date, tuple[pd.Timestamp, float]] = {}
    for timestamp_raw, value in local.items():
        timestamp: Any = pd.Timestamp(timestamp_raw)
        by_date[timestamp.date()] = (timestamp, float(value))
    if release_date not in by_date:
        return None
    prior_dates = sorted(item for item in by_date if item < release_date)
    if not prior_dates:
        return None
    prior_date = prior_dates[-1]
    pre_time, pre_price = by_date[prior_date]
    post_time, post_price = by_date[release_date]
    change = post_price - pre_price
    return {
        "measure": "daily_close_to_close",
        "definition": "Previous available New York trading-day Yahoo daily Close to the release-day Yahoo daily Close.",
        "pre_release": price_point(pre_time, pre_price),
        "post_release": price_point(post_time, post_price),
        "change": change,
        "return_pct": (change / pre_price * 100) if pre_price else None,
        "direction": direction(change),
        "interval": "1d",
    }


def make_record(event: dict, hourly: pd.Series, daily: pd.Series, gold_manifest: dict) -> dict:
    reaction = hourly_reaction(event, hourly)
    used_fallback = False
    if reaction is None:
        reaction = daily_reaction(event, daily)
        used_fallback = reaction is not None
    if reaction is None:
        reaction = {
            "measure": "unavailable",
            "definition": "No usable Yahoo hourly or daily observations covered this event.",
            "pre_release": None,
            "post_release": None,
            "change": None,
            "return_pct": None,
            "direction": None,
            "interval": None,
            "reason": "data unavailable",
        }
    reaction["source"] = {
        "provider": gold_manifest["provider"],
        "symbol": gold_manifest["symbol"],
        "source_url": gold_manifest["source_url"],
        "retrieved_at": gold_manifest["retrieved_at"],
        "adjustment": gold_manifest["adjustment"],
    }
    return {
        "event_id": event["id"],
        "release_type": event["release_type"],
        "release_label": event["label"],
        "release_name": event["name"],
        "release_date": event["date"],
        "release_time_et": event["time_et"],
        "release_time_wat": event["times"]["wat"],
        "leading_indicators": None,
        "model_score": None,
        "phase_note": "Leading indicators and model score are intentionally unavailable until Phase 3.",
        "price_reaction": reaction,
        "reaction_status": "daily_fallback" if used_fallback else "hourly_primary" if reaction["measure"] == "hourly_60m" else "unavailable",
    }


def make_source_status(name: str, url: str, state: str, checked_at: str, detail: str, records: int = 0, mode: str | None = None) -> dict:
    result = {"name": name, "url": url, "state": state, "last_checked": checked_at, "records": records, "detail": detail}
    if mode:
        result["mode"] = mode
    return result


def main() -> int:
    config = read_json(CONFIG_PATH, {})
    if not isinstance(config, dict) or not config.get("releases"):
        print("release_config.json is missing or invalid", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc)
    end = now.date()
    start = parse_config_date(str(config.get("history", {}).get("start_date")), "history.start_date")
    checked_at = now.isoformat()
    source_status: dict[str, dict] = {}

    try:
        fred_events, fred_info = fred_history_events(config, start, end)
        source = config["sources"]["fred_releases"]
        source_status["fred_history"] = make_source_status(name=source["name"], url=source["url"], state="ok", checked_at=checked_at, detail=f"Fetched {fred_info['records']} historical BLS release records across {fred_info['pages']} FRED pages.", records=fred_info["records"], mode="live")
    except SourceError as exc:
        fred_events = []
        source = config["sources"]["fred_releases"]
        source_status["fred_history"] = make_source_status(name=source["name"], url=source["url"], state="unavailable", checked_at=checked_at, detail=str(exc), mode="unavailable")

    try:
        fomc_events, fomc_info = historical_fomc_events(config, start, end)
        source = config["sources"]["federal_reserve_fomc"]
        source_status["fomc_history"] = make_source_status(name=source["name"], url=source["url"], state="ok", checked_at=checked_at, detail=f"Parsed {fomc_info['records']} historical FOMC events from the official calendar.", records=fomc_info["records"], mode="live")
    except SourceError as exc:
        fomc_events = []
        source = config["sources"]["federal_reserve_fomc"]
        source_status["fomc_history"] = make_source_status(name=source["name"], url=source["url"], state="unavailable", checked_at=checked_at, detail=str(exc), mode="unavailable")

    all_events = sorted(fred_events + fomc_events, key=lambda item: (item["date"], item["time_et"], item["release_type"]))
    if not all_events:
        print("No historical release events were available; no reaction database was written.", file=sys.stderr)
        return 1

    try:
        hourly, daily, gold_manifest = fetch_gold_history(config, start, end)
        source_status["gold_price_hourly"] = make_source_status(name=config["gold_price"]["provider"], url=config["gold_price"]["source_url"], state="ok" if not hourly.empty else "unavailable", checked_at=checked_at, detail=f"Loaded {len(hourly)} hourly {config['gold_price']['symbol']} rows; Yahoo hourly history is limited to approximately {config['gold_price']['hourly_history_limit_days']} days.", records=len(hourly), mode="hourly")
        source_status["gold_price_daily"] = make_source_status(name=config["gold_price"]["provider"], url=config["gold_price"]["source_url"], state="ok" if not daily.empty else "unavailable", checked_at=checked_at, detail=f"Loaded {len(daily)} daily {config['gold_price']['symbol']} rows for the daily fallback.", records=len(daily), mode="daily_fallback")
    except Exception as exc:
        hourly = pd.Series(dtype="float64")
        daily = pd.Series(dtype="float64")
        gold_manifest = {
            "provider": config["gold_price"]["provider"],
            "symbol": config["gold_price"]["symbol"],
            "instrument_label": config["gold_price"]["instrument_label"],
            "source_url": config["gold_price"]["source_url"],
            "retrieved_at": checked_at,
            "adjustment": config["gold_price"]["adjustment"],
            "hourly_rows": 0,
            "daily_rows": 0,
        }
        source_status["gold_price_hourly"] = make_source_status(name=config["gold_price"]["provider"], url=config["gold_price"]["source_url"], state="unavailable", checked_at=checked_at, detail=f"Hourly data unavailable: {exc}", mode="unavailable")
        source_status["gold_price_daily"] = make_source_status(name=config["gold_price"]["provider"], url=config["gold_price"]["source_url"], state="unavailable", checked_at=checked_at, detail=f"Daily data unavailable: {exc}", mode="unavailable")

    records = [make_record(event, hourly, daily, gold_manifest) for event in all_events]
    measures = Counter(record["price_reaction"]["measure"] for record in records)
    by_type = Counter(record["release_type"] for record in records)
    source_status["historical_reactions"] = make_source_status(name="Historical reaction database", url="data/historical_reactions.json", state="ok" if any(value > 0 for key, value in measures.items() if key != "unavailable") else "unavailable", checked_at=checked_at, detail=f"Built {len(records)} records across all configured release types using explicit measure labels.", records=len(records), mode="phase2")

    output = {
        "schema_version": 1,
        "generated_at": checked_at,
        "history_window": {"start_date": start.isoformat(), "end_date": end.isoformat()},
        "data_manifest": gold_manifest,
        "measure_definitions": {
            "hourly_60m": "Primary: last hourly Close before the release to the first hourly Close at or after 60 minutes after the release.",
            "daily_close_to_close": "Fallback: previous available trading-day Close to release-day Close.",
            "unavailable": "No usable source observations; never converted to a zero or a guessed result.",
        },
        "summary": {"records": len(records), "by_release_type": dict(by_type), "by_measure": dict(measures)},
        "records": records,
    }
    write_json_atomic(OUTPUT_PATH, output)

    prior_status = read_json(STATUS_PATH, {})
    prior_sources = prior_status.get("sources") if isinstance(prior_status, dict) else {}
    merged_sources = {**(prior_sources if isinstance(prior_sources, dict) else {}), **source_status}
    write_json_atomic(STATUS_PATH, {"schema_version": 1, "generated_at": checked_at, "sources": merged_sources})
    print(json.dumps({"generated_at": checked_at, "records": len(records), "by_release_type": dict(by_type), "by_measure": dict(measures), "sources": source_status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
