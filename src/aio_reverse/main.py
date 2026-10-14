"""Main CLI & MCP entrypoint for AIO-Reverse."""

import sys
from aio_reverse.adapters.mcp.server import McpServerController


def main():
    """Starts the AIO-Reverse MCP Server."""
    controller = McpServerController()
    controller.run_stdio()


if __name__ == "__main__":
    main()
