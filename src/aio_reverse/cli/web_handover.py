"""One-shot handover commands against a live target session."""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable

from aio_reverse.application.interactive_session import InteractiveSession
from aio_reverse.composition import (
    build_registry,
    build_session,
    build_toolkit,
    load_config,
)
from aio_reverse.targets.action_script import PRESS_KEYS


def configure(subparsers: argparse._SubParsersAction) -> None:
    session = subparsers.add_parser(
        "session", help="show the Chrome debugging status for a target"
    )
    session.add_argument("target")
    session.set_defaults(handler=run_session)

    state = subparsers.add_parser(
        "state", help="dump the live page info and environment snapshot"
    )
    state.add_argument("target")
    state.set_defaults(handler=run_state)

    click = subparsers.add_parser("click", help="click an element in the live page")
    click.add_argument("target")
    click.add_argument("selector")
    click.set_defaults(handler=run_click)

    type_text = subparsers.add_parser(
        "type", help="insert text into the focused element"
    )
    type_text.add_argument("target")
    type_text.add_argument("text")
    type_text.set_defaults(handler=run_type)

    press = subparsers.add_parser("press", help="press a whitelisted key")
    press.add_argument("target")
    press.add_argument("key", choices=sorted(PRESS_KEYS))
    press.set_defaults(handler=run_press)

    evaluate = subparsers.add_parser(
        "evaluate", help="evaluate an expression in the live page"
    )
    evaluate.add_argument("target")
    evaluate.add_argument("expression")
    evaluate.set_defaults(handler=run_evaluate)

    navigate = subparsers.add_parser(
        "navigate", help="navigate the live page to an http(s) URL"
    )
    navigate.add_argument("target")
    navigate.add_argument("url")
    navigate.set_defaults(handler=run_navigate)


def run_session(args: argparse.Namespace) -> int:
    config = load_config()
    target = build_registry(config).resolve(args.target)
    status = build_toolkit(config).browser_status(target.chrome_port)
    print(
        json.dumps(
            {"target": target.name, "browser": status}, indent=2
        )
    )
    return 0


def run_state(args: argparse.Namespace) -> int:
    print(
        json.dumps(
            _handover(args, lambda session: session.dump_state()), indent=2
        )
    )
    return 0


def run_click(args: argparse.Namespace) -> int:
    _handover(args, lambda session: session.click(args.selector))
    print(json.dumps({"clicked": args.selector}, indent=2))
    return 0


def run_type(args: argparse.Namespace) -> int:
    _handover(args, lambda session: session.type_text(args.text))
    print(json.dumps({"typed_characters": len(args.text)}, indent=2))
    return 0


def run_press(args: argparse.Namespace) -> int:
    _handover(args, lambda session: session.press(args.key))
    print(json.dumps({"pressed": args.key}, indent=2))
    return 0


def run_evaluate(args: argparse.Namespace) -> int:
    value = _handover(
        args, lambda session: session.evaluate(args.expression)
    )
    print(json.dumps({"result": value}, indent=2))
    return 0


def run_navigate(args: argparse.Namespace) -> int:
    page = _handover(args, lambda session: _navigate(session, args.url))
    print(json.dumps({"page": page}, indent=2))
    return 0


def _navigate(session: InteractiveSession, url: str) -> dict[str, Any]:
    session.navigate(url)
    return session.dump_state()["page"]


def _handover(
    args: argparse.Namespace,
    action: Callable[[InteractiveSession], Any],
) -> Any:
    config = load_config()
    target = build_registry(config).resolve(args.target)
    toolkit = build_toolkit(config)
    session = build_session(config, toolkit, target)
    try:
        return action(session)
    finally:
        session.close(keep_browser=True)
