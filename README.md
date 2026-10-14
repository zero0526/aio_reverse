# AIO-Reverse

**One MCP Server for Web & Mobile Network Traffic and Cryptographic Routine Reverse-Engineering.**

Built following **Clean Architecture (Hexagonal / Ports & Adapters)** with the philosophy: **"Borrow, Don't Write"**.

---

## 🏗 Project Architecture

```text
aio_reverse/
├── bridge/                         # [IN-ENGINE SCRIPTS] Scripts running inside third-party tools
│   ├── android/                    # JADX headless bridge script
│   ├── frida_scripts/              # SSL unpinning & javax.crypto.Cipher hooks
│   └── mitmproxy/                  # Mitmproxy flow capture & redaction addon
│
├── sidecars/                       # [STANDALONE SERVICES] Standalone daemons
│   ├── unidbg/                     # Java service running Unidbg for Android .so emulation
│   └── mitmproxy_daemon/           # Standalone proxy daemon configuration
│
├── src/aio_reverse/                # [CORE APPLICATION] Clean Architecture in Python
│   ├── domain/                     # LAYER 1: Core Domain (Entities, Values, Errors)
│   │   ├── entities/               # TargetArtifact, ApiEndpoint, CryptoRoutine, EvidenceRecord
│   │   └── errors.py               # Custom domain exceptions
│   │
│   ├── application/                # LAYER 2: Use Cases & Ports (Abstract Interfaces)
│   │   ├── ports/                  # IDecompilerPort, IDynamicHookPort, INetworkCapturePort,
│   │   │                           # IExecutionSandboxPort, IProcessSupervisorPort
│   │   └── use_cases/              # DiscoverApiSurface, TraceCryptoRoutine, EmulateCryptoExecution
│   │
│   ├── adapters/                   # LAYER 3: Interface Adapters
│   │   ├── mobile/                 # JadxAdapter, FridaAdapter
│   │   ├── web/                    # JsAstAdapter, ChromeCdpAdapter
│   │   ├── network/                # MitmproxyAdapter
│   │   ├── emulator/               # V8SandboxAdapter, BrowserEnvironmentShim, UnidbgAdapter
│   │   └── mcp/                    # MCP ServerController & Tool Registrations
│   │
│   └── infrastructure/             # LAYER 4: Frameworks & OS Drivers
│       ├── process/                # ProcessSupervisor (OS process groups, limits, cleanups)
│       ├── config.py               # Application settings
│       └── main.py                 # CLI & MCP Entrypoint
```

---

## 🚀 Quick Start with UV

```bash
cd /data/projects/web-apps/aio_reverse

# Sync virtualenv and dependencies
uv sync

# Run the MCP Server
uv run aio-reverse
```
