#!/usr/bin/env python3
"""Build separate chain cases from immutable locked track-record entries."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from update_calendar import read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG_PATH = DATA / "release_config.json"
TRACK_PATH = DATA / "track_record.json"
CHAINS_PATH = DATA / "chained_cases.json"


def chain_summary(records: list[dict]) -> dict:
    wins = sum(item.get("chain_grade") == "WIN" for item in records)
    losses = sum(item.get("chain_grade") == "LOSS" for item in records)
    skipped = len(records) - wins - losses
    n = wins + losses
    by_transition: dict[str, dict] = {}
    for item in records:
        transition = item.get("transition", "unknown")
        subset = by_transition.setdefault(transition, {"N": 0, "wins": 0, "losses": 0, "skipped": 0})
        grade = item.get("chain_grade")
        if grade == "WIN": subset["wins"] += 1
        elif grade == "LOSS": subset["losses"] += 1
        else: subset["skipped"] += 1
    for item in by_transition.values():
        item["N"] = item["wins"] + item["losses"]
        item["win_rate"] = (item["wins"] / item["N"] * 100) if item["N"] else None
    return {"N": n, "wins": wins, "losses": losses, "skipped": skipped, "win_rate": (wins / n * 100) if n else None, "by_transition": by_transition}


def main() -> int:
    config = read_json(CONFIG_PATH, {})
    track = read_json(TRACK_PATH, {})
    existing = read_json(CHAINS_PATH, {})
    track_records = track.get("records", []) if isinstance(track, dict) and isinstance(track.get("records"), list) else []
    chaining_config = config.get("chaining", {}) if isinstance(config, dict) else {}
    max_gap = int(chaining_config.get("max_gap_days", 45)) if isinstance(chaining_config, dict) else 45
    ordered = sorted(track_records, key=lambda item: (item.get("release_date", ""), item.get("event_id", "")))
    chains: list[dict] = []
    for previous, current in zip(ordered, ordered[1:]):
        try:
            gap = (date.fromisoformat(current["release_date"]) - date.fromisoformat(previous["release_date"])).days
        except (KeyError, TypeError, ValueError):
            continue
        if gap < 0 or gap > max_gap:
            continue
        previous_grade = previous.get("grade")
        current_grade = current.get("grade")
        chain_grade = current_grade if previous_grade in {"WIN", "LOSS"} and current_grade in {"WIN", "LOSS"} else "UNSURE-skipped"
        chains.append({
            "chain_id": f"chain-{previous['event_id']}-{current['event_id']}",
            "previous_event_id": previous["event_id"],
            "current_event_id": current["event_id"],
            "previous_release_type": previous.get("release_type"),
            "current_release_type": current.get("release_type"),
            "transition": f"{previous.get('release_type')}->{current.get('release_type')}",
            "gap_days": gap,
            "previous_grade": previous_grade,
            "current_grade": current_grade,
            "chain_grade": chain_grade,
            "definition": "Directional only when both adjacent immutable records are WIN or LOSS; current record determines chain result.",
        })
    summary = chain_summary(chains)
    candidate = {"schema_version": 1, "append_only_source": "track_record.json", "max_gap_days": max_gap, "summary": summary, "records": chains}
    old_signature = (existing.get("records"), existing.get("summary"), existing.get("max_gap_days")) if isinstance(existing, dict) else None
    new_signature = (candidate["records"], candidate["summary"], candidate["max_gap_days"])
    if old_signature == new_signature:
        print(json.dumps({"updated": False, "records": len(chains), "summary": summary}))
        return 0
    candidate["generated_at"] = datetime.now(timezone.utc).isoformat()
    write_json_atomic(CHAINS_PATH, candidate)
    print(json.dumps({"updated": True, "records": len(chains), "summary": summary}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
