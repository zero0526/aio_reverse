# Sidecar protocol v1

Lớp giao tiếp giữa Python và engine viết bằng JS/C++/Rust dùng lại **wre sidecar
protocol v1**. Đặc tả đầy đủ nằm ở
[`libs/web-re-toolkit/pages/src/content/docs/reference/protocol.md`](../../libs/web-re-toolkit/pages/src/content/docs/reference/protocol.md).
Tài liệu này chỉ ghi phần đã chuẩn hóa cho `sidecars/`.

## Transport

Consumer spawn engine với `--stdio`. Engine nói frame trên stdin/stdout; stderr chỉ
dành cho log người đọc và không bao giờ là một phần của protocol.

```text
u32be json_len | u32be bin_len | json (UTF-8) | bin
```

Giới hạn: 64 MiB JSON, 512 MiB binary. Frame lỗi/không đúng độ dài là `protocol`
error (hoặc đóng kết nối nếu không xác định được request id).

## Envelopes

```json
{"t":"req","v":1,"id":7,"op":"echo","session":"s1","params":{},"deadline_ms":10000}
{"t":"res","v":1,"id":7,"ok":true,"result":{}}
{"t":"res","v":1,"id":7,"ok":false,"error":{"kind":"bad_input","message":"...","retryable":false}}
{"t":"evt","v":1,"id":7,"event":"progress","data":{"done":1,"total":2}}
{"t":"cancel","v":1,"id":7}
```

`session` chỉ có ở request thuộc session. `deadline_ms` là tùy chọn. Response
tương ứng đúng một request; event có thể có 0..n trước response. Request id do
consumer chọn, duy nhất trên một kết nối.

## Handshake và base ops

Request đầu tiên phải là `hello`. Reply:

```json
{
  "protocol": 1,
  "bundle": "aio",
  "binary_version": "0.1.0",
  "toolkit_version": "0.1.0",
  "schema_hash": "0f3a9c2b1d4e5f60",
  "targets": ["echo"],
  "workers": 1,
  "pid": 51234
}
```

| op | session | params | result |
| --- | --- | --- | --- |
| `hello` | no | `{}` | handshake object |
| `describe` | no | `{}` | bundle descriptor |
| `targets` | no | `{}` | `["echo"]` |
| `metrics` | no | `{}` | `{requests, calls, errors, events, sessions_opened, sessions_open}` |
| `open` | no | `{"target":"echo","config":{}}` | `{"session":"s1","target":"echo","worker":0,"ops":[...]}` |
| `close` | yes | `{}` | `{"closed":true}` |
| `health` | yes | `{}` | `{"ok":true,"target":"echo","detail":{...}}` |
| `warmup` | yes | `{}` | `{"warm":true}` |
| `shutdown` | no | `{}` | `{"stopping":true}`, sau đó engine thoát |
| `diag` | yes | `{}` | `{"target":...,"session":...,"mode":"off","path":null,"report":...}` |

Một engine trên mỗi process. `targets` chỉ chứa descriptor id. Host xử lý request
tuần tự; `cancel` được reader thread bắt ngay lập tức. Node host abort
`AbortSignal` và trả `cancelled`; Rust/C++ đặt cờ để engine quan sát qua
`Call::check()`. `deadline_ms` cũng được kiểm tra cooperative qua `check()` và
host enforce lại sau khi call trả về.

## Errors

`error.kind` là phần ổn định. `retryable` đi kèm trên wire. `detail` là JSON tự do.
`target`/`op` được host điền khi biết.

| kind | ý nghĩa | retryable |
| --- | --- | --- |
| `bad_input` | params/config không hợp lệ, thiếu session | no |
| `unsupported` | không có op/target/option | no |
| `target_drift` | script/target không còn khớp engine | no |
| `blocked` | bị challenge/chặn | yes |
| `timeout` | quá deadline | yes |
| `cancelled` | caller hủy | no |
| `resource` | thiếu tài nguyên hoặc transport hỏng | yes |
| `protocol` | frame/envelope/version sai | no |
| `internal` | engine exception không phân loại | no |

Engine exception tự nhiên (throw/panic/std::exception) được host đóng gói thành
`internal` với `detail.engine_exception = {"type","message","stack"}`.

## Descriptor và schema hash

`describe` trả:

```json
{
  "protocol": 1,
  "bundle": "aio",
  "toolkit_version": "0.1.0",
  "binary_version": "0.1.0",
  "clients": [<engine descriptor>]
}
```

Engine descriptor là subset của v1:

```json
{
  "id": "echo",
  "version": "0.1.0",
  "summary": "...",
  "capabilities": {"needs_v8": false, "needs_chrome": false, "needs_network": false,
                   "stateful": true, "concurrency": "per_session", "warmup_ms": 0},
  "config": {"kind": "json"},
  "ops": [{"name": "echo", "summary": "...", "params": {"kind": "json"},
           "returns": {"kind": "json"}, "streams": [], "deadline_ms": 0}],
  "events": [{"name": "progress", "summary": "...", "data": {"kind": "json"}}],
  "types": {}
}
```

`hello.schema_hash` là **FNV-1a 64-bit** (16 hex thường) trên canonical JSON của
engine descriptor: sort key đệ quy, separator compact, UTF-8 không escape ASCII.
Mọi SDK phải cho cùng một hash với cùng descriptor.

## Op `execute` (dùng bởi core adapter)

```json
params: {
  "entrypoint": "calculateSignature",
  "arguments": [1, "a"],
  "environment": {"navigator": {}},
  "source_kind": "text",
  "source": "<code>",
  "memory_limit_mb": 64
}
bin_part: source bytes khi source_kind = "binary"
result:  {"result": <giá trị engine trả>, "source_bytes": 123}
```

`source` là `null` khi `source_kind` là `binary`.
