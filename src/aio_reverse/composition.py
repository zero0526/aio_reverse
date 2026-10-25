"""Composition root shared by the CLI and the MCP server."""

from __future__ import annotations

from aio_reverse.adapters.toolkit import WreToolkit
from aio_reverse.adapters.web.cdp import ChromeCdpSession
from aio_reverse.application.interactive_session import InteractiveSession
from aio_reverse.application.ports.toolkit_port import IToolkitPort
from aio_reverse.infrastructure.artifacts import (
    HtmlSnapshotStore,
    RunStore,
)
from aio_reverse.infrastructure.config import AppConfig
from aio_reverse.targets.target_registry import TargetRegistry
from aio_reverse.targets.web_target import WebTargetSpec


def load_config() -> AppConfig:
    config = AppConfig()
    config.ensure_directories()
    return config


def build_registry(config: AppConfig) -> TargetRegistry:
    return TargetRegistry(config.targets_root)


def build_toolkit(config: AppConfig) -> WreToolkit:
    return WreToolkit(config.toolkit_workspace)


def build_store(config: AppConfig) -> RunStore:
    return RunStore(config.web_output_dir)


def build_snapshot_store(config: AppConfig) -> HtmlSnapshotStore:
    return HtmlSnapshotStore(config.web_output_dir)


def build_session(
    config: AppConfig,
    toolkit: IToolkitPort,
    target: WebTargetSpec,
) -> InteractiveSession:
    browser = ChromeCdpSession(
        target.body_capture_patterns,
        stream_payloads=target.stream_payloads,
    )
    return InteractiveSession(
        target,
        toolkit,
        browser,
        config.profile_dir(target.name),
    )
