"""Main CLI & MCP entrypoint for AIO-Reverse."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from aio_reverse.cli import (
    web_handover,
    web_login,
    web_probe,
    web_run,
    web_surface,
    web_targets,
)
from aio_reverse.domain.errors import AioReverseError

WEB_COMMANDS = (
    web_targets,
    web_probe,
    web_login,
    web_run,
    web_surface,
    web_handover,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aio-reverse",
        description="Drive configured web targets with the Rust wre toolkit.",
    )
    commands = parser.add_subparsers(dest="command")

    web = commands.add_parser("web", help="drive configured web targets")
    web_commands = web.add_subparsers(dest="web_command", required=True)
    for module in WEB_COMMANDS:
        module.configure(web_commands)

    mcp = commands.add_parser("mcp", help="run the MCP server over stdio")
    mcp.set_defaults(handler=run_mcp)
    return parser


def run_mcp(args: argparse.Namespace) -> int:
    from aio_reverse.adapters.mcp import build_server

    build_server().run()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        return run_mcp(args)

    try:
        return handler(args)
    except (AioReverseError, ValueError, FileNotFoundError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
