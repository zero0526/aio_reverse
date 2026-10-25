"""Fetches and selects page targets exposed by the Chrome DevTools endpoint."""

from __future__ import annotations

import json
from typing import Any, Sequence
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener

from aio_reverse.domain.errors import BrowserSessionError

_HTTP = build_opener(ProxyHandler({}))


def http_json(url: str, method: str = "GET", timeout_s: float = 10.0) -> Any:
    """Call a DevTools HTTP endpoint and decode its JSON body."""
    request = Request(url, method=method)
    try:
        with _HTTP.open(request, timeout=timeout_s) as response:
            body = response.read()
    except (URLError, OSError) as error:
        raise BrowserSessionError(
            f"CDP endpoint {url} is unreachable: {error}"
        ) from error

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BrowserSessionError(
            f"CDP endpoint {url} returned invalid JSON"
        ) from error


def list_page_targets(host: str, port: int) -> list[dict[str, Any]]:
    """Return the page records from /json/list."""
    url = f"http://{host}:{port}/json/list"
    targets = http_json(url)
    if not isinstance(targets, list):
        raise BrowserSessionError(
            f"{url} returned {type(targets).__name__}, expected a list"
        )
    pages: list[dict[str, Any]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise BrowserSessionError(f"{url} returned a non-object target")
        if target.get("type") == "page":
            pages.append(target)
    return pages


def open_page_target(host: str, port: int) -> dict[str, Any]:
    """Create and return a new about:blank page target."""
    url = f"http://{host}:{port}/json/new?about:blank"
    target = http_json(url, method="PUT")
    if not isinstance(target, dict):
        raise BrowserSessionError(
            f"{url} returned {type(target).__name__}, expected an object"
        )
    return target


def select_page(
    targets: Sequence[dict[str, Any]],
    url_prefix: str | None,
    fallback: bool = False,
) -> dict[str, Any] | None:
    """Pick a page target, restricted to ``url_prefix`` when given.

    An exact URL match wins over a prefix match so that the tab navigated by
    ``wre capture`` is preferred over older tabs on the same origin. With
    ``fallback`` an unmatched prefix yields the first page instead of None.
    """

    pages = [target for target in targets if target.get("type") == "page"]
    if not pages:
        return None
    if url_prefix is None:
        return pages[0]

    matches = [
        target
        for target in pages
        if str(target.get("url") or "").startswith(url_prefix)
    ]
    exact = [
        target
        for target in matches
        if str(target.get("url") or "").rstrip("/") == url_prefix.rstrip("/")
    ]
    chosen = exact or matches
    if chosen:
        return chosen[0]
    return pages[0] if fallback else None
