# 03 — Bản đồ bề mặt DOM (chỉ đọc)

Mục đích: biết chính xác trang có gì, phần tử nào đang thực sự được render, và trạng
thái nào làm selector đổi nghĩa — trước khi click hoặc gửi bất cứ thứ gì.

## 1. Nguyên tắc

1. **Presence ≠ visibility.** Node có trong DOM không có nghĩa đang hiển thị.
2. **Một selector có thể khớp nhiều route.** SPA thường giữ DOM của route cũ với
   `display:none`.
3. **Đếm thô và đếm render là hai số khác nhau.** Phải ghi cả hai.
4. **Không dùng class generated/hash** làm selector hành động.
5. **Không sửa DOM để làm test pass.** Nếu DOM không cho thao tác, đó là phát hiện.

## 2. Trình tự khám phá

### Bước 1 — Nhận diện trang và phiên

```bash
uv run aio-reverse web state <target>
```

Ghi lại: URL, title, `ready_state`, sự tồn tại của landmark đăng nhập. Nếu `state`
timeout, dừng ở đây và xử lý theo playbook; không click mù.

### Bước 1b — Skeleton-first (khuyên dùng trước inventory thủ công)

Chụp **hai trạng thái khác nhau** rồi diff bằng `wre-template` qua Python surface:

```bash
uv run aio-reverse web snapshot <target> --label home
# đạt trạng thái thứ hai (mở thread / gửi lượt) rồi:
uv run aio-reverse web snapshot <target> --label thread
uv run aio-reverse web skeleton --page <home.html> --page <thread.html> --xpath
```

- Skeleton giữ lại cấu trúc chung và đánh dấu `← [dynamic]` đúng vùng đổi theo dữ liệu;
  `slots` liệt kê node động kèm path. Inventory thủ công (bước 2) chỉ cần làm sâu
  trong các vùng đó — trên ChatGPT thật, 2 snapshot cho reduction 96.3%, 6 slot,
  vùng động nằm ở scroll container hội thoại và portal root.
- Điều kiện: hai snapshot phải ở hai trạng thái **thực sự khác**; trang giống nhau
  thì mọi node "stable", skeleton vô dụng. HTML snapshot chỉ nằm trong
  `data/output/` (gitignored); không dán nội dung HTML vào docs.

### Bước 2 — Liệt kê landmark

Chạy các biểu thức read-only sau bằng `web evaluate`. Mỗi lệnh là một expression.

**A. Tổng quan trang và các vùng nhập liệu:**

```js
(() => {
  const rendered = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
  };
  return {
    url: location.href,
    title: document.title,
    readyState: document.readyState,
    editables: Array.from(document.querySelectorAll('[contenteditable="true"], textarea, [role="textbox"]')).map(el => ({
      tag: el.tagName,
      id: el.id,
      cls: typeof el.className === 'string' ? el.className : '',
      form: el.closest('form') ? {
        placement: el.closest('form').getAttribute('data-composer-placement'),
        testid: el.closest('form').getAttribute('data-testid')
      } : null,
      rendered: rendered(el)
    })),
    forms: Array.from(document.querySelectorAll('form')).map(f => ({
      placement: f.getAttribute('data-composer-placement'),
      testid: f.getAttribute('data-testid'),
      rendered: rendered(f)
    }))
  };
})()
```

**B. Inventory `aria-label` (chỉ phần tử render, tối đa 100):**

```js
(() => {
  const rendered = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
  };
  return Array.from(document.querySelectorAll('[aria-label]'))
    .filter(rendered)
    .slice(0, 100)
    .map(el => ({tag: el.tagName, label: el.getAttribute('aria-label'), role: el.getAttribute('role')}));
})()
```

**C. Inventory `data-testid` / `data-*` ổn định:**

```js
(() => Array.from(document.querySelectorAll('[data-testid], [data-conversation-role], [data-composer-placement]'))
  .slice(0, 100)
  .map(el => ({
    tag: el.tagName,
    testid: el.getAttribute('data-testid'),
    role: el.getAttribute('data-conversation-role'),
    placement: el.getAttribute('data-composer-placement')
  })))()
```

**D. So sánh thô vs render cho một selector:**

```js
(() => {
  const selector = 'REPLACE_ME';
  const all = Array.from(document.querySelectorAll(selector));
  const rendered = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden';
  };
  const visible = all.filter(rendered);
  return {
    selector,
    total: all.length,
    rendered: visible.length,
    hidden: all.filter(el => !rendered(el)).slice(0, 5).map(el => ({
      tag: el.tagName,
      cls: typeof el.className === 'string' ? el.className : '',
      display: getComputedStyle(el).display,
      parent: el.parentElement ? el.parentElement.tagName : null
    }))
  };
})()
```

**E. Chuỗi ancestor của một node (tìm route/workspace):**

