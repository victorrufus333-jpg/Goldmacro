#!/usr/bin/env python3
"""Append released locked signals to the immutable public track record."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from update_calendar import read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LOCKED_PATH = DATA / "locked_signals.json"
HISTORY_PATH = DATA / "historical_reactions.json"
TRACK_PATH = DATA / "track_record.json"


def grade(signal: str, direction: str | None) -> tuple[str, str]:
    if signal not in {"BUY", "SELL"}:
        return "UNSURE-skipped", "The locked signal was UNSURE and is excluded from directional N."
    if direction not in {"up", "down"}:
        return "UNSURE-skipped", "The measured gold reaction was flat or unavailable."
    expected = "up" if signal == "BUY" else "down"
    return ("WIN", "Locked signal direction matched the measured gold direction.") if direction == expected else ("LOSS", "Locked signal direction did not match the measured gold direction.")


def summary(records: list[dict]) -> dict:
    wins = sum(item.get("grade") == "WIN" for item in records)
    losses = sum(item.get("grade") == "LOSS" for item in records)
    skipped = len(records) - wins - losses
    n = wins + losses
    by_type: dict[str, dict] = {}
    release_types = sorted({str(item.get("release_type")) for item in records if item.get("release_type")})
    for release_type in release_types:
        subset = [item for item in records if item.get("release_type") == release_type]
        sw = sum(item.get("grade") == "WIN" for item in subset)
        sl = sum(item.get("grade") == "LOSS" for item in subset)
        ss = len(subset) - sw - sl
        sn = sw + sl
        by_type[release_type] = {"N": sn, "wins": sw, "losses": sl, "skipped": ss, "win_rate": (sw / sn * 100) if sn else None}
    return {"N": n, "wins": wins, "losses": losses, "skipped": skipped, "win_rate": (wins / n * 100) if n else None, "by_release_type": by_type}


def main() -> int:
    locked = read_json(LOCKED_PATH, {})
    history = read_json(HISTORY_PATH, {})
    existing_payload = read_json(TRACK_PATH, {"schema_version": 1, "records": []})
    locked_records = locked.get("records", []) if isinstance(locked, dict) and isinstance(locked.get("records"), list) else []
    history_records = history.get("records", []) if isinstance(history, dict) and isinstance(history.get("records"), list) else []
    existing = existing_payload.get("records", []) if isinstance(existing_payload, dict) and isinstance(existing_payload.get("records"), list) else []
    existing_ids = {item.get("event_id") for item in existing if isinstance(item, dict)}
    history_by_id = {item.get("event_id"): item for item in history_records}
    additions: list[dict] = []
    for locked_item in locked_records:
        event_id = locked_item.get("event_id")
        if not event_id or event_id in existing_ids:
            continue
        reaction_record = history_by_id.get(event_id)
        reaction = reaction_record.get("price_reaction") if isinstance(reaction_record, dict) else None
        if not isinstance(reaction, dict) or reaction.get("direction") not in {"up", "down", "flat"}:
            continue
        grade_value, reason = grade(str(locked_item.get("signal")), reaction.get("direction"))
        additions.append({
            "event_id": event_id,
            "release_type": locked_item.get("release_type"),
            "release_label": locked_item.get("release_label"),
            "release_name": locked_item.get("release_name"),
            "release_date": locked_item.get("release_date"),
            "release_time_et": locked_item.get("release_time_et"),
            "release_time_wat": locked_item.get("release_time_wat"),
            "signal": locked_item.get("signal"),
            "model_score": locked_item.get("model_score"),
            "available_votes": locked_item.get("available_votes"),
            "data_vintage": locked_item.get("data_vintage"),
            "locked_at": locked_item.get("captured_at"),
            "lock_time_et": locked_item.get("lock_time_et"),
            "grade": grade_value,
            "grade_reason": reason,
            "reaction": {"measure": reaction.get("measure"), "direction": reaction.get("direction"), "return_pct": reaction.get("return_pct"), "source": reaction.get("source")},
            "historical_context_at_lock": locked_item.get("historical_context"),
            "record_source": "locked_signals.json joined to historical_reactions.json",
            "immutable": True,
        })
    if not additions:
        print(json.dumps({"added": 0, "records": len(existing), "summary": summary(existing)}))
        return 0
    records = existing + additions
    payload = {
        "schema_version": 1,
        "append_only": True,
        "policy": "Existing records are never rewritten. New records are appended only after a live locked snapshot has a post-release reaction.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary(records),
        "records": records,
    }
    write_json_atomic(TRACK_PATH, payload)
    print(json.dumps({"added": len(additions), "records": len(records), "summary": payload["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
