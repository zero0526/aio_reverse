"""``web snapshot`` and ``web skeleton`` commands for template analysis."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from aio_reverse.application.use_cases.analyze_template import (
    AnalyzeTemplateUseCase,
)
from aio_reverse.application.use_cases.capture_page_snapshot import (
    CapturePageSnapshotUseCase,
)
from aio_reverse.composition import (
    build_registry,
    build_session,
    build_snapshot_store,
    build_toolkit,
    load_config,
)


def configure(subparsers: argparse._SubParsersAction) -> None:
    snapshot = subparsers.add_parser(
        "snapshot",
        help="save the live page HTML as a labelled snapshot for template diff",
    )
    snapshot.add_argument("target", help="configured target name")
    snapshot.add_argument(
        "--label",
        required=True,
        help="state name such as 'home' or 'thread' (part of the file name)",
    )
    snapshot.add_argument(
        "--json", action="store_true", help="print snapshot metadata as JSON"
    )
    snapshot.set_defaults(handler=run_snapshot)

    skeleton = subparsers.add_parser(
        "skeleton",
        help="differential template analysis of two or more saved HTML pages",
    )
    skeleton.add_argument(
        "--page",
        action="append",
        required=True,
        metavar="PATH",
        help="HTML page to include; repeat with at least two distinct states",
    )
    skeleton.add_argument(
        "--xpath",
        action="store_true",
        help="include canonical XPath in the skeleton",
    )
    skeleton.add_argument(
        "--json",
        action="store_true",
        help="print pages, reduction_ratio, skeleton and slots as JSON",
    )
    skeleton.set_defaults(handler=run_skeleton)


def run_snapshot(args: argparse.Namespace) -> int:
    config = load_config()
    target = build_registry(config).resolve(args.target)
    toolkit = build_toolkit(config)
    session = build_session(config, toolkit, target)
    use_case = CapturePageSnapshotUseCase(session, build_snapshot_store(config))
    try:
        captured = use_case.execute(args.label)
    finally:
        session.close(keep_browser=True)

    payload = {
        "target": target.name,
        "label": captured.snapshot.label,
        "url": captured.url,
        "path": str(captured.snapshot.path),
        "bytes": captured.snapshot.bytes,
        "sha256": captured.snapshot.sha256,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"snapshot {payload['path']}")
        print(f"url {payload['url']}")
        print(f"bytes {payload['bytes']} sha256 {payload['sha256']}")
    return 0


def run_skeleton(args: argparse.Namespace) -> int:
    pages = [Path(value) for value in args.page]
    toolkit = build_toolkit(load_config())
    analysis = AnalyzeTemplateUseCase(toolkit).execute(pages, xpath=args.xpath)

    if args.json:
        print(
            json.dumps(
                {
                    "pages": analysis.pages,
                    "reduction_ratio": analysis.reduction_ratio,
                    "skeleton": analysis.skeleton,
                    "slots": analysis.slots,
                },
                indent=2,
            )
        )
        return 0

    print(analysis.skeleton)
    print("-" * 50)
    print(
        f"Analyzed {analysis.pages} pages. "
        f"Token / text reduction: {analysis.reduction_ratio * 100:.1f}%"
    )
    return 0
