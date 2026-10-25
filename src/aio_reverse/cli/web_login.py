"""``web login`` command: open the target and wait for a human sign-in."""

from __future__ import annotations

import argparse
import json

from aio_reverse.composition import (
    build_registry,
    build_session,
    build_toolkit,
    load_config,
)


def configure(subparsers: argparse._SubParsersAction) -> None:
    login = subparsers.add_parser(
        "login", help="open Chrome and wait for a human to sign in"
    )
    login.add_argument("target", help="configured target name")
    login.add_argument(
        "--timeout",
        type=float,
        default=300.0,
        help="seconds to wait for the sign-in check (default: 300)",
    )
    login.set_defaults(handler=run_login)


def run_login(args: argparse.Namespace) -> int:
    config = load_config()
    target = build_registry(config).resolve(args.target)
    toolkit = build_toolkit(config)
    session = build_session(config, toolkit, target)
    try:
        page = session.login(timeout_s=args.timeout)
    finally:
        session.close(keep_browser=True)

    print(json.dumps({"target": target.name, "page": page}, indent=2))
    return 0
