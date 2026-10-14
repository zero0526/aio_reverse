"""Abstract Port for dynamic runtime instrumentation (Frida)."""

from abc import ABC, abstractmethod
from typing import Any, Callable


class IDynamicHookPort(ABC):
    """Port for runtime hooks, SSL unpinning, and memory inspection."""

    @abstractmethod
    def attach_or_spawn(self, package_or_process: str) -> str:
        """Attach to running app or spawn package on target device."""
        ...

    @abstractmethod
    def enable_ssl_unpinning(self, session_id: str) -> bool:
        """Inject universal SSL unpinning scripts into target process."""
        ...

    @abstractmethod
    def monitor_crypto_calls(self, session_id: str, callback: Callable[[dict[str, Any]], None]) -> None:
        """Hook encryption APIs (Cipher, Mac, KeyStore) and stream calls to callback."""
        ...
