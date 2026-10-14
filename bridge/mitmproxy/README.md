# Mitmproxy Bridge Addon

Scripts executed inside `mitmdump` process to intercept, filter, and stream flow data:
- `flow_capture_addon.py`: Intercepts HTTP/WebSocket flows, redacts sensitive authorization tokens, and exports JSON stream.
