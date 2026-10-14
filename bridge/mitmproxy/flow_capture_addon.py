"""Mitmproxy Addon Skeleton for AIO-Reverse.

Captures request/response pairs, redacts credentials, and writes structured records.
"""

class FlowCaptureAddon:
    def request(self, flow):
        pass

    def response(self, flow):
        pass

addons = [FlowCaptureAddon()]
