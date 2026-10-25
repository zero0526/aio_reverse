"""``web probe`` command: print the Rust probe JavaScript for a target."""

from __future__ import annotations

import argparse

from aio_reverse.composition import (
    build_registry,
    build_toolkit,
    load_config,
)


def configure(subparsers: argparse._SubParsersAction) -> None:
    probe = subparsers.add_parser(
        "probe", help="print the Rust probe JavaScript for a target"
    )
    probe.add_argument("target", help="configured target name")
    probe.set_defaults(handler=run_probe)


def run_probe(args: argparse.Namespace) -> int:
    config = load_config()
    target = build_registry(config).resolve(args.target)
    toolkit = build_toolkit(config)
    print(toolkit.emit_probe(target.probe))
    return 0
