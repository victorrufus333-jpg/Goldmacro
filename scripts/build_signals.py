#!/usr/bin/env python3
"""Build configurable pre-release indicator votes and BUY/SELL/UNSURE signals."""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from update_calendar import SourceError, fetch_json, read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG_PATH = DATA / "release_config.json"
CALENDAR_PATH = DATA / "calendar.json"
HISTORY_PATH = DATA / "historical_reactions.json"
SIGNALS_PATH = DATA / "signals.json"
STATUS_PATH = DATA / "status.json"
FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SERIES_URL = "https://api.stlouisfed.org/fred/series"
ET_ZONE = ZoneInfo("America/New_York")


class IndicatorError(RuntimeError):
    pass


def parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise IndicatorError(f"invalid date: {value}") from exc


def event_cutoff(event: dict, today: date) -> tuple[date, str]:
    event_date = parse_date(event["date"])
    if event_date < today:
        return event_date - timedelta(days=1), "historical_reconstruction"
    return min(event_date - timedelta(days=1), today - timedelta(days=1)), "live_candidate"


def event_datetime(event: dict) -> datetime:
    return datetime.fromisoformat(event["times"]["et"])


def build_query(series_id: str, vintage_dates: list[date], observation_start: date, observation_end: date, api_key: str) -> str:
    params = {
        "api_key": api_key,
        "file_type": "json",
        "series_id": series_id,
        "observation_start": observation_start.isoformat(),
        "observation_end": observation_end.isoformat(),
        "vintage_dates": ",".join(item.isoformat() for item in vintage_dates),
        "output_type": "2",
        "sort_order": "asc",
        "limit": "100000",
    }
    return FRED_OBSERVATIONS_URL + "?" + urllib.parse.urlencode(params)


def fetch_vintage_series(series_id: str, vintage_dates: list[date], observation_start: date, observation_end: date, api_key: str) -> tuple[dict[date, list[tuple[date, float]]], dict]:
    payload = fetch_json(build_query(series_id, vintage_dates, observation_start, observation_end, api_key))
    observations = payload.get("observations")
    if not isinstance(observations, list):
        raise IndicatorError(f"FRED series {series_id} returned no observations list")
    series_by_vintage: dict[date, list[tuple[date, float]]] = {vintage: [] for vintage in vintage_dates}
    for vintage in vintage_dates:
        field = f"{series_id}_{vintage.strftime('%Y%m%d')}"
        values: list[tuple[date, float]] = []
        for row in observations:
            raw_value = row.get(field)
            if raw_value in (None, "", "."):
                continue
            try:
                values.append((parse_date(str(row["date"])), float(raw_value)))
            except (KeyError, TypeError, ValueError):
                continue
        series_by_vintage[vintage] = values
    return series_by_vintage, {"series_id": series_id, "observations": len(observations), "vintage_dates": len(vintage_dates)}


def latest_delta(values: list[tuple[date, float]], cutoff: date, lookback: int) -> dict:
    usable = [(observation_date, value) for observation_date, value in values if observation_date <= cutoff]
    if not usable:
        return {"status": "unavailable", "reason": "No observation was available by the cutoff vintage."}
    current_date, current_value = usable[-1]
    if len(usable) <= lookback:
        return {"status": "insufficient_history", "reason": f"Only {len(usable)} observations were available; need {lookback + 1}.", "observation_date": current_date.isoformat(), "value": current_value}
    prior_date, prior_value = usable[-1 - lookback]
    return {
        "status": "ok",
        "observation_date": current_date.isoformat(),
        "value": current_value,
        "prior_observation_date": prior_date.isoformat(),
        "prior_value": prior_value,
        "delta": current_value - prior_value,
    }


def score_indicator(rule: dict, series_values: list[tuple[date, float]], cutoff: date, max_staleness_days: int, catalog: dict) -> dict:
    result = latest_delta(series_values, cutoff, int(rule["lookback"]))
    base = {
        "series_id": rule["series_id"],
        "label": rule["label"],
        "method": rule["method"],
        "lookback": rule["lookback"],
        "threshold": rule["threshold"],
        "buy_when": rule["buy_when"],
        "units": catalog.get(rule["series_id"], {}).get("units"),
        "frequency": catalog.get(rule["series_id"], {}).get("frequency"),
        "source_url": FRED_OBSERVATIONS_URL,
        "cutoff_vintage": cutoff.isoformat(),
    }
    base.update(result)
    if result.get("status") != "ok":
        base["vote"] = None
        return base
    observation_date = parse_date(result["observation_date"])
    staleness_days = (cutoff - observation_date).days
    base["staleness_days"] = staleness_days
    if staleness_days > max_staleness_days:
        base["status"] = "stale"
        base["reason"] = f"Latest observation is {staleness_days} days old; limit is {max_staleness_days}."
        base["vote"] = None
        return base
    delta = float(result["delta"])
    threshold = float(rule["threshold"])
    base["direction"] = "positive" if delta > 0 else "negative" if delta < 0 else "flat"
    if abs(delta) < threshold:
        base["vote"] = 0
        base["vote_label"] = "NEUTRAL"
    else:
        positive = delta > 0
        buy_when_positive = rule["buy_when"] == "positive"
        is_buy = positive == buy_when_positive
        base["vote"] = 1 if is_buy else -1
        base["vote_label"] = "BUY" if is_buy else "SELL"
    return base


