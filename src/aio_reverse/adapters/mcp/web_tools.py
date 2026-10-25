"""MCP tools that expose configured web targets to a local agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from mcp.server.mcpserver import MCPServer

from aio_reverse.adapters.mcp.session_registry import SessionRegistry
from aio_reverse.application.ports.toolkit_port import IToolkitPort
from aio_reverse.application.ports.web_session_port import (
    IHtmlSnapshotStore,
    IRunStore,
)
from aio_reverse.application.use_cases.analyze_template import (
    AnalyzeTemplateUseCase,
)
from aio_reverse.application.use_cases.capture_page_snapshot import (
    CapturePageSnapshotUseCase,
)
from aio_reverse.application.use_cases.run_web_scripts import (
    RunWebScriptsUseCase,
)
from aio_reverse.targets.action_script import ActionScript
from aio_reverse.targets.action_script_loader import load_action_script
from aio_reverse.targets.target_registry import TargetRegistry
from aio_reverse.targets.web_target import WebTargetSpec


class WebToolServices:
    """Application calls behind the MCP tools."""

    def __init__(
        self,
        targets: TargetRegistry,
        store: IRunStore,
        sessions: SessionRegistry,
        toolkit: IToolkitPort,
        snapshots: IHtmlSnapshotStore,
        loader: Callable[[WebTargetSpec, str], ActionScript] = load_action_script,
    ) -> None:
        self._targets = targets
        self._store = store
        self._sessions = sessions
        self._toolkit = toolkit
        self._snapshots = snapshots
        self._loader = loader

    def list_targets(self) -> dict[str, Any]:
        return {
            "targets": [
                _target_info(self._targets.resolve(name))
                for name in self._targets.names()
            ]
        }

    def open(self, target_name: str) -> dict[str, Any]:
        session = self._sessions.acquire(target_name)
        session.open()
        state = session.dump_state()
        return {
            "target": target_name,
            "page": state["page"],
            "env": state["env"],
        }

    def run_script(
        self,
        target_name: str,
        script: str,
        variables: Mapping[str, str] | None,
    ) -> dict[str, Any]:
        session = self._sessions.acquire(target_name)
        use_case = RunWebScriptsUseCase(session, self._store, self._loader)
        result = use_case.execute([script], variables=variables)
        return {
            "run_id": result.run_id,
            "run_dir": str(result.run_dir),
            "turn": result.summary["turns"][0],
            "totals": result.summary["totals"],
        }

    def state(self, target_name: str) -> dict[str, Any]:
        return self._sessions.acquire(target_name).dump_state()

    def snapshot(self, target_name: str, label: str) -> dict[str, Any]:
        session = self._sessions.acquire(target_name)
        use_case = CapturePageSnapshotUseCase(session, self._snapshots)
        captured = use_case.execute(label)
        return {
            "target": target_name,
            "label": captured.snapshot.label,
            "url": captured.url,
            "path": str(captured.snapshot.path),
            "bytes": captured.snapshot.bytes,
            "sha256": captured.snapshot.sha256,
        }

    def skeleton(
        self, pages: list[str], xpath: bool = False
    ) -> dict[str, Any]:
        analysis = AnalyzeTemplateUseCase(self._toolkit).execute(
            [Path(page) for page in pages], xpath=xpath
        )
        return {
            "pages": analysis.pages,
            "reduction_ratio": analysis.reduction_ratio,
            "skeleton": analysis.skeleton,
            "slots": analysis.slots,
        }

    def inject_probe(self, target_name: str) -> dict[str, Any]:
        self._sessions.acquire(target_name).inject_probe()
        return {"target": target_name, "probe": "__WRE"}

    def click(self, target_name: str, selector: str) -> dict[str, Any]:
        self._sessions.acquire(target_name).click(selector)
        return {"target": target_name, "clicked": selector}

    def type_text(self, target_name: str, text: str) -> dict[str, Any]:
        self._sessions.acquire(target_name).type_text(text)
        return {"target": target_name, "typed_characters": len(text)}

    def press(self, target_name: str, key: str) -> dict[str, Any]:
        self._sessions.acquire(target_name).press(key)
        return {"target": target_name, "pressed": key}

    def evaluate(self, target_name: str, expression: str) -> dict[str, Any]:
        value = self._sessions.acquire(target_name).evaluate(expression)
        return {"target": target_name, "result": value}

    def navigate(self, target_name: str, url: str) -> dict[str, Any]:
        session = self._sessions.acquire(target_name)
        session.navigate(url)
        return {
            "target": target_name,
            "page": session.dump_state()["page"],
        }

    def close(self, target_name: str, keep_browser: bool) -> dict[str, Any]:
        closed = self._sessions.close(
            target_name, keep_browser=keep_browser
        )
        return {
            "target": target_name,
            "closed": closed,
            "browser": "kept running" if keep_browser else "stopped",
        }


def register_web_tools(server: MCPServer, services: WebToolServices) -> None:
    """Register the web handover tool surface on a server instance."""

    @server.tool(
        name="web_targets",
        description="List configured web targets, their URLs and scripts.",
    )
    def web_targets() -> dict[str, Any]:
        return services.list_targets()

    @server.tool(
        name="web_open",
        description=(
            "Open a target in persistent Chrome, verify sign-in, install the "
            "Rust probe and return the page/environment state. Run "
            "'aio-reverse web login <target>' first when the target is not signed in."
        ),
    )
    def web_open(target: str) -> dict[str, Any]:
        return services.open(target)

    @server.tool(
        name="web_run_script",
        description=(
            "Run one target action script as a measured turn and write "
            "artifacts. 'variables' fill {{name}} placeholders in the script."
        ),
    )
    def web_run_script(
        target: str,
        script: str,
        variables: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        return services.run_script(target, script, variables)

    @server.tool(
        name="web_state",
        description="Return the live page info and environment snapshot.",
    )
    def web_state(target: str) -> dict[str, Any]:
        return services.state(target)

    @server.tool(
        name="web_snapshot",
        description=(
            "Save the live page HTML as a labelled snapshot under "
            "data/output/web/<target>/snapshots/ and return its path, byte "
            "count and sha256 (never the HTML itself). Capture two distinct "
            "states (e.g. 'home' then 'thread') before web_skeleton."
        ),
    )
    def web_snapshot(target: str, label: str) -> dict[str, Any]:
        return services.snapshot(target, label)

    @server.tool(
        name="web_skeleton",
        description=(
            "Differential template analysis of two or more saved HTML pages: "
            "prunes shared boilerplate and returns the skeleton, dynamic "
            "slots and reduction ratio from the Rust wre-template crate."
        ),
    )
    def web_skeleton(
        pages: list[str], xpath: bool = False
    ) -> dict[str, Any]:
        return services.skeleton(pages, xpath)

    @server.tool(
        name="web_inject_probe",
        description="Ensure the Rust probe (window.__WRE) is installed in the page.",
    )
    def web_inject_probe(target: str) -> dict[str, Any]:
        return services.inject_probe(target)

    @server.tool(
        name="web_click",
        description="Click an element in the live page with trusted mouse events.",
    )
    def web_click(target: str, selector: str) -> dict[str, Any]:
        return services.click(target, selector)

    @server.tool(
        name="web_type",
        description=(
            "Insert text into the focused element. Click the input with "
            "web_click first when focus is elsewhere."
        ),
    )
    def web_type(target: str, text: str) -> dict[str, Any]:
        return services.type_text(target, text)

    @server.tool(
        name="web_press",
        description="Press one of Enter, Escape, Tab or Backspace.",
    )
    def web_press(target: str, key: str) -> dict[str, Any]:
        return services.press(target, key)

    @server.tool(
        name="web_evaluate",
        description="Evaluate a JavaScript expression in the live page.",
    )
    def web_evaluate(target: str, expression: str) -> dict[str, Any]:
        return services.evaluate(target, expression)

    @server.tool(
        name="web_navigate",
        description="Navigate the live page to an absolute http(s) URL.",
    )
    def web_navigate(target: str, url: str) -> dict[str, Any]:
        return services.navigate(target, url)

    @server.tool(
        name="web_close",
        description=(
            "Detach from the page. Chrome stays running by default so the "
            "persistent sign-in survives; set keep_browser=false to stop it."
        ),
    )
    def web_close(target: str, keep_browser: bool = True) -> dict[str, Any]:
        return services.close(target, keep_browser)


def _target_info(target: WebTargetSpec) -> dict[str, Any]:
    return {
        "name": target.name,
        "entry_url": target.entry_url,
        "login_url": target.login_url,
        "chrome_port": target.chrome_port,
        "setup_scripts": list(target.setup_scripts),
        "turn_scripts": list(target.turn_scripts),
        "probe_preset": target.probe.preset,
        "body_capture_patterns": list(target.body_capture_patterns),
        "stream_payloads": target.stream_payloads,
    }
