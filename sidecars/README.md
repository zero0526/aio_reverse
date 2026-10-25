# Sidecar engines

Một lớp giao tiếp chuẩn để Python gọi engine viết bằng **Node/JS, C++ hoặc
Rust** qua cùng một wire protocol. Engine chỉ cần implement xử lý; framing,
session, deadline, event và error serialization do host SDK lo.

Spec giao thức: [`protocol/README.md`](protocol/README.md) (hằng số máy đọc:
[`protocol/contract.json`](protocol/contract.json)). Python dùng lại
[`wre-runtime`](../libs/web-re-toolkit/packages/python) của `web-re-toolkit`,
không tự viết lại framing/error taxonomy.

## Layout

```text
sidecars/
├── protocol/            # contract.json + tóm tắt protocol v1, op "execute"
├── python/              # SDK "aio-sidecar" (aio_sidecar): connect/alert/event
├── node/                # Host SDK ESM + echo engine
│   ├── sdk/src/         # createHost/runStdio/Call/EngineError
│   └── examples/echo*   # echo.mjs + wrapper shell
├── rust/                # crate "aio-sidecar" (serde only) + examples/echo.rs
├── cpp/                 # C++17 header-only SDK + examples/echo.cpp
└── conformance/         # fixture echo.descriptor.json + test 3 host
```

`conformance/fixtures/echo.descriptor.json` là **single source** cho descriptor:
Node đọc runtime, Rust `include_str!`, C++ CMake nhúng vào header. Conformance
so `describe().clients[0]` với fixture và so `hello.schema_hash` trên cả 3 host.

## Cài đặt Python

```python
from aio_reverse.adapters.sidecar import SidecarSandboxAdapter

with SidecarSandboxAdapter("./my-engine", target="my-engine", op="execute") as sandbox:
    result = sandbox.execute_snippet(
        code_or_binary="...", entrypoint="main", arguments=[], timeout_ms=2000
    )
```

Hoặc dùng SDK trực tiếp khi cần điều khiển session/event:

```python
from aio_sidecar import connect

with connect("./my-engine", client_id="probe", on_alert=print) as client:
    session = client.open("my-engine", {"mode": "fast"})
    result = session.call("execute", {"source": "..."}, deadline_ms=1000)
```

Lỗi từ engine đi qua wire dưới dạng typed error, SDK gọi `on_alert(alert)`
**trước khi** raise. Không có callback thì log ERROR qua logger `aio_sidecar`.
Core adapter map sang domain error: `timeout|cancelled → TimeoutError`,
`resource → SandboxResourceLimitError`, còn lại `EmulationFailureError`, luôn
`raise ... from sidecar_error`.

## Viết engine

### Node (ESM, không dependency)

```js
import { runStdio, EngineError, ErrorKind } from "./sdk/src/index.js";

const engine = {
  describe() { return descriptor; },          // v1 descriptor subset
  open(config, ctx) { return { config }; },   // optional, per session
  async call(state, op, params, call) {
    call.check();                             // timeout/cancel cooperative
    call.emit("progress", { step: 1 });       // event trước response
    if (op === "explode") throw new EngineError(ErrorKind.Blocked, "challenge");
    return { ok: true };
  },
  health(state) { return { ok: true }; },     // optional
  diagnostics(state) { return {}; },          // optional, dùng cho op diag
  close(state) {},                            // optional
};

runStdio(engine);
```

`call` có `signal` (AbortSignal), `check()`, `emit(name, data)`, `log(level,
text)`, `input()` và `setOutput(Buffer)` cho binary frame part. Throw khác
`EngineError`/`WreError` → `internal` kèm `detail.engine_exception`.

### Rust (crate `aio-sidecar`, chỉ serde)

