# aio-sidecar (Python)

Thin Python SDK around [`wre-runtime`](../../libs/web-re-toolkit/packages/python)
for sidecar engines that speak wire protocol v1. It does not reimplement
framing or the error taxonomy; it adds:

- a normalized entry point (`connect`) and client/session wrappers;
- `on_alert` callbacks fired synchronously **before** a typed error is raised;
- `on_event` callbacks enriched with client/target/op/session context;
- `deadline_ms` in every call;
- spawn failures wrapped as `ResourceError`.

Engine authors only implement an engine; callers only see this SDK.

## Install

```bash
uv sync
```

The package depends on `wre-runtime` through the monorepo path source declared
in `pyproject.toml`.

## Usage

```python
from aio_sidecar import connect

def on_alert(alert):
    print("sidecar alert", alert.kind, alert.phase, alert.op, alert.message)

def on_event(event):
    print("event", event.call_id, event.event, event.data)

with connect("./my-engine", client_id="session-1", on_alert=on_alert,
             on_event=on_event) as client:
    print(client.hello)
    print(client.targets())
    with client.open("my-engine") as session:
        value = session.call("echo", {"hello": "world"}, deadline_ms=1000)
        print(value)
```

Binary payloads travel in the frame binary part:

```python
result, echoed = session.call_with_binary(
    "bytes", {"label": "probe"}, bin_part=b"\x00\x01\x02"
)
```

## Error / alert contract

The SDK re-exports the `wre_runtime.errors` taxonomy (`WreError` subclasses
keyed by `kind`). Every error raised from a call:

1. builds a `SidecarAlert(kind, message, retryable, phase, client_id, target,
   op, session, binary, pid, detail, exception, occurred_at)` with
   `phase in {"connect", "call", "close"}`;
2. invokes `on_alert(alert)` synchronously;
3. re-raises the original `WreError` unchanged.

If no `on_alert` is supplied, the alert is logged to the `aio_sidecar` logger at
ERROR level. If the callback itself raises, that failure is logged and the
original sidecar error is still raised (the callback never masks it).

`connect` wraps `OSError` from spawning the binary in a retryable
`ResourceError` and fires the alert with `phase="connect"`, `op="hello"`.

`Session.close()` and `Client.shutdown()` are best-effort: wire errors are
reported through the alert callback, then swallowed so cleanup can finish.
Explicit `call`/`open` failures always propagate.

## Schema hash

`schema_hash(descriptor)` computes the v1 `hello.schema_hash`: FNV-1a 64-bit
over canonical JSON (recursively sorted keys, compact separators, UTF-8 without
ASCII escaping). Pass the expected value to `connect(expect_schema_hash=...)`
to reject engines whose descriptor drifted.

```python
from aio_sidecar import schema_hash

expected = schema_hash(engine_descriptor)
client = connect("./engine", expect_schema_hash=expected)
```

## Tests

```bash
uv run python -m unittest discover -s sidecars/python/tests -v
```
