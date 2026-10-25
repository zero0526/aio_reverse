"""Filesystem store for HTML page snapshots consumed by template analysis."""

from __future__ import annotations

from pathlib import Path

from aio_reverse.application.ports.web_session_port import (
    IHtmlSnapshotStore,
    SnapshotFile,
)
from aio_reverse.domain.content_fingerprint import text_metadata
from aio_reverse.infrastructure.artifacts.artifact_naming import safe_name, utc_stamp


class HtmlSnapshotStore(IHtmlSnapshotStore):
    """Writes ``<target>/snapshots/<utc>-<label>.html`` and never overwrites."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def write(self, target_name: str, label: str, html: str) -> SnapshotFile:
        if not isinstance(html, str) or not html.strip():
            raise ValueError("html snapshot must be a non-empty string")

        clean_label = safe_name(label)
        directory = self.root / safe_name(target_name) / "snapshots"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{utc_stamp()}-{clean_label}.html"
        if path.exists():
            raise FileExistsError(
                f"snapshot {path} already exists; relabel or capture again later"
            )

        path.write_text(html, encoding="utf-8")
        size, digest = text_metadata(html)
        return SnapshotFile(label=clean_label, path=path, bytes=size, sha256=digest)