def evaluate_event(event: dict, config: dict, series_cache: dict[str, dict[date, list[tuple[date, float]]]], today: date, now: datetime, mode: str) -> dict:
    engine = config["signal_engine"]
    release_type = event["release_type"]
    rules = engine["rules"].get(release_type, [])
    cutoff, inferred_mode = event_cutoff(event, today)
    if mode == "upcoming":
        cutoff = min(cutoff, today)
        inferred_mode = "live_candidate"
    catalog = engine.get("indicator_catalog", {})
    max_staleness = int(engine["data"].get("max_staleness_days", 90))
    indicators: list[dict] = []
    for rule in rules:
        series_vintages = series_cache.get(rule["series_id"], {})
        values = series_vintages.get(cutoff, [])
        if not values:
            item = {
                "series_id": rule["series_id"],
                "label": rule["label"],
                "method": rule["method"],
                "lookback": rule["lookback"],
                "threshold": rule["threshold"],
                "buy_when": rule["buy_when"],
                "status": "unavailable",
                "reason": "The FRED vintage response did not contain a usable column for this cutoff.",
                "vote": None,
                "cutoff_vintage": cutoff.isoformat(),
                "source_url": FRED_OBSERVATIONS_URL,
            }
        else:
            item = score_indicator(rule, values, cutoff, max_staleness, catalog)
        indicators.append(item)

    numeric_votes = [item["vote"] for item in indicators if isinstance(item.get("vote"), int)]
    missing = len(indicators) - len(numeric_votes)
    score = sum(numeric_votes)
    minimum_votes = int(engine["score"]["minimum_votes"])
    maximum_missing_fraction = float(engine["score"]["maximum_missing_fraction"])
    missing_fraction = missing / len(indicators) if indicators else 1.0
    reasons: list[str] = []
    if len(numeric_votes) < minimum_votes:
        reasons.append(f"Only {len(numeric_votes)} of {len(indicators)} indicator votes are usable; minimum is {minimum_votes}.")
    if missing_fraction > maximum_missing_fraction:
        reasons.append(f"Missing or stale indicators are {missing_fraction:.0%}; maximum allowed is {maximum_missing_fraction:.0%}.")
    if reasons:
        signal = "UNSURE"
    elif score >= int(engine["score"]["buy_min"]):
        signal = "BUY"
    elif score <= int(engine["score"]["sell_max"]):
        signal = "SELL"
    else:
        signal = "UNSURE"
        reasons.append(f"Score {score} did not clear BUY {engine['score']['buy_min']} or SELL {engine['score']['sell_max']}.")
    if not reasons:
        reasons.append(f"Score {score} cleared the configured threshold with {len(numeric_votes)} usable votes.")

    release_dt = event_datetime(event)
    lock_minutes = int(engine["lock"]["minutes_before_release"])
    lock_dt = release_dt - timedelta(minutes=lock_minutes)
    if mode == "historical":
        lock_state = "historical_reconstruction"
        locked = True
    elif now < lock_dt:
        lock_state = "candidate_before_lock"
        locked = False
    elif now < release_dt:
        lock_state = "locked_pre_release"
        locked = True
    else:
        lock_state = "released"
        locked = True

    return {
        "event_id": event["id"],
        "release_type": release_type,
        "release_label": event.get("label"),
        "release_name": event.get("name"),
        "release_date": event["date"],
        "release_time_et": event.get("time_et"),
        "release_time_wat": event.get("times", {}).get("wat"),
        "mode": inferred_mode,
        "data_vintage": cutoff.isoformat(),
        "indicator_source": "FRED series observations with vintage_dates",
        "leading_indicators": indicators,
        "model_score": score if numeric_votes else None,
        "signal": signal,
        "signal_locked": locked,
        "lock_state": lock_state,
        "lock_time_et": lock_dt.isoformat(),
        "lock_minutes_before_release": lock_minutes,
        "available_votes": len(numeric_votes),
        "missing_indicators": missing,
        "missing_fraction": missing_fraction,
        "reason": " ".join(reasons),
        "revised_data_warning": engine["data"]["revised_data_warning"],
        "generated_at": now.isoformat(),
    }


