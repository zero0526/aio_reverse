# ChatGPT — DOM map

> Đi kèm [`behavior-report.md`](behavior-report.md). Số liệu ngày 2026-10-25.

## 1. Selector đã xác nhận

| Mục đích | Selector | Phạm vi | Ghi chú |
|---|---|---|---|
| Form composer | `form[data-chatgpt-composer]` | Toàn trang | Có thể có 2 bản (home/thread) |
| Vùng nhập | `form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]` | Trong form | Không phải textarea |
| Composer home | `form[data-chatgpt-composer][data-composer-placement="home"] div.ProseMirror[contenteditable="true"]` | Home | Chỉ render ở home |
| Composer thread | `form[data-chatgpt-composer][data-composer-placement="thread"] div.ProseMirror[contenteditable="true"]` | Thread | Ẩn khi ở home |
| Gửi | `form[data-chatgpt-composer] button[aria-label="Send"]` | Trong form | Tránh selector toàn trang |
| Stop | `button[aria-label="Stop"]` | Toàn trang | Chỉ khi stream |
| New chat | `button[aria-label="New chat"]` | Sidebar/header | Luôn có trong phiên |
| Assistant | `h4[data-conversation-role="assistant"]` | Toàn trang | Bản ẩn vẫn tồn tại |
| Đăng nhập | `button[aria-label="Open profile menu"]` | Header | Presence-only |
| Nút cũ | `#prompt-textarea` | — | **Không còn tồn tại** |

## 2. Vì sao phải lọc render

Sau "New chat", DOM vẫn giữ heading assistant cũ trong workspace ẩn. Ví dụ điển hình:

```text
querySelectorAll('h4[data-conversation-role="assistant"]').length  → 3
số match có rect > 0 và visibility != hidden                         → 0
```

Nếu count/click dùng số thô:

- `count` trả 3 thay vì 0 → `wait_count > 3` sẽ chờ sai.
- `click` có thể chọn bản ẩn → không có hiệu ứng.

Primitive hiện tại đã lọc:

```js
function rendered(el) {
  const r = el.getBoundingClientRect();
  const s = getComputedStyle(el);
  return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
}
```

Filter này **không** kiểm tra `opacity:0`, off-screen, `pointer-events:none` hay overlay.

## 3. Lệnh kiểm tra nhanh

```bash
uv run aio-reverse web evaluate chatgpt "document.title"
uv run aio-reverse web evaluate chatgpt "document.readyState"
uv run aio-reverse web evaluate chatgpt "document.querySelectorAll('form[data-chatgpt-composer]').length"
```

So sánh raw/rendered cho composer:

```js
(() => {
  const selector = 'form[data-chatgpt-composer] div.ProseMirror[contenteditable="true"]';
  const all = Array.from(document.querySelectorAll(selector));
  const rendered = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
  };
  return {
    total: all.length,
    rendered: all.filter(rendered).length,
    placements: all.map(el => {
      const form = el.closest('form');
      return form ? form.getAttribute('data-composer-placement') : null;
    })
  };
})()
```

Kiểm tra assistant:

```js
(() => {
  const all = Array.from(document.querySelectorAll('h4[data-conversation-role="assistant"]'));
  const rendered = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
  };
  return {total: all.length, rendered: all.filter(rendered).length};
})()
```

Kiểm tra điểm click Send có bị che:

```js
(() => {
  const el = document.querySelector('form[data-chatgpt-composer] button[aria-label="Send"]');
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'center'});
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  const hit = document.elementFromPoint(x, y);
  return {x, y, hitTag: hit ? hit.tagName : null, hitIsSelf: hit === el || el.contains(hit)};
})()
```

## 4. State matrix

| Landmark | Home idle | Thread idle | Streaming | Signed out |
|---|---|---|---|---|
| Home composer | Render | Ẩn | Ẩn/Render | Không có |
| Thread composer | Ẩn | Render | Render | Không có |
| Send | Render | Render | Ẩn/đổi | Không có |
| Stop | Không có | Không có | Render | Không có |
| Assistant (render) | 0 | N | N hoặc N+1 | Không có |
| Profile menu | Render | Render | Render | Không có |

## 5. Pitfall

| Pitfall | Dấu hiệu | Cách xử lý |
|---|---|---|
| Route cache ẩn | Raw > rendered | Selector container + render filter |
| Home/thread cùng mount | 2 composer | Chọn theo `data-composer-placement` |
| Aria-label đổi do localize | `Send`/`Stop` không thấy | Kiểm tra inventory aria-label |
| ProseMirror lồng nhau | Click vào wrapper không focus | Click đúng `div.ProseMirror[contenteditable="true"]` |
| Overlay | `hitIsSelf=false` | Chờ overlay biến mất; ghi gap |
| Cold start | Composer chưa render | Chờ `ready_expression`; reload có kiểm soát |

## 6. Ghi chú

- `login_expression` chỉ kiểm tra presence của profile menu; không kiểm tra render.
- `ready_expression` kiểm tra composer render; đây là điều kiện cần trước mọi action.
- Không dùng `#prompt-textarea` trong target/script mới.
