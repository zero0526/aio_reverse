# Target: chatgpt

Cấu hình này mô tả một phiên ChatGPT do con người đăng nhập thủ công. Không có
credential, cookie hay token nào được lưu trong repo.

## Thành phần

| File | Vai trò |
|---|---|
| `target.json` | URL, biểu thức kiểm tra đăng nhập/ready, probe Rust, script mặc định |
| `scripts/new_chat.json` | Mở cuộc trò chuyện mới trước lượt đo |
| `scripts/send_prompt.json` | Gõ prompt, gửi, chờ phản hồi stream xong |

## Selector đã xác nhận (2026-10-25)

ChatGPT hiện dùng composer ProseMirror và không còn `#prompt-textarea` hay
`[data-message-author-role]`:

| Mục đích | Selector |
|---|---|
| Composer | `form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]` |
| Composer trang chủ | `form[data-chatgpt-composer][data-composer-placement="home"]` |
| Nút gửi | `form[data-chatgpt-composer] button[aria-label="Send"]` |
| Nút dừng stream | `button[aria-label="Stop"]` |
| Chat mới | `button[aria-label="New chat"]` |
| Tin nhắn assistant | `h4[data-conversation-role="assistant"]` |
| Đăng nhập | `button[aria-label="Open profile menu"]` |

Các primitive `click`/`count`/`wait_*` chỉ xét phần tử **đang render**. Điều này
bắt buộc vì ChatGPT giữ DOM của route cũ trong một workspace `display:none`;
selector toàn cục sẽ đếm cả tin nhắn ẩn.

Khi một selector không còn khớp, lệnh chạy sẽ fail loud với đúng bước và selector.
Dùng các lệnh handover để dò lại DOM trước khi sửa file:

```bash
uv run aio-reverse web state chatgpt
uv run aio-reverse web evaluate chatgpt "document.querySelectorAll('h4[data-conversation-role]').length"
```

Chỉ sử dụng với tài khoản bạn sở hữu hoặc được phép kiểm thử, và tuân thủ điều
khoản dịch vụ của dịch vụ mục tiêu.
