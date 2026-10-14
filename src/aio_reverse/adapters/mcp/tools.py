"""MCP Tool declarations and input schemas."""

TOOLS = [
    {
        "name": "discover_api_surface",
        "description": "Analyze an APK or Web bundle to discover network API endpoints.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string", "description": "Absolute path to target APK or JS file"}
            },
            "required": ["artifact_path"]
        }
    },
    {
        "name": "trace_crypto_routines",
        "description": "Scan target for signing, token generation, or encryption routines.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artifact_path": {"type": "string", "description": "Absolute path to target APK or JS file"}
            },
            "required": ["artifact_path"]
        }
    },
    {
        "name": "emulate_crypto_function",
        "description": "Run extracted crypto routine in an isolated sandbox (V8 / Unidbg).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "routine_name": {"type": "string"},
                "code_snippet": {"type": "string"},
                "arguments": {"type": "array", "items": {"type": "string"}}
            },
            "required": ["routine_name", "code_snippet", "arguments"]
        }
    }
]