```rust
impl Engine for MyEngine {
    fn describe(&self) -> Value { descriptor.clone() }
    fn open(&self, _ctx: &SessionCtx, config: Value) -> Result<Box<dyn Session>, SidecarError> {
        Ok(Box::new(MySession { config }))
    }
}

impl Session for MySession {
    fn call(&mut self, op: &str, params: Value, call: &mut Call<'_>) -> Result<Value, SidecarError> {
        call.check()?;
        if op == "echo" { Ok(params) } else {
            Err(SidecarError::new(ErrorKind::Unsupported, "unknown op"))
        }
    }
}

fn main() {
    run_stdio(MyEngine, HostOptions::default()).expect("sidecar");
}
```

`Session` chỉ bắt buộc `call`; `health/warmup/diagnostics/close` có default.

### C++ (C++17, header-only)

```cpp
class MyEngine final : public aio_sidecar::Engine {
public:
    aio_sidecar::json describe() const override { return descriptor; }
    std::unique_ptr<aio_sidecar::Session> open(
        const aio_sidecar::SessionCtx& ctx, aio_sidecar::json config) override {
        return std::make_unique<MySession>(ctx, std::move(config));
    }
};

int main() {
    MyEngine engine(descriptor);
    aio_sidecar::run_stdio(engine);
}
```

`Call` cung cấp `check()`, `emit`, `log`, `input`, `set_output`, `deadline_ms`.
`SidecarError` mang đúng `ErrorKind`; `std::exception`/panic khác → `internal` +
`detail.engine_exception`. nlohmann/json 3.11.3 được vendor tại
[`cpp/third_party`](cpp/third_party/README.md) (MIT, sha256 ghi trong README).

## Build và test

```bash
uv sync

node --check sidecars/node/sdk/src/*.js sidecars/node/examples/echo.mjs
cargo build --manifest-path sidecars/rust/Cargo.toml --example echo
cargo test  --manifest-path sidecars/rust/Cargo.toml
cmake -S sidecars/cpp -B sidecars/cpp/build -DCMAKE_BUILD_TYPE=Release
cmake --build sidecars/cpp/build -j

uv run python -m unittest discover -s sidecars/python/tests -v
uv run python -m unittest discover -s sidecars/conformance -v
```

Conformance tự tìm 3 engine tại:

| host | mặc định | override |
| --- | --- | --- |
| Node | `sidecars/node/examples/echo` | `SIDECAR_ECHO_NODE` |
| C++ | `sidecars/cpp/build/echo_engine` | `SIDECAR_ECHO_CPP` |
| Rust | `sidecars/rust/target/debug/examples/echo` | `SIDECAR_ECHO_RUST` |

Thiếu binary thì suite **fail loud** kèm lệnh build. Chỉ đặt
`SIDECAR_CONFORMANCE_SKIP_MISSING=1` khi muốn bỏ qua host chưa build.

Bộ case dùng chung: handshake/schema hash/descriptor, open/echo UTF-8/config,
per-call và global event, binary roundtrip, 9 error kind + alert field, native
exception → `internal`, unknown op/target/session, deadline, close/shutdown, và
kill child → `protocol` error. Thêm test core adapter: text/binary `execute`,
map lỗi, missing result fail loud, timeout, reconnect sau transport failure.

## Giới hạn đã biết

- Một engine trên mỗi process; nhiều engine = nhiều process.
- Host xử lý request **tuần tự** (một in-flight/process).
- Cancel cooperative: Rust/C++ phải gọi `check()`; Node quan sát AbortSignal và
  có thể trả `cancelled` ngay.
- Node SDK re-export `frames.js`/`errors.js` từ `libs/web-re-toolkit` bằng đường
  dẫn tương đối, nên gắn với layout monorepo; đóng gói độc lập là việc sau.
- Native exception/panic: Node kèm `stack`; Rust/C++ chỉ có `type` + `message`.
- `SidecarSandboxAdapter.default_deadline_ms` chỉ dùng khi `timeout_ms=None`;
  port mặc định `timeout_ms=1000`.
