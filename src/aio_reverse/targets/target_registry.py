"""Discovers web target directories under the toolkit targets root."""

from __future__ import annotations

from pathlib import Path

from aio_reverse.targets.target_loader import load_target
from aio_reverse.targets.web_target import WebTargetSpec


class TargetRegistry:
    """Resolves target names to validated target specs."""

    def __init__(self, targets_root: Path) -> None:
        self.targets_root = targets_root.expanduser().resolve()

    def names(self) -> list[str]:
        if not self.targets_root.is_dir():
            raise FileNotFoundError(
                f"targets root does not exist: {self.targets_root}"
            )
        return sorted(
            entry.name
            for entry in self.targets_root.iterdir()
            if entry.is_dir() and (entry / "target.json").is_file()
        )

    def resolve(self, name: str) -> WebTargetSpec:
        if not name.strip():
            raise ValueError("target name must not be empty")
        if name != Path(name).name or name in {".", ".."}:
            raise ValueError(f"invalid target name {name!r}")

        if not self.targets_root.is_dir():
            raise FileNotFoundError(
                f"targets root does not exist: {self.targets_root}"
            )

        directory = self.targets_root / name
        if not (directory / "target.json").is_file():
            known = ", ".join(self.names()) or "none"
            raise ValueError(
                f"unknown web target {name!r}; configured targets: {known}"
            )
        return load_target(directory)
