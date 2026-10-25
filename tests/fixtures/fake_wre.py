#!/usr/bin/env python3
"""Deterministic stand-in for the Rust wre CLI used by unit tests."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ARGV = sys.argv[1:]


def record() -> None:
    destination = os.getenv("FAKE_WRE_ARGV")
    if destination:
        Path(destination).write_text(json.dumps(ARGV), encoding="utf-8")


def emit(value: object) -> None:
    print(json.dumps(value))
    raise SystemExit(0)


def main() -> None:
    record()

    if os.getenv("FAKE_WRE_FAIL"):
        print("fake wre failure", file=sys.stderr)
        raise SystemExit(3)

    if "--version" in ARGV:
        print("wre 9.9.9")
        return

    if os.getenv("FAKE_WRE_BAD_JSON"):
        print("not json")
        return

    if os.getenv("FAKE_WRE_BAD_TEMPLATE") and "template" in ARGV:
        emit({"pages": 1, "first_page": "a", "skeleton": "x", "slots": []})

    if "env" in ARGV and "script" in ARGV:
        print("(() => ({ navigator: { webdriver: false } }))()")
        return

    if "probe" in ARGV and "emit" in ARGV:
        name = ARGV[ARGV.index("--name") + 1] if "--name" in ARGV else "__WRE"
        source = (
            "(function () { var root = {"
            " drain: function () { return {reads: [], calls: [], events: [],"
            " network: [], sse: [], websocket: [], notes: []}; }"
            " }; })();"
        )
        emit({"name": name, "source": source, "bytes": len(source)})

    if "browser" in ARGV:
        emit({"running": True, "port": 9333})

    if "capture" in ARGV:
        emit({"id": "cap-1", "dir": "/tmp/cap", "requests": 1, "probes": ["surface"]})

    if "template" in ARGV and "diff" in ARGV:
        pages = [a for a in ARGV[ARGV.index("diff") + 1:] if not a.startswith("--")]
        if len(pages) < 2:
            print(f"fake wre template diff needs two pages, got {pages}", file=sys.stderr)
            raise SystemExit(2)
        emit(
            {
                "pages": len(pages),
                "first_page": Path(pages[0]).name,
                "reduction_ratio": 0.5,
                "skeleton": '[document]\n  [p] "fake"  ← [dynamic]\n',
                "slots": [
                    {
                        "path": "document[1]/html[1]/body[1]/p[1]",
                        "tag": "p",
                        "role": "content",
                        "text": "fake",
                        "attributes": [],
                    }
                ],
            }
        )

    if "markers" in ARGV:
        emit(
            [
                {
                    "name": "webdriver-true",
                    "group": "navigator",
                    "kind": "presence",
                    "source": "Object.defineProperty(Navigator.prototype,'webdriver',{get(){return true}});",
                    "note": "test marker",
                }
            ]
        )

    if "pools" in ARGV:
        emit({"markers": ["webdriver-true"], "pools": [["webdriver-true"]]})

    if "sweep" in ARGV:
        emit({"baselines": 2, "arms": [], "attributed": []})

    if "show" in ARGV:
        emit({"id": "cap-1", "requests": 1})

    print(f"fake wre does not understand: {ARGV}", file=sys.stderr)
    raise SystemExit(2)


if __name__ == "__main__":
    main()
