#!/usr/bin/env python3
"""Build point-in-time confidence and conviction analytics from Phase 3 signals."""
from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from update_calendar import read_json, write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG_PATH = DATA / "release_config.json"
SIGNALS_PATH = DATA / "signals.json"
HISTORY_PATH = DATA / "historical_reactions.json"
CONFIDENCE_PATH = DATA / "confidence.json"
STATUS_PATH = DATA / "status.json"


def numeric(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(order):
        end = cursor + 1
        while end < len(order) and values[order[end]] == values[order[cursor]]:
            end += 1
        average = (cursor + 1 + end) / 2.0
        for position in range(cursor, end):
            ranks[order[position]] = average
        cursor = end
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    x_var = sum((x - x_mean) ** 2 for x in xs)
    y_var = sum((y - y_mean) ** 2 for y in ys)
    denominator = math.sqrt(x_var * y_var)
    return numerator / denominator if denominator else 0.0


def spearman_p_value(rho: float | None, n: int) -> float | None:
    if rho is None or n < 5:
        return None
    if abs(rho) >= 1:
        return 0.0
    t = abs(rho) * math.sqrt((n - 2) / max(1e-12, 1 - rho * rho))
    # Deterministic normal approximation; the output explicitly carries this caveat.
    return min(1.0, math.erfc(t / math.sqrt(2.0)))


def series_rule_map(config: dict) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    for release_type, rules in config["signal_engine"]["rules"].items():
        for rule in rules:
            result[(release_type, rule["series_id"])] = rule
    return result


def event_features(record: dict, rule_map: dict[tuple[str, str], dict]) -> dict[str, dict]:
    features: dict[str, dict] = {}
    release_type = str(record.get("release_type", ""))
    for item in record.get("leading_indicators", []) or []:
        if not isinstance(item, dict) or not item.get("series_id"):
            continue
        series_id = str(item["series_id"])
        rule = rule_map.get((release_type, series_id), item)
        delta = numeric(item.get("delta"))
        vote = item.get("vote") if isinstance(item.get("vote"), int) else None
        features[series_id] = {"delta": delta, "vote": vote, "buy_when": rule.get("buy_when", item.get("buy_when"))}
    return features


def outcome_return(record: dict) -> float | None:
    raw_reaction = record.get("price_reaction")
    reaction: dict = raw_reaction if isinstance(raw_reaction, dict) else {}
    return numeric(reaction.get("return_pct"))


def directional_grade(record: dict) -> str | None:
    grade = record.get("grade")
    return grade if grade in {"WIN", "LOSS"} else None


def reliability(records: list[dict], release_type: str, series_id: str, rule: dict, rule_map: dict[tuple[str, str], dict]) -> dict:
    xs: list[float] = []
    ys: list[float] = []
    for record in records:
        if record.get("release_type") != release_type:
            continue
        value = event_features(record, rule_map).get(series_id, {}).get("delta")
        outcome = outcome_return(record)
        if value is None or outcome is None:
            continue
        # Positive signed delta means the configured BUY direction.
        if rule.get("buy_when") == "negative":
            value = -value
        xs.append(value)
        ys.append(outcome)
    rho = pearson(rank(xs), rank(ys)) if len(xs) >= 3 else None
    n = len(xs)
    p_value = spearman_p_value(rho, n)
    minimum_n = int(rule.get("_minimum_reliability_N", 5))
    reliability_weight = max(0.0, float(rho or 0.0)) * math.sqrt(n / (n + 10.0)) if n else 0.0
    return {
        "release_type": release_type,
        "series_id": series_id,
        "label": rule.get("label", series_id),
        "N": n,
        "spearman_rho": round(rho, 6) if rho is not None else None,
        "p_value": round(p_value, 6) if p_value is not None else None,
        "weight_raw": round(reliability_weight, 6),
        "status": "underpowered" if n < minimum_n else "measured",
        "note": "Positive rho means the configured BUY direction historically aligned with a positive GC=F reaction. p_value is a normal approximation; it is not a guarantee of predictive power.",
    }


def similarity(current: dict[str, dict], prior: dict[str, dict]) -> float:
    overlap = [series_id for series_id in current if series_id in prior and current[series_id].get("vote") is not None and prior[series_id].get("vote") is not None]
    if not overlap:
        return 0.0
    agreements = sum(current[series_id]["vote"] == prior[series_id]["vote"] for series_id in overlap)
    return agreements / len(overlap)


def prior_records(records: list[dict], current: dict, chronological_only: bool) -> list[dict]:
    if not chronological_only:
        return [item for item in records if item.get("event_id") != current.get("event_id")]
    current_date = str(current.get("release_date", ""))
    return [item for item in records if str(item.get("release_date", "")) < current_date]


def confidence_for(record: dict, training: list[dict], rule_map: dict[tuple[str, str], dict], config: dict, *, walk_forward: bool) -> dict:
    release_type = str(record.get("release_type", ""))
    settings = config["confidence"]
    current_features = event_features(record, rule_map)
    reliability_rows = []
    rules = [rule for (release, _), rule in rule_map.items() if release == release_type]
    training_type = [item for item in training if item.get("release_type") == release_type]
    for rule in rules:
        enriched_rule = dict(rule)
        enriched_rule["_minimum_reliability_N"] = settings["minimum_reliability_N"]
        reliability_rows.append(reliability(training_type, release_type, rule["series_id"], enriched_rule, rule_map))
    weights = {item["series_id"]: float(item["weight_raw"]) for item in reliability_rows}
    weighted_total = 0.0
    weighted_abs = 0.0
    for series_id, feature in current_features.items():
        vote = feature.get("vote")
        weight = weights.get(series_id, 0.0)
        if isinstance(vote, int) and vote in {-1, 0, 1} and weight > 0:
            weighted_total += vote * weight
            weighted_abs += weight
    weighted_net = weighted_total / weighted_abs if weighted_abs else 0.0
    similar: list[tuple[float, dict]] = []
    for candidate in prior_records(training_type, record, walk_forward):
        candidate_features = event_features(candidate, rule_map)
        score = similarity(current_features, candidate_features)
        if score >= float(settings["similar_case_min_similarity"]):
            similar.append((score, candidate))
    similar.sort(key=lambda item: (-item[0], str(item[1].get("release_date", ""))))
    selected = similar[: int(settings["similar_case_top_k"])]
    wins = sum(directional_grade(item[1]) == "WIN" for item in selected)
    losses = sum(directional_grade(item[1]) == "LOSS" for item in selected)
    similar_n = wins + losses
    prior_strength = float(settings["prior_strength"])
    hit_rate = (wins + prior_strength * 0.5) / (similar_n + prior_strength) * 100 if similar_n else 50.0
    vote_support = abs(weighted_net)
    confidence_pct = 100.0 * (0.65 * hit_rate / 100.0 + 0.35 * (0.5 + 0.5 * vote_support))
    signal = record.get("signal")
    if signal == "BUY":
        directional_alignment = weighted_net
    elif signal == "SELL":
        directional_alignment = -weighted_net
    else:
        directional_alignment = 0.0
    conviction_pct = max(0.0, min(100.0, abs(directional_alignment) * 100.0))
    min_prior = int(config["confidence"]["walk_forward"]["minimum_prior_cases"])
    return {
        "confidence_pct": round(max(0.0, min(100.0, confidence_pct)), 2),
        "conviction_pct": round(conviction_pct, 2),
        "confidence_label": "directional evidence" if signal in {"BUY", "SELL"} else "evidence strength only; action remains UNSURE",
        "walk_forward": walk_forward,
        "walk_forward_eligible": len(training_type) >= min_prior,
        "prior_case_N": len(training_type),
        "similar_case_N": similar_n,
        "similar_case_candidates": len(similar),
        "similar_hit_rate_shrunk": round(hit_rate, 2),
        "similar_wins": wins,
        "similar_losses": losses,
        "weighted_vote_net": round(weighted_net, 6),
        "weighted_vote_support_pct": round(vote_support * 100.0, 2),
        "reliability": reliability_rows,
        "similar_cases": [{"event_id": item[1].get("event_id"), "release_date": item[1].get("release_date"), "similarity": round(item[0], 3), "grade": item[1].get("grade")} for item in selected],
        "method": "Walk-forward historical cases only for historical records; all completed historical cases for upcoming records. Reliability weights use signed indicator deltas and GC=F reaction returns.",
    }


def validation_summary(records: list[dict], contexts: dict[str, dict], *, walk_forward: bool) -> dict:
    eligible = [record for record in records if contexts.get(record.get("event_id", ""), {}).get("walk_forward") == walk_forward and contexts.get(record.get("event_id", ""), {}).get("walk_forward_eligible")]
    directional = [record for record in eligible if record.get("signal") in {"BUY", "SELL"} and directional_grade(record)]
    wins = sum(directional_grade(record) == "WIN" for record in directional)
    losses = sum(directional_grade(record) == "LOSS" for record in directional)
    return {"N": wins + losses, "wins": wins, "losses": losses, "skipped": len(eligible) - len(directional), "win_rate": round(wins / (wins + losses) * 100, 2) if wins + losses else None, "eligible_records": len(eligible), "definition": "Directional records with sufficient prior history; UNSURE and non-directional reactions remain excluded from N."}


def calibration(records: list[dict], contexts: dict[str, dict]) -> list[dict]:
    buckets = [(0, 40), (40, 60), (60, 75), (75, 90), (90, 101)]
    output = []
    for low, high in buckets:
        selected = [record for record in records if low <= float(contexts.get(record.get("event_id", ""), {}).get("confidence_pct", 50)) < high and directional_grade(record)]
        wins = sum(directional_grade(record) == "WIN" for record in selected)
        output.append({"bucket": f"{low}-{high - 1}", "N": len(selected), "wins": wins, "losses": len(selected) - wins, "observed_win_rate": round(wins / len(selected) * 100, 2) if selected else None})
    return output


def main() -> int:
    config = read_json(CONFIG_PATH, {})
    signals = read_json(SIGNALS_PATH, {})
    history = read_json(HISTORY_PATH, {})
    if not isinstance(config, dict) or not isinstance(signals, dict) or not isinstance(history, dict):
        print("Task 2 inputs are missing or invalid", file=sys.stderr)
        return 1
    historical = [item for item in signals.get("records", []) if isinstance(item, dict) and item.get("mode") == "historical_reconstruction"]
    upcoming = [item for item in signals.get("records", []) if isinstance(item, dict) and item.get("mode") != "historical_reconstruction"]
    rule_map = series_rule_map(config)
    generated_at = datetime.now(timezone.utc).isoformat()
    contexts: dict[str, dict] = {}
    in_sample_contexts: dict[str, dict] = {}
    for record in sorted(historical, key=lambda item: str(item.get("release_date", ""))):
        contexts[str(record.get("event_id"))] = confidence_for(record, historical, rule_map, config, walk_forward=True)
        in_sample_contexts[str(record.get("event_id"))] = confidence_for(record, historical, rule_map, config, walk_forward=False)
    for record in upcoming:
        contexts[str(record.get("event_id"))] = confidence_for(record, historical, rule_map, config, walk_forward=False)
    updated_records = []
    for record in signals.get("records", []):
        updated = dict(record)
        if str(record.get("event_id")) in contexts:
            updated["confidence"] = contexts[str(record.get("event_id"))]
        updated_records.append(updated)
    updated_signals = dict(signals)
    updated_signals["generated_at"] = generated_at
    updated_signals["confidence_version"] = config["confidence"]["version"]
    updated_signals["records"] = updated_records
    write_json_atomic(SIGNALS_PATH, updated_signals)

    history_by_id = {str(item.get("event_id")): item for item in history.get("records", []) if isinstance(item, dict)}
    updated_history_records = []
    for record in history.get("records", []):
        updated = dict(record)
        context = contexts.get(str(record.get("event_id")))
        if context:
            updated["confidence"] = context
        updated_history_records.append(updated)
    updated_history = dict(history)
    updated_history["generated_at"] = generated_at
    updated_history["confidence_version"] = config["confidence"]["version"]
    updated_history["records"] = updated_history_records
    write_json_atomic(HISTORY_PATH, updated_history)

    reliability_table = []
    for (release_type, series_id), rule in sorted(rule_map.items()):
        enriched_rule = dict(rule)
        enriched_rule["_minimum_reliability_N"] = config["confidence"]["minimum_reliability_N"]
        reliability_table.append(reliability(historical, release_type, series_id, enriched_rule, rule_map))
    confidence_output = {
        "schema_version": 1,
        "generated_at": generated_at,
        "method": "Point-in-time confidence engine using historical FRED-vintage votes and the existing post-release GC=F reaction measure.",
        "limitations": [config["confidence"]["p_value_note"], "GC=F is a COMEX futures proxy, not spot XAUUSD.", "Small samples and historical regime changes can make reliability unstable; confidence is not a probability guarantee."],
        "indicator_reliability": reliability_table,
        "validation": {
            "in_sample": validation_summary(historical, in_sample_contexts, walk_forward=False),
            "walk_forward_out_of_sample": validation_summary(historical, contexts, walk_forward=True),
            "calibration": calibration(historical, contexts),
        },
        "records": contexts,
    }
    write_json_atomic(CONFIDENCE_PATH, confidence_output)

    status = read_json(STATUS_PATH, {})
    prior_sources = status.get("sources") if isinstance(status, dict) else {}
    sources = dict(prior_sources) if isinstance(prior_sources, dict) else {}
    sources["confidence_engine"] = {"name": "Confidence and conviction engine", "url": "data/confidence.json", "state": "ok" if contexts else "unavailable", "last_checked": generated_at, "records": len(contexts), "detail": f"Built confidence contexts for {len(contexts)} signals with reliability, similar-case, walk-forward, and calibration outputs.", "mode": "task2"}
    write_json_atomic(STATUS_PATH, {"schema_version": 1, "generated_at": generated_at, "sources": sources})
    print(json.dumps({"generated_at": generated_at, "historical": len(historical), "upcoming": len(upcoming), "contexts": len(contexts), "in_sample": confidence_output["validation"]["in_sample"], "walk_forward": confidence_output["validation"]["walk_forward_out_of_sample"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
