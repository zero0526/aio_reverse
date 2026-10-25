"""MCP server exposing web target tools over local stdio."""

from __future__ import annotations

from dataclasses import dataclass

from mcp.server.mcpserver import MCPServer

from aio_reverse.adapters.mcp.session_registry import SessionRegistry
from aio_reverse.adapters.mcp.web_tools import (
    WebToolServices,
    register_web_tools,
)
from aio_reverse.application.ports.toolkit_port import IToolkitPort
from aio_reverse.composition import (
    build_registry,
    build_session,
    build_snapshot_store,
    build_store,
    build_toolkit,
    load_config,
)
from aio_reverse.infrastructure.config import AppConfig

INSTRUCTIONS = (
    "Drive web targets configured under targets/<name>/target.json. "
    "Run 'aio-reverse web login <target>' once for a human sign-in before "
    "web_open. Use web_run_script for measured turns and the click/type/"
    "evaluate/navigate tools for exploration. Only use accounts you own or "
    "are authorized to test."
)


@dataclass(frozen=True)
class WebMcpServer:
    """The MCP server plus the sessions it must close on shutdown."""

    server: MCPServer
    sessions: SessionRegistry

    def run(self) -> None:
        try:
            self.server.run(transport="stdio")
        finally:
            self.sessions.close_all()


def build_server(
    config: AppConfig | None = None,
    toolkit: IToolkitPort | None = None,
) -> WebMcpServer:
    """Build the tool surface without opening Chrome or contacting a target."""
    if config is None:
        config = load_config()
    if toolkit is None:
        toolkit = build_toolkit(config)

    targets = build_registry(config)
    store = build_store(config)
    sessions = SessionRegistry(
        targets, lambda target: build_session(config, toolkit, target)
    )
    services = WebToolServices(
        targets, store, sessions, toolkit, build_snapshot_store(config)
    )
    server = MCPServer(
        name="aio-reverse",
        version="0.1.0",
        instructions=INSTRUCTIONS,
    )
    register_web_tools(server, services)
    return WebMcpServer(server=server, sessions=sessions)
