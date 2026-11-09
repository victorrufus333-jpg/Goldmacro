#!/usr/bin/env python3
"""Assemble the static site into dist/ without third-party dependencies."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
DATA = ROOT / "data"
DIST = ROOT / "dist"


def copy_tree(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            copy_tree(item, target)
        else:
            shutil.copy2(item, target)


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    copy_tree(SITE, DIST)
    copy_tree(DATA, DIST / "data")

    # Static hosts can resolve these logical views without server-side routing.
    index = DIST / "index.html"
    for view in ("calendar", "status"):
        target = DIST / view / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(index, target)

    routes = {
        "routes": [
            {"path": "/", "title": "Gold Macro Signal"},
            {"path": "/calendar", "title": "Macro Calendar"},
            {"path": "/status", "title": "Source Status"},
        ]
    }
    (DIST / "manus-routes.json").write_text(json.dumps(routes, indent=2) + "\n", encoding="utf-8")
    (DIST / ".nojekyll").write_text("\n", encoding="utf-8")
    print(f"Built {DIST} with {sum(1 for _ in DIST.rglob('*'))} files/directories.")


if __name__ == "__main__":
    main()
