"""Application configuration and environment paths."""

import os
from dataclasses import dataclass, field
from pathlib import Path

# Resolve project root (4 levels up from infrastructure/config.py)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent


@dataclass(frozen=True)
class AppConfig:
    """Central configuration for tools, timeouts, and workspaces."""

    # Base data directory: defaults to <PROJECT_ROOT>/data, customizable via AIO_DATA_DIR
    base_data_dir: Path = field(
        default_factory=lambda: Path(
            os.getenv("AIO_DATA_DIR", str(PROJECT_ROOT / "data"))
        )
    )

    # Database directory & file path
    @property
    def db_dir(self) -> Path:
        return self.base_data_dir / "db"

    @property
    def db_path(self) -> Path:
        return self.db_dir / "aio_reverse.db"

    @property
    def sqlite_url(self) -> str:
        return f"sqlite:///{self.db_path}"

    # Workspaces and other data locations
    @property
    def targets_dir(self) -> Path:
        return self.base_data_dir / "targets"

    @property
    def captures_dir(self) -> Path:
        return self.base_data_dir / "captures"

    @property
    def cache_dir(self) -> Path:
        return self.base_data_dir / "cache"

    @property
    def output_dir(self) -> Path:
        return self.base_data_dir / "output"

    workspace_dir: Path = Path("/tmp/aio_reverse")
    jadx_path: str = "jadx"
    mitmproxy_port: int = 8080
    unidbg_endpoint: str = "http://127.0.0.1:9999"
    default_timeout_seconds: int = 30

    def ensure_directories(self) -> None:
        """Ensures that all critical data directories exist on disk."""
        self.db_dir.mkdir(parents=True, exist_ok=True)
        self.targets_dir.mkdir(parents=True, exist_ok=True)
        self.captures_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
