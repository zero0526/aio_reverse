"""Use case: capture a labelled HTML snapshot of the live page."""

from __future__ import annotations

from dataclasses import dataclass

from aio_reverse.application.ports.web_session_port import (
    IHtmlSnapshotStore,
    IWebSession,
    SnapshotFile,
)


@dataclass(frozen=True)
class CapturedSnapshot:
    """Where the snapshot was taken and where it was stored."""

    url: str
    snapshot: SnapshotFile


class CapturePageSnapshotUseCase:
    """Dumps the live document, persists it, and returns metadata only.

    The caller owns the session: this use case neither opens nor closes it.
    """

    def __init__(self, session: IWebSession, store: IHtmlSnapshotStore) -> None:
        self._session = session
        self._store = store

    def execute(self, label: str) -> CapturedSnapshot:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("snapshot label must be a non-empty string")

        page = self._session.capture_page(label.strip())
        snapshot = self._store.write(
            self._session.target.name, page.label, page.html
        )
        return CapturedSnapshot(url=page.url, snapshot=snapshot)
