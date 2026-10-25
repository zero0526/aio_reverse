# AIO-Reverse

**One MCP Server for Web & Mobile Network Traffic and Cryptographic Routine Reverse-Engineering.**

Built following **Clean Architecture (Hexagonal / Ports & Adapters)** with the philosophy: **"Borrow, Don't Write"**.

---

## 🏗 Project Architecture

```text
aio_reverse/
├── libs/web-re-toolkit/            # [RUST TOOLKIT] wre-probe, wre-target, wre-cli
├── targets/<name>/                 # [TARGET CONFIG] target.json + scripts/*.json
│   └── chatgpt/
│
├── sidecars/                       # [STANDALONE ENGINES] One protocol, many languages
│   ├── protocol/                   # v1 contract.json + protocol notes
│   ├── python/                     # "aio-sidecar" client SDK
│   ├── node/                       # ESM host SDK + echo engine
│   ├── rust/                       # "aio-sidecar" crate + echo engine
│   ├── cpp/                        # C++17 header-only host SDK + echo engine
│   └── conformance/                # shared echo fixture + cross-host test suite
│
├── src/aio_reverse/                # [CORE APPLICATION] Clean Architecture in Python
│   ├── domain/                     # Errors and core values
│   ├── application/                # Use cases, ports and orchestration
│   │   ├── action_engine.py        # Executes JSON action scripts
│   │   ├── interactive_session.py  # Target + Chrome + Rust probe lifecycle
│   │   ├── expression_waiter.py    # Page-state polling with loud timeouts
│   │   ├── turn_summary.py         # Per-turn / per-run summaries
│   │   ├── ports/                  # Toolkit, browser session, web session, run store
│   │   └── use_cases/              # run_web_scripts, crypto/API discovery use cases
│   ├── targets/                    # target.json schema, loader, registry, scripts
│   ├── adapters/
│   │   ├── toolkit/wre_cli.py      # Process boundary to the Rust `wre` CLI
│   │   ├── web/cdp/                # Chrome CDP transport, collector, page routing
│   │   ├── mcp/                    # MCP server, session registry, web tools
│   │   └── ...                     # mobile, network, emulator, sidecar
│   ├── infrastructure/             # Config, artifact JSON store, process helpers
│   ├── cli/                        # `aio-reverse web ...` commands
│   ├── composition.py              # Shared dependency wiring for CLI + MCP
│   └── main.py                     # CLI & MCP entrypoint
```

The Rust toolkit owns the stealth probe, browser launch and static capture. Python
stays a thin wrapper: target configuration, action scripts, a persistent Chrome
session, artifacts and agent handover.

---

## 🚀 Quick Start with UV

```bash
cd /data/projects/web-apps/aio_reverse

# Sync virtualenv and dependencies
uv sync

# Build the Rust CLI once
(cd libs/web-re-toolkit && cargo build --release -p wre-cli)

# Discover targets and scripts
uv run aio-reverse web targets
uv run aio-reverse web scripts chatgpt

# Human-in-the-loop sign-in (persistent profile: data/profiles/chatgpt)
uv run aio-reverse web login chatgpt

# One measured turn; artifacts land in data/output/web/chatgpt/<run_id>/
uv run aio-reverse web run chatgpt --script send_prompt --var prompt="ping"

# Inspect or drive the live page
uv run aio-reverse web state chatgpt
uv run aio-reverse web click chatgpt 'form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]'
uv run aio-reverse web type chatgpt "follow-up"
uv run aio-reverse web press chatgpt Enter
```

Running `aio-reverse` without a subcommand (or with `mcp`) starts the MCP server
over local stdio. It exposes 11 tools: `web_targets`, `web_open`,
`web_run_script`, `web_state`, `web_inject_probe`, `web_click`, `web_type`,
`web_press`, `web_evaluate`, `web_navigate`, `web_close`.

## 🧩 Adding a web target

Create `targets/<name>/target.json` plus `targets/<name>/scripts/*.json`; no Python
change is required. See [`targets/chatgpt/README.md`](targets/chatgpt/README.md) for
the schema and selector notes.

`targets/fakechat/` is a local end-to-end fixture backed by
`tests/fixtures/fake_chat_server.py` (HTTP + SSE + WebSocket); it calls no external
service and exists only to verify `drain()` per turn.

## 🔌 Sidecar engines (Node / C++ / Rust)

Engine authors implement only `describe` + `call`; the host SDK owns framing,
sessions, deadlines, events and typed errors. Python talks to every engine
through the same wire protocol v1 and can raise an alert before propagating a
typed error.

```python
from aio_reverse.adapters.sidecar import SidecarSandboxAdapter

with SidecarSandboxAdapter("./my-engine", target="my-engine") as sandbox:
    result = sandbox.execute_snippet("...", "main", [], timeout_ms=2000)
```

See [`sidecars/README.md`](sidecars/README.md) for the engine contracts and
[`sidecars/protocol/README.md`](sidecars/protocol/README.md) for the wire
protocol. Full cross-language checks:

```bash
uv run python -m unittest discover -s sidecars/conformance -v
```

## ⚠️ Authorized use only

- Sign-in is always manual. No credential/cookie/token automation is provided.
- Use only accounts you own or are explicitly authorized to test, and respect the
  target service's terms of service and rate limits.
- `data/profiles/` (Chrome profile, cookies) and `data/output/` (captured prompts,
  bodies, network data) are gitignored. Never commit them.
- The MCP server is local stdio only; `web_evaluate` and `web_navigate` are
  powerful and must not be exposed to untrusted clients.
