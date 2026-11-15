#!/usr/bin/env python3
"""Notify an optional webhook when generated source health is not OK."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "data" / "status.json"
FAILURE_STATES = {"unavailable", "stale", "fallback", "error"}


def load_status() -> dict:
    try:
        payload = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read generated status: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("sources"), dict):
        raise RuntimeError("generated status has no valid sources object")
    return payload


def failures(status: dict) -> list[dict]:
    output = []
    for key, item in status["sources"].items():
        if not isinstance(item, dict):
            output.append({"key": key, "name": key, "state": "error", "detail": "source status entry is invalid"})
            continue
        state = str(item.get("state", "unavailable"))
        if state in FAILURE_STATES:
            output.append({"key": key, "name": str(item.get("name", key)), "state": state, "detail": str(item.get("detail", "No detail supplied.")), "last_checked": item.get("last_checked")})
    return output


def github_context() -> tuple[str, str]:
    repository = os.environ.get("GITHUB_REPOSITORY", "Gold Macro Signal")
    run_url = ""
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    if repository and run_id:
        run_url = f"{server}/{repository}/actions/runs/{run_id}"
    return repository, run_url


def build_payload(items: list[dict], status: dict) -> dict:
    repository, run_url = github_context()
    lines = [f"Gold Macro Signal source-health alert ({repository})", f"Status generated: {status.get('generated_at', 'unknown')}"]
    for item in items:
        lines.append(f"- {item['name']}: {item['state']} — {item['detail']}")
    if run_url:
        lines.append(f"GitHub Actions run: {run_url}")
    lines.append("Dashboard: https://victorrufus333-jpg.github.io/Goldmacro/?view=status")
    text = "\n".join(lines)
    # `content` supports Discord; `text` supports Slack-style incoming webhooks.
    return {"text": text, "content": text, "source_failures": items, "generated_at": status.get("generated_at")}


def send(webhook_url: str, payload: dict) -> None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(webhook_url, data=body, headers={"Content-Type": "application/json", "User-Agent": "GoldMacroSignal/1.0"}, method="POST")
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status < 200 or response.status >= 300:
            raise RuntimeError(f"webhook returned HTTP {response.status}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Notify a webhook about non-OK generated source states")
    parser.add_argument("--dry-run", action="store_true", help="print the redacted payload without sending")
    args = parser.parse_args()
    status = load_status()
    items = failures(status)
    if not items:
        print("All generated data sources are healthy; no notification needed.")
        return 0
    payload = build_payload(items, status)
    if args.dry_run:
        print(json.dumps(payload, indent=2))
        return 0
    webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print(f"Source-health alert needed for {len(items)} source(s), but ALERT_WEBHOOK_URL is not configured.", file=sys.stderr)
        return 0
    try:
        send(webhook_url, payload)
    except (OSError, urllib.error.URLError, RuntimeError) as exc:
        print(f"Source-health webhook delivery failed: {exc}", file=sys.stderr)
        return 1
    print(f"Source-health alert sent for {len(items)} source(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
