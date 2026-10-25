# <Target> — Báo cáo hành vi web

> Ngày: <YYYY-MM-DD>
> Run ID: `<run_id>` (nếu có)
> Target: `targets/<name>/`
> Phiên bản `wre`: `<version>`
> Trạng thái: draft | reviewed | accepted
> Quy ước: Observed / Inferred / Unknown. Không có body, token, ID thật, prompt thật.

## 1. Mission & phạm vi

| Trường | Giá trị |
|---|---|
| Goal | |
| Target | |
| Account | |
| Allowed | |
| Forbidden | |
| Evidence | |
| Stop | |

## 2. Bối cảnh & bằng chứng

- Entry URL:
- Login URL:
- Chrome port:
- Profile:
- Lệnh đã chạy:
- Artifact:

## 3. Mô hình trang

- Loại trang: SPA / MPA / hybrid (Observed/Inferred)
- Route chính:
- Route cache / workspace ẩn:
- Cơ chế nhập:
- Dấu hiệu đăng nhập:
- Dấu hiệu sẵn sàng:

## 4. Bản đồ DOM

| Landmark | Selector | Raw | Rendered | State | Ghi chú |
|---|---|---|---|---|---|
| | | | | | |

State matrix:

| Landmark | State A | State B | State C |
|---|---|---|---|
| | | | |

## 5. Mô hình tương tác

- Focus:
- Nhập:
- Submit:
- Hủy/Stop:
- Điều hướng:
- Trusted input:
- Overlay/che khuất:

## 6. Vòng đời phiên

```text
boot → hydrate → auth_check → idle → active → settled
                         ↘ auth_required
                                      ↘ error
```

| State | Tín hiệu quan sát | Ghi chú |
|---|---|---|
| | | |

## 7. Bản đồ network

| Path | Method | Pha | Vai trò | Bằng chứng |
|---|---|---|---|---|
| | | | | |

Telemetry/nhiễu:

## 8. Truyền phát

- Transport chính:
- EventSource:
- WebSocket:
- fetch-stream:
- Tín hiệu hoàn tất:
- Giải thích nếu `sse=0`:

## 9. Chuỗi hành động

### Setup

| # | Action | Tiền điều kiện | Bất biến | Timeout |
|---|---|---|---|---|
| | | | | |

### Turn

| # | Action | Tiền điều kiện | Bất biến | Timeout |
|---|---|---|---|---|
| | | | | |

Biến:

## 10. Bằng chứng & tiêu chí chấp nhận

| Tiêu chí | Kỳ vọng | Thực tế | Pass? |
|---|---|---|---|
| steps | | | |
| exceptions | 0 | | |
| console_errors | 0 | | |
| requests | | | |
| probe lists | đủ 6 | | |
| page.ready_state | complete | | |

Lệnh tái lập:

```bash
```

## 11. Rủi ro & điều chưa biết

| Rủi ro | Mức | Phát hiện | Giảm thiểu |
|---|---|---|---|
| | | | |

Unknown:

## 12. Code gate

- [ ] Đã trả lời state machine.
- [ ] Selector đã kiểm tra raw/rendered.
- [ ] Request ↔ action đã rõ.
- [ ] Transport stream đã rõ.
- [ ] Tín hiệu hoàn tất UI + network đã rõ.
- [ ] Không dùng sleep làm chờ chính.
- [ ] Artifact chứng minh.
- [ ] Rủi ro đã liệt kê.
- [ ] Không có dữ liệu nhạy cảm.
- [ ] Người dùng đã chấp nhận.
