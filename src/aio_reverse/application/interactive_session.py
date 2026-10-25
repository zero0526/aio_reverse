"""Long-lived interactive session over Chrome and the Rust probe."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from aio_reverse.application.action_engine import ActionEngine
from aio_reverse.application.expression_waiter import ExpressionWaiter
from aio_reverse.application.page_snapshot import PageSnapshot
from aio_reverse.application.probe_network_redaction import redact_probe_network
from aio_reverse.application.ports.browser_session_port import IBrowserSessionPort
from aio_reverse.application.ports.toolkit_port import IToolkitPort
from aio_reverse.application.ports.web_session_port import IWebSession, SessionTurn
from aio_reverse.domain.errors import (
    AuthenticationRequiredError,
    BrowserSessionError,
    ProbeUnavailableError,
)
from aio_reverse.targets.action_script import ActionScript
from aio_reverse.targets.web_target import WebTargetSpec, require_http_url

READY_TIMEOUT_S = 60.0


class InteractiveSession(IWebSession):
    """Drives one target with a persistent Chrome profile and live CDP page."""

    def __init__(
        self,
        target: WebTargetSpec,
        toolkit: IToolkitPort,
        session: IBrowserSessionPort,
        profile_dir: Path,
    ) -> None:
        self._target = target
        self._toolkit = toolkit
        self._session = session
        self._profile_dir = profile_dir
        self._engine = ActionEngine(session)
        self._opened = False

    @property
    def target(self) -> WebTargetSpec:
        return self._target

    def open(self) -> None:
        if self._opened:
            return
        self._toolkit.start_browser(
            self._target.chrome_port, profile=self._profile_dir
        )
        self._session.attach(self._target.chrome_port, self._target.origin)

        url = self._page_url()
        if not url.startswith(self._target.origin):
            self._session.navigate(self._target.entry_url)

        waiter = ExpressionWaiter(self._session)
        waiter.wait_truthy(
            self._target.ready_expression,
            READY_TIMEOUT_S,
            context=f"target {self._target.name!r} ready_expression",
        )
        if self._session.evaluate(self._target.login_expression) is not True:
            raise AuthenticationRequiredError(
                f"target {self._target.name!r} is not signed in; run: "
                f"aio-reverse web login {self._target.name}"
            )

        self.inject_probe()
        self._opened = True

    def login(self, timeout_s: float = 300.0) -> dict[str, Any]:
        self._toolkit.start_browser(
            self._target.chrome_port, profile=self._profile_dir
        )
        self._session.attach(self._target.chrome_port, self._target.origin)

        url = self._page_url()
        if not url.startswith(self._target.origin):
            self._session.navigate(self._target.login_url)

        ExpressionWaiter(self._session).wait_truthy(
            self._target.login_expression,
            timeout_s,
            context=f"sign-in for target {self._target.name!r}",
        )
        self.inject_probe()
        self._opened = True
        return self._session.page_info()

    def run_script(
        self,
        script: ActionScript,
        variables: Mapping[str, object] | None = None,
    ) -> SessionTurn:
        self.open()
        started_at = time.time()
        self._session.begin_turn()
        steps = self._engine.run(script, variables)
        probe = redact_probe_network(
            self._session.drain_probe(),
            self._target.body_capture_patterns,
        )
        page = self._session.page_info()
        env = self._session.snapshot_env(
            self._toolkit.env_script(self._target.env_depth)
        )
        capture = self._session.end_turn()
        return SessionTurn(
            script=script.name,
            variables=dict(variables or {}),
            steps=steps,
            capture=capture,
            probe=probe,
            page=page,
            env=env,
            started_at=started_at,
            ended_at=time.time(),
        )

    def click(self, selector: str) -> None:
        self.open()
        self._session.click(selector)

    def type_text(self, text: str) -> None:
        self.open()
        self._session.insert_text(text)

    def press(self, key: str) -> None:
        self.open()
        self._session.press(key)

    def evaluate(self, expression: str) -> Any:
        self.open()
        return self._session.evaluate(expression)

    def navigate(self, url: str) -> None:
        require_http_url(url, field_name="url", context="web navigate")
        self.open()
        self._session.navigate(url)
        self.inject_probe()

    def inject_probe(self) -> None:
        if self._probe_present():
            return
        source = self._toolkit.emit_probe(self._target.probe)
        self._session.add_init_script(source)
        self._session.evaluate(source)
        if not self._probe_present():
            raise ProbeUnavailableError(
                f"Rust probe was not installed on target {self._target.name!r}"
            )

    def _probe_present(self) -> bool:
        value = self._session.evaluate(
            "typeof window.__WRE === 'object' && window.__WRE !== null"
            " && typeof window.__WRE.drain === 'function'"
        )
        return value is True

    def dump_state(self) -> dict[str, Any]:
        self.open()
        return {
            "page": self._session.page_info(),
            "env": self._session.snapshot_env(
                self._toolkit.env_script(self._target.env_depth)
            ),
        }

    def capture_page(self, label: str) -> PageSnapshot:
        self.open()
        return PageSnapshot(
            label=label,
            url=self._page_url(),
            html=self._session.outer_html(),
            captured_at=datetime.now(timezone.utc),
        )

    def _page_url(self) -> str:
        page = self._session.page_info()
        url = page.get("url")
        if not isinstance(url, str):
            raise BrowserSessionError(
                f"page_info returned a non-string url: {url!r}"
            )
        return url

    def close(self, keep_browser: bool = True) -> None:
        self._session.close()
        self._opened = False
        if not keep_browser:
            self._toolkit.stop_browser(self._target.chrome_port)
