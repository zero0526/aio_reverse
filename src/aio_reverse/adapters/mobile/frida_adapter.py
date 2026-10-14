"""Frida Dynamic Hook Adapter implementing IDynamicHookPort."""

from typing import Any, Callable
from aio_reverse.application.ports.dynamic_hook_port import IDynamicHookPort


class FridaAdapter(IDynamicHookPort):
    """Communicates with Frida server on USB / emulator device."""

    def attach_or_spawn(self, package_or_process: str) -> str:
        # Skeleton: Uses frida.get_usb_device().spawn(...)
        return "session_frida_dummy_id"

    def enable_ssl_unpinning(self, session_id: str) -> bool:
        # Skeleton: Injects bridge/frida_scripts/ssl_unpinning.js
        return True

    def monitor_crypto_calls(self, session_id: str, callback: Callable[[dict[str, Any]], None]) -> None:
        # Skeleton: Injects bridge/frida_scripts/cipher_monitor.js and streams messages
        pass
