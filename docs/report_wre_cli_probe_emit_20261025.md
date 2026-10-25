# Báo cáo nghiệm thu — Phase 2: `wre probe emit` + `--profile`

Ngày: 2026-10-25

## 1. Mục tiêu task

Mở đường cho Python lấy probe chuẩn từ Rust qua CLI, thay vì tự viết JavaScript; đồng thời cho phép chỉ định Chrome profile bền khi mở browser hoặc capture.

## 2. Đã làm được gì (chi tiết thay đổi)

- Thêm subcommand top-level `wre probe emit` với các flag:
  `--target`, `--name`, `--preset`, `--property`, `--method`, `--event`,
  `--no-network`, `--workers`, `--no-stealth`, `--no-call-sites`, `--no-sse`, `--no-websocket`.
- `--target` đọc manifest `targets/<name>.toml`; kết hợp với bất kỳ flag override nào đều bị từ chối với thông điệp rõ ràng.
- Preset chỉ nhận `fingerprint`, `minimal`, `none`; giá trị khác fail loud.
- `--property`/`--method` bắt buộc dạng `holder.name` (split tại dấu `.` cuối); thiếu dấu chấm fail loud kèm giá trị sai.
- Output: `--json` trả `{"name", "source", "bytes"}`; plain in JavaScript thô ra stdout.
- `wre-target::Probe` có thêm `sse`/`websocket` (mặc định `true`), `Probe::default()` viết tay để giữ default đúng, `to_spec()` truyền cờ xuống `SurfaceSpec`.
- `wre browser` và `wre capture` nhận `--profile <path>`; mặc định vẫn là `artifacts/chrome/profile-<port>`; thư mục profile được tạo trước khi launch.
- Thêm helper `prepare_profile_dir` dùng chung cho cả browser và capture (tránh lặp logic tạo thư mục).

## 3. Làm tại đâu (file & vị trí)

| File | Nội dung |
|---|---|
| `libs/web-re-toolkit/crates/wre-cli/src/args.rs` | `Command::Probe`, `ProbeCommand::Emit`; `profile` trong `Browser`/`Capture` |
| `libs/web-re-toolkit/crates/wre-cli/src/probe_cmd.rs` | `run`, `emit`, `build_spec`, `split_trap` |
| `libs/web-re-toolkit/crates/wre-cli/src/main.rs` | `mod probe_cmd`; dispatch `Command::Probe`; truyền `profile` |
| `libs/web-re-toolkit/crates/wre-cli/src/capture_cmd.rs` | `browser(..., profile)`; `CaptureArgs.profile`; `prepare_profile_dir` |
| `libs/web-re-toolkit/crates/wre-target/src/lib.rs` | `Probe.sse`, `Probe.websocket`, `Default` thủ công, `default_true`, `to_spec()` |

## 4. Hướng dẫn và kết quả verify

Lệnh:

```bash
cd libs/web-re-toolkit
cargo test -p wre-target -p wre-cli
cargo build --release -p wre-cli
```

Kết quả:

```text
running 9 tests (wre-target)
test result: ok. 9 passed; 0 failed
Finished `release` profile [optimized] target(s)
```

Kiểm tra emit:

```bash
wre --json probe emit --name __WRE \
  --property Navigator.prototype.userAgent \
  --method HTMLCanvasElement.prototype.toDataURL \
  --no-sse --no-websocket
```

Kết quả: JSON hợp lệ, `name=__WRE`, `bytes=16723`; source ghi ra file và `node --check` pass.

Kiểm tra manifest:

```bash
wre --root libs/web-re-toolkit --json probe emit --target example
```

Kết quả: `bytes=19590`, `node --check` pass.

Kiểm tra fail loud:

```text
wre probe emit --preset nope
error: unknown probe preset "nope"; expected fingerprint, minimal or none
exit=1

wre probe emit --property nodot
error: --property expects holder.property, got "nodot"
exit=1

wre probe emit --target example --preset minimal
error: --target reads probe rules from targets/<name>.toml; do not combine it with --preset or trap flags
exit=1
```

Kiểm tra help:

```bash
wre browser --help | grep -- --profile
wre capture --help | grep -- --profile
```

Cả hai hiển thị `--profile <PROFILE>`.
