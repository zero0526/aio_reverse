"""Executes validated action scripts against a live browser session."""

from __future__ import annotations

import time
from typing import Any, Mapping

from aio_reverse.application.expression_waiter import ExpressionWaiter
from aio_reverse.application.ports.browser_session_port import IBrowserSessionPort
from aio_reverse.application.ports.web_session_port import StepRecord
from aio_reverse.domain.errors import ActionScriptError
from aio_reverse.targets.action_script import Action, ActionScript, resolve_action

DEFAULT_ACTION_TIMEOUT_S = 30.0


class ActionEngine:
    """Runs one script, resolving templates and recording each step."""

    def __init__(self, session: IBrowserSessionPort) -> None:
        self._session = session
        self._waiter = ExpressionWaiter(session)

    def run(
        self,
        script: ActionScript,
        variables: Mapping[str, object] | None = None,
    ) -> tuple[StepRecord, ...]:
        scope = dict(variables or {})
        missing = sorted(set(script.required_variables()) - set(scope))
        if missing:
            raise ValueError(
                f"action script {script.name!r} requires variables {missing}"
            )

        records: list[StepRecord] = []
        deadline = time.monotonic() + script.timeout_s
        for index, action in enumerate(script.actions):
            context = f"action script {script.name}.actions[{index}]"
            resolved = resolve_action(action, scope, context=context)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ActionScriptError(
                    script.name,
                    index,
                    resolved.type,
                    f"script timeout_s={script.timeout_s:g}s exceeded before step",
                )
            timeout_s = min(
                resolved.timeout_s or DEFAULT_ACTION_TIMEOUT_S, remaining
            )
            started_at = time.time()
            try:
                value = self._execute(resolved, timeout_s)
            except Exception as error:
                raise ActionScriptError(
                    script.name, index, resolved.type, str(error)
                ) from error

            if resolved.save is not None:
                if value is None:
                    raise ActionScriptError(
                        script.name,
                        index,
                        resolved.type,
                        f"save {resolved.save!r} produced no value",
                    )
                scope[resolved.save] = value

            records.append(
                StepRecord(
                    index=index,
                    type=resolved.type,
                    started_at=started_at,
                    ended_at=time.time(),
                    saved=resolved.save,
                    value=value,
                )
            )
            if time.monotonic() > deadline:
                raise ActionScriptError(
                    script.name,
                    index,
                    resolved.type,
                    f"script timeout_s={script.timeout_s:g}s exceeded after step",
                )
        return tuple(records)

    def _execute(self, action: Action, timeout_s: float) -> Any:
        if action.type == "navigate":
            self._session.navigate(action.url, timeout_s=timeout_s)
            return None
        if action.type == "click":
            self._session.click(action.selector, timeout_s=timeout_s)
            return None
        if action.type == "type":
            self._session.click(action.selector, timeout_s=timeout_s)
            self._session.insert_text(action.text)
            return None
        if action.type == "press":
            self._session.press(action.key)
            return None
        if action.type == "wait_visible":
            self._waiter.wait_visible(action.selector, timeout_s)
            return None
        if action.type == "wait_hidden":
            self._waiter.wait_hidden(action.selector, timeout_s)
            return None
        if action.type == "count":
            return self._waiter.count(action.selector, timeout_s)
        if action.type == "wait_count":
            self._waiter.wait_count(
                action.selector, action.greater_than, timeout_s
            )
            return None
        if action.type == "wait_network_quiet":
            self._waiter.wait_network_quiet(action.ms, timeout_s)
            return None
        if action.type == "sleep":
            duration_s = action.ms / 1000.0
            if duration_s > timeout_s:
                raise ValueError(
                    f"sleep {action.ms}ms exceeds the remaining "
                    f"timeout {timeout_s:.3f}s"
                )
            time.sleep(duration_s)
            return None
        if action.type == "evaluate":
            return self._session.evaluate(action.expression, timeout_s=timeout_s)
        raise ValueError(f"unsupported action type {action.type!r}")