```js
(() => {
  const el = document.querySelector('REPLACE_ME');
  if (!el) return null;
  const chain = [];
  let node = el;
  while (node && node !== document.documentElement) {
    const s = getComputedStyle(node);
    chain.push({
      tag: node.tagName,
      id: node.id,
      cls: typeof node.className === 'string' ? node.className.slice(0, 120) : '',
      display: s.display,
      visibility: s.visibility
    });
    node = node.parentElement;
  }
  return chain;
})()
```

**F. Kiểm tra điểm click có bị che không:**

```js
(() => {
  const el = document.querySelector('REPLACE_ME');
  if (!el) return null;
  el.scrollIntoView({block: 'center', inline: 'center'});
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2;
  const y = r.top + r.height / 2;
  const hit = document.elementFromPoint(x, y);
  return {
    x, y,
    tag: el.tagName,
    hitTag: hit ? hit.tagName : null,
    hitIsSelf: hit === el || el.contains(hit)
  };
})()
```

`hitIsSelf=false` nghĩa là có overlay hoặc phần tử khác sẽ nhận click. Ghi lại; không
tự ý xóa overlay.

### Bước 3 — Lập state matrix

Với mỗi trạng thái, ghi selector nào render:

| Landmark | Home idle | Thread idle | Streaming | Error | Signed out |
|---|---|---|---|---|---|
| composer home | ? | ? | ? | ? | ? |
| composer thread | ? | ? | ? | ? | ? |
| nút Send | ? | ? | ? | ? | ? |
| nút Stop | ? | ? | ? | ? | ? |
| tin nhắn assistant | ? | ? | ? | ? | ? |
| menu tài khoản | ? | ? | ? | ? | ? |

Không chuyển state bằng cách gửi dữ liệu thật. Dùng thao tác UI tối thiểu, có thể lặp
lại, và chỉ khi mission cho phép.

### Bước 4 — Xếp hạng selector

| Hạng | Loại | Ví dụ | Ghi chú |
|---|---|---|---|
| 1 | `data-*` ổn định | `form[data-chatgpt-composer]` | Tốt nhất |
| 2 | `aria-label` + role | `button[aria-label="Send"]` | Có thể đổi khi localize |
| 3 | `id`/`name` ổn định | `#prompt-textarea` | Chỉ khi thật ổn định |
| 4 | Text hiển thị | `button:has-text("Send")` | Không dùng nếu đa ngôn ngữ |
| 5 | Cấu trúc CSS | `form > div > button` | Dễ gãy |
| 6 | Class hash | `.css-1x2y3z` | Cấm dùng |

Ưu tiên selector hẹp trong đúng container. Ví dụ:

```text
form[data-chatgpt-composer] button[aria-label="Send"]
```

tốt hơn `button[aria-label="Send"]` toàn trang, vì tránh nhiều composer/route.

### Bước 5 — Ghi bằng chứng

Mỗi selector chốt phải kèm:

```text
selector | raw count | rendered count | state | command | date
```

Nếu không có bảng này, chưa được chuyển sang thiết kế action chain.

## 3. Giới hạn của primitive hiện tại

Các primitive `click`, `wait_visible`, `wait_hidden`, `count`, `wait_count` dùng
`document.querySelectorAll`; `web evaluate` chỉ là công cụ chạy biểu thức. Do đó:

- **Không xuyên shadow DOM.** Node trong shadow root sẽ không được thấy.
- **Không xuyên iframe** (kể cả same-origin) từ context trang.
- **Không kiểm tra `opacity:0`, off-screen, `pointer-events:none`.** Filter chỉ kiểm tra
  kích thước và `visibility`.
- **Click không kiểm tra `elementFromPoint`.** Nếu overlay phủ lên, click có thể rơi vào
  overlay.

Nếu gặp các trường hợp trên: ghi "primitive gap", đề xuất bổ sung vào adapter, không
viết JavaScript tùy ý để vượt qua.

## 4. Mẫu ghi DOM map

```markdown
| Landmark | Selector | Raw | Rendered (home) | Rendered (thread) | Ghi chú |
|---|---|---|---|---|---|
| composer | `form[...] div.ProseMirror[...]` | 2 | 1 | 1 | Bản home ẩn khi ở thread |
| send | `form[...] button[aria-label="Send"]` | 2 | 1 | 1 | Nằm trong form |
| reply | `h4[data-conversation-role="assistant"]` | 3 | 0 | 3 | DOM cũ còn trong route cache |
```

## 5. Checklist cổng 2

- [ ] Đã ghi URL/title/readyState ở trạng thái đầu.
- [ ] Đã inventory form/editable/button/aria-label.
- [ ] Đã so sánh raw vs rendered cho mọi selector hành động.
- [ ] Đã lập state matrix cho ít nhất: idle, active/streaming, signed out.
- [ ] Đã kiểm tra hidden route cache / bản sao `display:none`.
- [ ] Đã kiểm tra điểm click có bị overlay che không.
- [ ] Đã ghi giới hạn shadow DOM/iframe nếu gặp.
- [ ] Mọi selector hành động nằm trong container hẹp, không phải toàn trang.
