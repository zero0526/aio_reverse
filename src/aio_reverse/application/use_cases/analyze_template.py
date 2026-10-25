"""Use case: differential template analysis over captured HTML pages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from aio_reverse.application.ports.toolkit_port import IToolkitPort


@dataclass(frozen=True)
class TemplateAnalysis:
    """Skeleton, dynamic slots and reduction ratio for a set of pages."""

    pages: int
    skeleton: str
    slots: list[dict[str, Any]]
    reduction_ratio: float


class AnalyzeTemplateUseCase:
    """Validates HTML inputs before delegating to the wre template engine."""

    def __init__(self, toolkit: IToolkitPort) -> None:
        self._toolkit = toolkit

    def execute(
        self,
        pages: Sequence[Path],
        *,
        xpath: bool = False,
    ) -> TemplateAnalysis:
        if len(pages) < 2:
            raise ValueError(
                f"template analysis needs at least 2 HTML pages, got {len(pages)}"
            )
        for page in pages:
            if page.suffix.lower() != ".html":
                raise ValueError(f"template page must be .html, got {page}")
            if not page.is_file():
                raise ValueError(f"template page does not exist: {page}")

        result = self._toolkit.template_diff(pages, xpath=xpath)
        return TemplateAnalysis(
            pages=result["pages"],
            skeleton=result["skeleton"],
            slots=result["slots"],
            reduction_ratio=result["reduction_ratio"],
        )
