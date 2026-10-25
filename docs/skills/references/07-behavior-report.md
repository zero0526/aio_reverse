# 07 — Báo cáo hành vi và code gate

Mục đích: buộc hiểu biết phải được viết ra, có bằng chứng, trước khi viết code. Báo cáo
là deliverable, không phải ghi chú phụ.

## 1. Khi nào phải viết

Viết báo cáo khi:

- Mở một target mới.
- Sửa selector/action chain vì DOM hoặc network đổi.
- Thêm luồng nghiệp vụ mới (gửi, tải, đăng, tìm kiếm…).
- Điều tra một lỗi mà nguyên nhân chưa rõ.
- Bàn giao cho người/agent khác tiếp tục.

Không cần báo cáo đầy đủ cho thay đổi docs thuần túy hoặc sửa lỗi chính tả.

## 2. Mười một mục bắt buộc

### 1. Mission & phạm vi

Goal, target, tài khoản, allowed/forbidden, evidence, stop conditions.

### 2. Bối cảnh & bằng chứng

Ngày, run ID, target config, phiên bản `wre`, lệnh đã chạy. Không ghi credential.

### 3. Mô hình trang

SPA hay MPA? Route nào? Có route cache/workspace ẩn? Composer/input dạng gì? Điều gì
đánh dấu đã đăng nhập, đã sẵn sàng?

### 4. Bản đồ DOM

Bảng landmark + selector + raw/rendered + trạng thái. Kèm state matrix.

### 5. Mô hình tương tác

Focus, nhập, submit, hủy, điều hướng. Trusted input được dùng ở đâu. Phần tử nào có thể
bị che.

### 6. Vòng đời phiên

State machine: boot → hydrate → auth check → idle → active → settled → error. Mỗi
transition có tín hiệu quan sát được.

### 7. Bản đồ network

Bảng path/method/pha/vai trò/bằng chứng. Không query string, không body. Nêu telemetry.

### 8. Truyền phát

Transport: EventSource, WebSocket, fetch-stream. Metadata: frames, bytes, event counts.
Giải thích nếu `sse=0`.

### 9. Chuỗi hành động

Setup + turn, từng bước với tiền điều kiện, bất biến, timeout, tín hiệu lỗi. Kèm lý do
chọn count delta / Stop hidden / network quiet.

### 10. Bằng chứng & tiêu chí chấp nhận

Artifact path, các con số, checklist pass. Lệnh tái lập.

### 11. Rủi ro, điều chưa biết, điều kiện dừng

DOM churn, A/B, localize, phiên hết hạn, rate limit, anti-automation, cold start. Ghi rõ
Unknown và cách kiểm chứng sau.

## 3. Quy ước độ tin cậy

| Nhãn | Nghĩa | Ví dụ |
|---|---|---|
| **Observed** | Thấy trực tiếp trong artifact/lệnh | "26 request, 17 khớp pattern" |
| **Inferred** | Suy ra từ nhiều quan sát | "Path X là bước chuẩn bị lượt" |
| **Unknown** | Chưa có bằng chứng | "Chưa rõ WebSocket dùng cho loại event nào" |

Không dùng "chắc chắn", "luôn luôn", "hệ thống dùng framework Y" nếu chưa có bằng chứng.
Có thể mô tả hành vi mà không cần biết framework.

## 4. Code gate

Chỉ được viết code khi báo cáo trả lời được **tất cả**:

- [ ] Trang đang ở state machine nào, và tín hiệu của từng state?
- [ ] Selector hành động đã được kiểm tra raw vs rendered ở các state liên quan?
- [ ] Request nào tương ứng với hành động nào?
- [ ] Stream đi bằng transport nào?
- [ ] Tín hiệu hoàn tất của UI và của network là gì?
- [ ] Chuỗi hành động không dựa vào `sleep` làm cơ chế chờ chính?
- [ ] Artifact nào chứng minh chain chạy đúng?
- [ ] Rủi ro nào có thể làm chain gãy, và cách phát hiện?
- [ ] Không có dữ liệu nhạy cảm trong báo cáo?
- [ ] Người dùng đã chấp nhận phạm vi và kế hoạch?

Nếu thiếu bất kỳ mục nào: quay lại cổng tương ứng, không viết code.

## 5. Câu hỏi review

1. Nếu DOM đổi 10%, chỗ nào gãy trước? Selector nào thay được bằng `data-*`?
2. Nếu trang đã có dữ liệu cũ, count có còn đúng không?
3. Nếu stream chậm 2 phút, timeout nào chặn?
4. Nếu phiên hết hạn giữa chain, lỗi nổi lên ở đâu?
5. Nếu telemetry chạy liên tục, `wait_network_quiet` có treo không?
6. Nếu có hai route cùng mount, click có rơi vào bản ẩn không?
7. Nếu chạy lại chain lần hai, setup có idempotent không?
8. Nếu không có network body, kết luận nào vẫn đứng vững?

## 6. Mẫu

Dùng [`../templates/behavior-report.md`](../templates/behavior-report.md). Ca đã hoàn
thành: [`../examples/chatgpt/behavior-report.md`](../examples/chatgpt/behavior-report.md).

## 7. Lưu trữ

- Báo cáo đặt dưới `docs/` hoặc `docs/skills/examples/<target>/`.
- Không chứa body/prompt/token/ID thật.
- Ghi kèm run ID và ngày để tái lập.
- Nếu báo cáo thay thế báo cáo cũ, ghi rõ "thay thế" và lý do; không sửa lịch sử.