def make_event_from_history(record: dict) -> dict:
    local_et = datetime.fromisoformat(f"{record['release_date']}T{record['release_time_et']}:00").replace(tzinfo=ET_ZONE)
    return {
        "id": record["event_id"],
        "release_type": record["release_type"],
        "label": record["release_label"],
        "name": record["release_name"],
        "date": record["release_date"],
        "time_et": record["release_time_et"],
        "times": {"et": local_et.isoformat(), "wat": record["release_time_wat"]},
    }


def grade_signal(signal: str, reaction_direction: str | None) -> tuple[str, str]:
    if signal not in {"BUY", "SELL"}:
        return "UNSURE-skipped", "Signal was UNSURE and is excluded from win-rate N."
    if reaction_direction not in {"up", "down"}:
        return "UNSURE-skipped", "Gold reaction was flat or unavailable and is excluded from win-rate N."
    expected = "up" if signal == "BUY" else "down"
    if reaction_direction == expected:
        return "WIN", "Signal direction matched the measured gold direction."
    return "LOSS", "Signal direction did not match the measured gold direction."


def track_record_metrics(signals: list[dict]) -> dict[str, dict]:
    metrics: dict[str, dict] = {}
    for release_type in sorted({item["release_type"] for item in signals}):
        items = [item for item in signals if item["release_type"] == release_type]
        wins = sum(item.get("grade") == "WIN" for item in items)
        losses = sum(item.get("grade") == "LOSS" for item in items)
        skipped = len(items) - wins - losses
        n = wins + losses
        metrics[release_type] = {
            "N": n,
            "wins": wins,
            "losses": losses,
            "skipped": skipped,
            "win_rate": (wins / n * 100) if n else None,
            "definition": "N counts only BUY/SELL cases with an available non-flat gold reaction; UNSURE-skipped cases are reported separately.",
        }
    return metrics


def source_status(name: str, url: str, state: str, checked_at: str, detail: str, records: int = 0, mode: str | None = None) -> dict:
    result = {"name": name, "url": url, "state": state, "last_checked": checked_at, "records": records, "detail": detail}
    if mode:
        result["mode"] = mode
    return result


