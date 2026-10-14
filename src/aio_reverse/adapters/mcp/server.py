"""MCP Server Controller for handling AI Agent requests."""

import sys
import json
from aio_reverse.adapters.mcp.tools import TOOLS


class McpServerController:
    """Manages MCP stdio transport and routes calls to Application Use Cases."""

    def __init__(self):
        # Skeleton: Holds references to instantiated Use Cases
        pass

    def run_stdio(self):
        """Runs the main stdio loop listening for JSON-RPC MCP requests."""
        # Skeleton: Can integrate with official `mcp` Python SDK
        print("[AIO-Reverse] MCP Server Skeleton initialized.", file=sys.stderr)
