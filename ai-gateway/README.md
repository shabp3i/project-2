# ⚡ Quán Net AI - Gateway & Admin Billing System

Hệ thống quản lý truy cập và tính phí token AI theo mô hình "quán net", bao gồm **API Gateway tương thích OpenAI**, **Bảng điều khiển Quản trị (Admin Panel)** và **cơ chế trừ credit token thực tế**.

---

## 🎯 Mô hình Hoạt động

```
[OpenCode Client (Bạn bè)] 
     │ (API Key riêng: sk-user-xxxx)
     ▼
[AI Gateway (FastAPI + SQLite)]  <─────── [Admin Panel Web (Bạn quản lý)]
     │ (Kiểm tra số dư > 0)                  - Tạo key cho bạn bè
     │ (Trừ token theo usage thật)           - Nạp token khi nhận tiền
     ▼                                       - Đổi domain ngrok động
[Upstream (Google Colab)]
     │ (ngrok domain tĩnh)
[llama.cpp server]
```

1. **Nạp tiền ngoài đời:** Bạn bè trả tiền mặt / chuyển khoản cho bạn ➔ Bạn mở Admin Panel bấm **"Nạp Token"** cho tài khoản của họ (chọn các mốc nhanh: +100.000, +500.000, +1.000.000 token...).
2. **Sử dụng:** Bạn bè dùng OpenCode (hoặc bất kỳ ứng dụng nào tương thích OpenAI) trỏ về Gateway với API Key riêng của họ (`sk-user-xxxxxxxx`).
3. **Trừ token:** Gateway lấy số token thật từ trường `usage` (`prompt_tokens` + `completion_tokens`) mà llama.cpp server trả về và trừ thẳng vào `token_balance`.
4. **Hết token:** Khi `token_balance <= 0`, Gateway từ chối ngay với mã lỗi **HTTP 402 ("Hết token, vui lòng nạp thêm")**. Nếu request lớn làm âm nhẹ số dư, request đó vẫn hoàn thành nhưng request tiếp theo sẽ bị khoá ngay lập tức.
5. **Bảo mật & Riêng tư:** Gateway **KHÔNG** lưu nội dung tin nhắn chat của người dùng. Chỉ lưu thông số kỹ thuật (thời gian, model, số token, mã phản hồi).

---

## 🚀 Triển khai Gateway (VPS / Máy chủ cá nhân)

### Cách 1: Chạy bằng Docker Compose (Khuyên dùng)

1. **Chuẩn bị cấu hình:**
   ```bash
   cd ai-gateway
   cp .env.example .env
   ```
   Chỉnh sửa file `.env`:
   - `UPSTREAM_BASE_URL`: Domain tĩnh ngrok của Colab (ví dụ: `https://ten-domain-cua-ban.ngrok-free.app/v1`).
   - `ADMIN_PASSWORD`: Mật khẩu bạn dùng để đăng nhập trang Admin.

2. **Khởi động:**
   ```bash
   docker compose up -d --build
   ```

3. **Kiểm tra trạng thái:**
   ```bash
   docker compose ps
   docker compose logs -f
   ```

Database SQLite được lưu bền vững tại thư mục `./data/gateway.db` trên máy chủ của bạn, không bị mất khi restart container.

---

### Cách 2: Chạy trực tiếp bằng Python (Không dùng Docker)

1. **Cài đặt thư viện:**
   ```bash
   cd ai-gateway
   pip install -r requirements.txt
   ```

2. **Tạo file cấu hình:**
   ```bash
   cp .env.example .env   # Trên Linux/macOS
   # Hoặc trên Windows PowerShell:
   Copy-Item .env.example .env
   ```

3. **Khởi chạy máy chủ:**
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

---

## 🖥️ Hướng dẫn sử dụng Admin Panel

Truy cập: **`http://<IP-MAY-CHU-CUA-BAN>:8000/admin`**

### 1. Đăng nhập
- Nhập mật khẩu bạn đã đặt trong biến `ADMIN_PASSWORD` của file `.env`.

### 2. Tạo hội viên mới
- Bấm nút **"+ Tạo User Mới"** ➔ Nhập tên hội viên (ví dụ: `Nam_Dev`, `Hoang_AI`).
- Hệ thống tự sinh một API Key riêng biệt có định dạng: `sk-user-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
- Bấm nút **"📋 Copy Key"** và gửi cho bạn bè để họ dán vào `opencode.json`.
- Hội viên mới mặc định có `token_balance = 0`.

### 3. Nạp Token (Sau khi nhận tiền ngoài đời)
- Tại dòng của hội viên đó, bấm nút **"+ Nạp Token"**.
- Chọn mốc nhanh: **+100.000**, **+500.000**, **+1.000.000**, **+2.000.000 token** hoặc gõ số token bất kỳ.
- Bấm **"Xác Nhận Nạp Token"** ➔ Số dư được cộng ngay lập tức vào tài khoản.

### 4. Tạm khoá / Mở lại tài khoản
- Bấm nút **"Khoá"** nếu muốn tạm ngừng quyền truy cập của người dùng đó (trả lỗi HTTP 403 Forbidden). Bấm **"Mở lại"** để kích hoạt trở lại.

### 5. Đổi Upstream URL (Domain Ngrok Colab) không cần restart
- Vào tab **"⚙️ Cấu Hình Upstream"**.
- Điền domain tĩnh ngrok mới hoặc backend mới.
- Bấm **"⚡ Kiểm Tra Kết Nối Colab"** để ping thử xem Colab có đang bật hay không.
- Bấm **"Lưu Cấu Hình"** ➔ Áp dụng tức thì cho toàn bộ request kế tiếp mà không cần khởi động lại máy chủ Gateway!

### 6. Xem nhật ký sử dụng
- Vào tab **"📜 Nhật Ký Request"** để theo dõi lượng token tiêu thụ theo thời gian thực của từng hội viên.

---

## ⚙️ Biến môi trường (.env)

| Biến | Mặc định | Mô tả |
| :--- | :--- | :--- |
| `UPSTREAM_BASE_URL` | `https://.../v1` | URL ngrok trỏ tới llama.cpp server trên Colab |
| `UPSTREAM_API_KEY` | *(trống)* | API key của upstream nếu llama.cpp có cấu hình `--api-key` |
| `ADMIN_PASSWORD` | `admin123456` | Mật khẩu truy cập trang `/admin` (Cần đổi) |
| `SECRET_KEY` | *(ngẫu nhiên)* | Khóa ký phiên đăng nhập của Admin |
| `DB_PATH` | `data/gateway.db` | Đường dẫn file cơ sở dữ liệu SQLite |
| `RATE_LIMIT_PER_MINUTE` | `60` | Giới hạn số request/phút tối đa cho mỗi user key |
| `CONNECT_TIMEOUT` | `10.0` | Thời gian chờ kết nối upstream tối đa (giây) |
| `READ_TIMEOUT` | `300.0` | Thời gian chờ phản hồi tạo token từ LLM (giây) |
