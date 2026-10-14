"""Application configuration and environment paths."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    """Central configuration for tools, timeouts, and workspaces."""

    workspace_dir: Path = Path("/tmp/aio_reverse")
    jadx_path: str = "jadx"
    mitmproxy_port: int = 8080
    unidbg_endpoint: str = "http://127.0.0.1:9999"
    default_timeout_seconds: int = 30
