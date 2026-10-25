"""A captured HTML snapshot of the live page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PageSnapshot:
    """Labelled document dump paired with the URL it came from."""

    label: str
    url: str
    html: str
    captured_at: datetime
