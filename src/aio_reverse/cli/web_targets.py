"""``web targets`` and ``web scripts`` commands."""

from __future__ import annotations

import argparse

from aio_reverse.composition import build_registry, load_config
from aio_reverse.targets.action_script_loader import load_action_script


def configure(subparsers: argparse._SubParsersAction) -> None:
    targets = subparsers.add_parser(
        "targets", help="list configured web targets"
    )
    targets.set_defaults(handler=run_targets)

    scripts = subparsers.add_parser(
        "scripts", help="list setup and turn scripts of a target"
    )
    scripts.add_argument("target", help="configured target name")
    scripts.set_defaults(handler=run_scripts)


def run_targets(args: argparse.Namespace) -> int:
    config = load_config()
    registry = build_registry(config)
    names = registry.names()
    if not names:
        print(f"no targets configured under {registry.targets_root}")
        return 0
    for name in names:
        target = registry.resolve(name)
        print(f"{target.name}\t{target.entry_url}\tport {target.chrome_port}")
    return 0


def run_scripts(args: argparse.Namespace) -> int:
    config = load_config()
    target = build_registry(config).resolve(args.target)
    for kind, names in (
        ("setup", target.setup_scripts),
        ("turn", target.turn_scripts),
    ):
        for name in names:
            script = load_action_script(target, name)
            description = script.description or "-"
            print(f"{kind}\t{name}\t{description}")
    return 0
