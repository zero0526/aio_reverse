"""``web run`` command: execute setup and turn scripts and store artifacts."""

from __future__ import annotations

import argparse
import json

from aio_reverse.application.use_cases.run_web_scripts import (
    RunWebScriptsUseCase,
)
from aio_reverse.composition import (
    build_registry,
    build_session,
    build_store,
    build_toolkit,
    load_config,
)


def configure(subparsers: argparse._SubParsersAction) -> None:
    run = subparsers.add_parser(
        "run", help="run action scripts and write artifacts"
    )
    run.add_argument("target", help="configured target name")
    run.add_argument(
        "--setup-script",
        action="append",
        default=[],
        metavar="NAME",
        help="setup script; repeatable (default: target setup_scripts)",
    )
    run.add_argument(
        "--script",
        action="append",
        default=[],
        metavar="NAME",
        help="measured turn script; repeatable (default: target turn_scripts)",
    )
    run.add_argument(
        "--var",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="template variable available to every script; repeatable",
    )
    run.add_argument(
        "--json", action="store_true", help="print the full result as JSON"
    )
    run.set_defaults(handler=run_web)


def run_web(args: argparse.Namespace) -> int:
    variables = parse_variables(args.var)
    config = load_config()
    target = build_registry(config).resolve(args.target)
    setup_scripts = (
        list(args.setup_script) if args.setup_script else list(target.setup_scripts)
    )
    turn_scripts = (
        list(args.script) if args.script else list(target.turn_scripts)
    )
    if not turn_scripts:
        raise ValueError(
            f"target {target.name!r} has no turn_scripts; pass --script NAME"
        )

    toolkit = build_toolkit(config)
    session = build_session(config, toolkit, target)
    use_case = RunWebScriptsUseCase(session, build_store(config))
    result = use_case.execute(
        turn_scripts, setup_scripts=setup_scripts, variables=variables
    )

    if args.json:
        print(
            json.dumps(
                {
                    "run_id": result.run_id,
                    "run_dir": str(result.run_dir),
                    "turns": result.turns,
                    "setup_steps": result.setup_steps,
                    "summary": result.summary,
                },
                indent=2,
            )
        )
        return 0

    totals = result.summary["totals"]
    print(f"run {result.run_id}")
    print(f"artifacts {result.run_dir}")
    print(
        f"turns {result.turns} setup_steps {result.setup_steps} "
        f"steps {totals['steps']}"
    )
    print(
        f"requests {totals['requests']} "
        f"matched {totals['matched_requests']} "
        f"sse {totals['sse_events']} ws {totals['ws_frames']} "
        f"console_errors {totals['console_errors']} "
        f"exceptions {totals['exceptions']}"
    )
    probe = totals["probe"]
    print(
        f"probe reads {probe['reads']} calls {probe['calls']} "
        f"events {probe['events']} network {probe['network']} "
        f"sse {probe['sse']} websocket {probe['websocket']}"
    )
    return 0


def parse_variables(values: list[str]) -> dict[str, str]:
    """Parse repeated NAME=VALUE flags, rejecting malformed and duplicate keys."""
    variables: dict[str, str] = {}
    for item in values:
        name, separator, value = item.partition("=")
        if not separator or not name.strip():
            raise ValueError(f"--var must look like NAME=VALUE, got {item!r}")
        if name in variables:
            raise ValueError(f"--var {name!r} was provided more than once")
        variables[name] = value
    return variables
