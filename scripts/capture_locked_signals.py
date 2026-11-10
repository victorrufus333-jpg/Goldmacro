#!/usr/bin/env python3
"""Capture only live pre-release locked signals into an append-only snapshot."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from update_calendar import read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SIGNALS_PATH = DATA / "signals.json"
LOCKED_PATH = DATA / "locked_signals.json"


def stable_part(item: dict) -> dict:
    return {
        "event_id": item["event_id"],
        "release_type": item.get("release_type"),
        "release_label": item.get("release_label"),
        "release_name": item.get("release_name"),
        "release_date": item.get("release_date"),
        "release_time_et": item.get("release_time_et"),
        "release_time_wat": item.get("release_time_wat"),
        "signal": item.get("signal"),
        "model_score": item.get("model_score"),
        "available_votes": item.get("available_votes"),
        "missing_indicators": item.get("missing_indicators"),
        "historical_context": item.get("historical_context"),
        "data_vintage": item.get("data_vintage"),
        "lock_state": item.get("lock_state"),
        "lock_time_et": item.get("lock_time_et"),
        "lock_minutes_before_release": item.get("lock_minutes_before_release"),
        "leading_indicators": [
            {
                "series_id": vote.get("series_id"),
                "label": vote.get("label"),
                "vote": vote.get("vote"),
                "vote_label": vote.get("vote_label"),
                "value": vote.get("value"),
                "delta": vote.get("delta"),
                "observation_date": vote.get("observation_date"),
                "cutoff_vintage": vote.get("cutoff_vintage"),
                "status": vote.get("status"),
            }
            for vote in item.get("leading_indicators", [])
        ],
        "capture_source": "signals.json live locked snapshot",
    }


def main() -> int:
    source = read_json(SIGNALS_PATH, {})
    existing_payload = read_json(LOCKED_PATH, {"schema_version": 1, "records": []})
    if not isinstance(source, dict) or not isinstance(existing_payload, dict):
        print("invalid Phase 4 signal input", file=sys.stderr)
        return 1
    existing = existing_payload.get("records", []) if isinstance(existing_payload.get("records"), list) else []
    by_id = {item.get("event_id"): item for item in existing if isinstance(item, dict) and item.get("event_id")}
    additions: list[dict] = []
    for item in source.get("records", []):
        if not isinstance(item, dict) or item.get("lock_state") != "locked_pre_release" or not item.get("signal_locked"):
            continue
        event_id = item.get("event_id")
        if not event_id:
            continue
        snapshot = stable_part(item)
        if event_id in by_id:
            old = {key: value for key, value in by_id[event_id].items() if key != "captured_at"}
            if old != snapshot:
                print(f"append-only conflict for locked signal {event_id}", file=sys.stderr)
                return 1
            continue
        snapshot["captured_at"] = datetime.now(timezone.utc).isoformat()
        additions.append(snapshot)
    if not additions:
        print(json.dumps({"added": 0, "existing": len(existing)}))
        return 0
    records = existing + additions
    payload = {
        "schema_version": 1,
        "append_only": True,
        "eligibility": "Only live locked_pre_release snapshots are included; historical reconstructions are excluded.",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {"records": len(records)},
        "records": records,
    }
    write_json_atomic(LOCKED_PATH, payload)
    print(json.dumps({"added": len(additions), "records": len(records)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
