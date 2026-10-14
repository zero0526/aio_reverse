"""Mitmproxy Adapter implementing INetworkCapturePort."""

from pathlib import Path
from aio_reverse.application.ports.network_capture_port import INetworkCapturePort
from aio_reverse.domain.entities.endpoint import ApiEndpoint


class MitmproxyAdapter(INetworkCapturePort):
    """Interacts with mitmdump daemon and processes flow dumps."""

    def start_capture_session(self, port: int = 8080) -> str:
        # Skeleton: Spawns mitmdump with bridge/mitmproxy/flow_capture_addon.py
        return "mitm_session_dummy_id"

    def stop_capture_session(self, session_id: str) -> Path:
        # Skeleton: Flushes dump and terminates proxy process
        return Path("/tmp/aio_reverse_flows.dump")

    def extract_observed_endpoints(self, dump_path: Path) -> list[ApiEndpoint]:
        # Skeleton: Parses dump file and redacts Authorization / Cookies
        return []
