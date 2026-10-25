"""MCP adapter: web target tools over stdio."""

from .server import WebMcpServer, build_server

__all__ = ["WebMcpServer", "build_server"]