def main() -> int:
    config = read_json(CONFIG_PATH, {})
    history = read_json(HISTORY_PATH, {})
    calendar = read_json(CALENDAR_PATH, {})
    if not isinstance(config, dict) or not config.get("signal_engine") or not isinstance(history, dict) or not isinstance(calendar, dict):
        print("Phase 3 inputs are missing or invalid", file=sys.stderr)
        return 1
    api_key = os.environ.get("FRED_API_KEY", "").strip()
    checked_at = datetime.now(timezone.utc)
    today = checked_at.date()
    if not api_key:
        print("FRED_API_KEY is not configured; signals cannot be built honestly", file=sys.stderr)
        return 1

    historical_records = history.get("records", []) if isinstance(history.get("records"), list) else []
    historical_events = [make_event_from_history(record) for record in historical_records]
    upcoming_events = [event for event in calendar.get("events", []) if isinstance(event, dict) and event.get("times", {}).get("et") and event_datetime(event) >= checked_at]
    all_events = historical_events + upcoming_events
    vintage_dates = sorted({event_cutoff(event, today)[0] for event in all_events})
    if not vintage_dates:
        print("No historical or upcoming events are available", file=sys.stderr)
        return 1

    history_start = parse_date(str(config.get("history", {}).get("start_date", today.isoformat())))
    max_lookback = max(int(rule["lookback"]) for rules in config["signal_engine"]["rules"].values() for rule in rules)
    observation_start = history_start - timedelta(days=max(450, max_lookback * 35))
    series_ids = sorted({rule["series_id"] for rules in config["signal_engine"]["rules"].values() for rule in rules})
    rules_by_series: dict[str, set[str]] = {}
    for release_type, rules in config["signal_engine"]["rules"].items():
        for rule in rules:
            rules_by_series.setdefault(rule["series_id"], set()).add(release_type)
    series_cache: dict[str, dict[date, list[tuple[date, float]]]] = {}
    source_errors: dict[str, str] = {}
    source_records = 0
    for series_id in series_ids:
        try:
            needed_vintages = sorted({event_cutoff(event, today)[0] for event in all_events if event["release_type"] in rules_by_series[series_id]})
            series_cache[series_id], info = fetch_vintage_series(series_id, needed_vintages, observation_start, today, api_key)
            source_records += int(info["observations"])
        except Exception as exc:
            source_errors[series_id] = str(exc)
            series_cache[series_id] = {}

    historical_signals = [evaluate_event(event, config, series_cache, today, checked_at, "historical") for event in historical_events]
    upcoming_signals = [evaluate_event(event, config, series_cache, today, checked_at, "upcoming") for event in upcoming_events]
    history_by_id = {record["event_id"]: record for record in historical_records}
    for item in historical_signals:
        grade, reason = grade_signal(item["signal"], history_by_id[item["event_id"]].get("price_reaction", {}).get("direction"))
        item["grade"] = grade
        item["grade_reason"] = reason
    metrics = track_record_metrics(historical_signals)
    for item in historical_signals + upcoming_signals:
        item["historical_context"] = metrics.get(item["release_type"], {"N": 0, "wins": 0, "losses": 0, "skipped": 0, "win_rate": None})
    all_signals = historical_signals + upcoming_signals

    signal_by_id = {item["event_id"]: item for item in all_signals}
    updated_history = dict(history)
    updated_records: list[dict] = []
    for record in historical_records:
        signal = signal_by_id.get(record["event_id"])
        updated = dict(record)
        if signal:
            updated["leading_indicators"] = signal["leading_indicators"]
            updated["model_score"] = signal["model_score"]
            updated["signal"] = signal["signal"]
            updated["signal_state"] = signal["lock_state"]
            updated["signal_reason"] = signal["reason"]
            updated["signal_data_vintage"] = signal["data_vintage"]
            updated["signal_revised_data_warning"] = signal["revised_data_warning"]
            updated["grade"] = signal["grade"]
            updated["grade_reason"] = signal["grade_reason"]
            updated["historical_context"] = signal["historical_context"]
            updated["phase_note"] = "Phase 3 signal reconstruction uses FRED vintage_dates and is not a licensed real-time consensus backtest."
        updated_records.append(updated)
    updated_history["generated_at"] = checked_at.isoformat()
    updated_history["signal_engine_version"] = config["signal_engine"]["version"]
    updated_history["records"] = updated_records
    updated_history["signal_summary"] = {
        "by_signal": dict(Counter(item["signal"] for item in historical_signals)),
        "by_release_type": dict(Counter(item["release_type"] for item in historical_signals)),
        "historical_records": len(historical_signals),
        "track_record": metrics,
    }
    write_json_atomic(HISTORY_PATH, updated_history)

    signal_output = {
        "schema_version": 1,
        "generated_at": checked_at.isoformat(),
        "engine_version": config["signal_engine"]["version"],
        "lock_minutes_before_release": config["signal_engine"]["lock"]["minutes_before_release"],
        "historical_vintage_rule": config["signal_engine"]["data"]["historical_vintage_rule"],
        "revised_data_warning": config["signal_engine"]["data"]["revised_data_warning"],
        "summary": {
            "historical": len(historical_signals),
            "upcoming": len(upcoming_signals),
            "by_signal": dict(Counter(item["signal"] for item in all_signals)),
            "by_lock_state": dict(Counter(item["lock_state"] for item in all_signals)),
            "track_record": metrics,
        },
        "source_errors": source_errors,
        "records": all_signals,
    }
    write_json_atomic(SIGNALS_PATH, signal_output)

    prior_status = read_json(STATUS_PATH, {})
    prior_sources = prior_status.get("sources") if isinstance(prior_status, dict) else {}
    source_state = "ok" if not source_errors and all_signals else "unavailable" if not all_signals else "fallback"
    phase_status = {
        "fred_indicators": source_status("FRED indicator observations", FRED_OBSERVATIONS_URL, "unavailable" if source_errors else "ok", checked_at.isoformat(), f"Retrieved {len(series_ids) - len(source_errors)} of {len(series_ids)} configured indicator series using vintage_dates.", records=source_records, mode="vintage"),
        "signal_engine": source_status("Configurable signal engine", "data/signals.json", source_state, checked_at.isoformat(), f"Built {len(historical_signals)} historical reconstructions and {len(upcoming_signals)} upcoming signal records.", records=len(all_signals), mode="phase3"),
    }
    merged_sources = {**(prior_sources if isinstance(prior_sources, dict) else {}), **phase_status}
    write_json_atomic(STATUS_PATH, {"schema_version": 1, "generated_at": checked_at.isoformat(), "sources": merged_sources})
    print(json.dumps({"generated_at": checked_at.isoformat(), "series": len(series_ids), "source_errors": source_errors, "historical": len(historical_signals), "upcoming": len(upcoming_signals), "by_signal": dict(Counter(item["signal"] for item in all_signals))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
