# ⚡ HƯỚNG DẪN TOÀN DIỆN HỆ THỐNG QUẢN LÝ TRUY CẬP AI THEO KIỂU "QUÁN NET"

> Hệ thống hoàn chỉnh gồm 3 thành phần:
> 1. **Gateway Backend (FastAPI + SQLite)**: Trung gian tương thích OpenAI, trừ token theo `usage` thật, chặn khi hết token (HTTP 402), bảo mật riêng tư.
> 2. **Admin Panel (Giao diện Web)**: Quản lý hội viên, nạp token sau khi nhận tiền ngoài đời, xem log, đổi domain ngrok Colab động không cần restart.
> 3. **OpenCode Client**: Bản build từ mã nguồn gốc kèm sẵn cấu hình mẫu `opencode.json` để bạn phân phối cho bạn bè dễ dàng.

---

## 📐 Kiến Trúc Hoạt Động

```
┌────────────────────────────────────────────────────────┐
│  BẠN BÈ (CLIENT)                                      │
│  Sử dụng OpenCode Client đã đóng gói                   │
│  File cấu hình opencode.json có API key riêng         │
└──────────────────────────┬─────────────────────────────┘
                           │ Gửi request (Authorization: Bearer sk-user-xxxx)
                           ▼
┌────────────────────────────────────────────────────────┐
│  AI GATEWAY (FASTAPI + SQLITE)                         │
│  - Kiểm tra số dư token_balance > 0 (Hết -> HTTP 402) │
│  - Kiểm tra rate limit chống spam                      │
│  - Forward request lên Colab                           │
│  - Đọc usage thật (prompt + completion) từ response    │
│  - Trừ đúng số token vào tài khoản người dùng          │
│  - Ghi log kỹ thuật (KHÔNG lưu nội dung chat)          │
└──────────────┬───────────────────────────▲─────────────┘
               │                           │
               │ Forward                   │ Quản lý & Nạp token
               ▼                           │
┌──────────────────────────────┐ ┌────────┴──────────────┐
│ UPSTREAM (GOOGLE COLAB)      │ │ ADMIN PANEL (WEB UI)  │
│ - llama.cpp server           │ │ - Đăng nhập mật khẩu  │
│ - Lộ ra qua ngrok domain tĩnh│ │ - Tạo user, sinh key  │
│   (https://...ngrok-free.app)│ │ - Nạp token (+100k...)│
└──────────────────────────────┘ │ - Đổi ngrok động      │
                                 └───────────────────────┘
```

---

## 🛠️ PHẦN 1: TRIỂN KHAI GATEWAY VÀ ADMIN PANEL

Gateway nên được triển khai trên một VPS nhỏ (1 vCPU, 1GB RAM giá rẻ từ Hetzner, Vultr, OVH, hoặc VPS Việt Nam) hoặc máy tính có IP tĩnh / Cloudflare Tunnel.

Thư mục mã nguồn gateway nằm tại: `ai-gateway/`

### Cách 1: Triển khai bằng Docker Compose (Khuyên dùng)

1. **Vào thư mục `ai-gateway`:**
   ```bash
   cd ai-gateway
   ```

2. **Tạo file môi trường `.env` từ file mẫu:**
   ```bash
   cp .env.example .env
   ```

3. **Cấu hình các tham số trong `.env`:**
   ```ini
   # Domain tĩnh ngrok từ Colab của bạn (kèm /v1 ở cuối)
   UPSTREAM_BASE_URL=https://ten-domain-cua-toi.ngrok-free.app/v1
   UPSTREAM_API_KEY=

   # Mật khẩu đăng nhập Admin Panel (đổi thành mật khẩu an toàn của bạn)
   ADMIN_PASSWORD=mat_khau_admin_cua_ban_123

   # Khóa bảo mật ký token admin
   SECRET_KEY=mot_chuoi_ngau_nhien_dai_de_bao_mat_he_thong

   # Rate limit tối đa trên 1 key (chống spam)
   RATE_LIMIT_PER_MINUTE=60
   ```

4. **Khởi động container:**
   ```bash
   docker compose up -d --build
   ```

5. **Kiểm tra trạng thái:**
   ```bash
   docker compose ps
   docker compose logs -f
   ```
   > Toàn bộ dữ liệu hội viên và token được lưu tại `./data/gateway.db` (SQLite WAL mode), đảm bảo an toàn kể cả khi restart hoặc cập nhật Docker container.

---

### Cách 2: Triển khai trực tiếp bằng Python (Không dùng Docker)

1. Yêu cầu: Python 3.10+
2. Cài đặt thư viện:
   ```bash
   cd ai-gateway
   pip install -r requirements.txt
   ```
3. Copy `.env.example` thành `.env` và chỉnh sửa thông số.
4. Chạy server:
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

---

## 🎮 PHẦN 2: HƯỚNG DẪN SỬ DỤNG ADMIN PANEL

Mở trình duyệt truy cập: **`http://<IP_MAY_CHU_HOAC_DOMAIN>:8000/admin`**

### 1. Đăng nhập
- Nhập mật khẩu bạn đã thiết lập trong biến `ADMIN_PASSWORD` của file `.env`.
- Phiên đăng nhập được bảo mật bằng Signed Token và cookie trong 7 ngày.

### 2. Tạo hội viên mới cho bạn bè
- Bấm nút **"+ Tạo User Mới"**.
- Điền tên bạn bè (ví dụ: `Huy_Dev`, `Nam_AI`).
- Hệ thống tự sinh một API key riêng có định dạng: `sk-user-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
- Bấm **"📋 Copy Key"** để lưu lại gửi cho bạn bè.
- Hội viên mới mặc định có **0 token**.

### 3. Nạp Token (Quy trình "Nhận tiền ngoài đời ➔ Cộng token")
1. Bạn bè chuyển khoản hoặc đưa tiền mặt cho bạn.
2. Bạn mở Admin Panel, tại dòng của hội viên đó, bấm nút **"+ Nạp Token"**.
3. Chọn các mốc nhanh:
   - `+ 100,000 token`
   - `+ 500,000 token`
   - `+ 1,000,000 token`
   - `+ 2,000,000 token`
   - Hoặc gõ số token tuỳ ý vào ô nhập.
4. Bấm **"Xác Nhận Nạp Token"** ➔ Số dư được cộng ngay lập tức vào tài khoản.

### 4. Tạm khoá / Mở lại tài khoản
- Nút **"Khoá"**: Tạm đình chỉ quyền gọi API của tài khoản (trả về HTTP 403 Forbidden).
- Nút **"Mở lại"**: Kích hoạt trở lại cho người dùng khi cần.

### 5. Đổi Upstream URL (Ngrok Colab) Động Không Cần Restart
- Nếu bạn khởi động lại Colab với domain ngrok mới hoặc đổi sang backend khác (vLLM, Ollama, server GPU khác):
  1. Vào tab **"⚙️ Cấu Hình Upstream"**.
  2. Điền URL mới vào ô `Upstream Base URL`.
  3. Bấm nút **"⚡ Kiểm Tra Kết Nối Colab"** để kiểm tra độ trễ (latency ms) và danh sách model sẵn sàng.
  4. Bấm **"Lưu Cấu Hình"** ➔ Áp dụng ngay tức thì cho mọi request mà **không cần khởi động lại Gateway**!

### 6. Xem Nhật Ký Sử Dụng (Request Logs)
- Vào tab **"📜 Nhật Ký Request"** để xem 100 request gần nhất:
  - Thời gian, Tên hội viên, Model sử dụng.
  - Số prompt tokens, completion tokens, tổng tokens đã trừ.
  - Mã trạng thái (HTTP 200, 402, 503...) và độ trễ phản hồi (ms).
  - **Quyền riêng tư:** Hệ thống tuyệt đối không lưu nội dung câu hỏi/tin nhắn chat của người dùng.

---

## 💻 PHẦN 3: BUILD VÀ ĐÓNG GÓI CLIENT OPENCODE

> **Ghi chú quan trọng:** Việc build lại từ mã nguồn gốc OpenCode (thay vì cài bản release có sẵn) chỉ nhằm mục đích bạn tự đóng gói kèm sẵn file cấu hình mẫu (`opencode.json`) trỏ về Gateway của bạn để phân phối cho bạn bè tiện dùng nhất, không thay đổi bất kỳ logic nội bộ nào của OpenCode.

### 1. Chuẩn bị môi trường build (Trên máy bạn)

OpenCode yêu cầu runtime **Bun** (phiên bản v1.2+):

- **Trên Windows (chạy PowerShell với quyền Admin hoặc User):**
  ```powershell
  powershell -c "irm bun.sh/install.ps1 | iex"
  ```
  *(Sau khi cài xong, khởi động lại PowerShell để nhận lệnh `bun`)*

- **Trên macOS / Linux:**
  ```bash
  curl -fsSL https://bun.sh/install | bash
  ```

- Kiểm tra cài đặt thành công:
  ```bash
  bun --version
  ```

---

### 2. Cài đặt Dependencies cho OpenCode

Tại thư mục gốc của repository OpenCode:
```bash
bun install
```

Lệnh này sẽ tự động tải các gói thư viện và áp dụng các bản patch cần thiết theo `bun.lock`.

---

### 3. Cấu hình file `opencode.json` mẫu

Tại thư mục gốc của project đã có sẵn file `opencode.json` với nội dung chuẩn:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "quan-net-ai": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Quán Net AI (Colab llama.cpp)",
      "options": {
        "baseURL": "http://IP_HOAC_DOMAIN_GATEWAY_CUA_BAN:8000/v1",
        "apiKey": "sk-user-THAY_BANG_KEY_ADMIN_CAP_CHO_BAN"
      },
      "models": {
        "default": {
          "name": "Colab AI Model"
        }
      }
    }
  },
  "model": "quan-net-ai/default"
}
```

**Lưu ý quan trọng cho người dùng:**
- Trường `baseURL`: Giữ nguyên địa chỉ Gateway của bạn (ví dụ: `https://gateway.example.com/v1` hoặc `http://123.45.67.89:8000/v1`).
- Trường `apiKey`: Mỗi người chỉ cần thay chuỗi `sk-user-THAY_BANG_KEY_ADMIN_CAP_CHO_BAN` bằng mã API Key riêng do bạn (Admin) cấp.

---

### 4. Chạy thử nghiệm trên máy phát triển

Để kiểm tra ngay OpenCode đang chạy tốt với cấu hình trên:
```bash
bun run dev
```
OpenCode sẽ khởi động giao diện dòng lệnh/TUI và kết nối tới Gateway của bạn.

---

### 5. Build file chạy độc lập (`.exe` trên Windows hoặc binary trên Linux/macOS)

Để đóng gói thành file thực thi độc lập:
```bash
bun run --cwd packages/cli build --single
```

File thực thi sau khi build sẽ nằm trong thư mục:
- **Windows:** `packages/cli/dist/cli-win32-x64/opencode.exe` (hoặc `packages/cli/dist/...`)
- **macOS / Linux:** `packages/cli/dist/cli-.../opencode`

---

### 6. Cách đóng gói và phân phối cho bạn bè ("Gói Quán Net AI")

Tạo một thư mục phân phối, ví dụ `QuanNetAI-OpenCode/`:
1. Chép file `opencode.exe` (vừa build) vào thư mục này.
2. Chép file `opencode.json` vào cùng thư mục với `opencode.exe`.
3. Nén thư mục thành file `QuanNetAI-OpenCode.zip` và gửi cho bạn bè.

**Hướng dẫn 1 bước cho bạn bè:**
> "Bạn tải file zip về, giải nén ra. Mở file `opencode.json` bằng Notepad, dán key `sk-user-...` mình đã gửi cho bạn vào ô `apiKey`. Sau đó mở terminal gõ `./opencode` hoặc nhấp đúp file chạy là xong!"

---

## 🧠 PHẦN 4: GỢI Ý CHẠY LLAMA.CPP SERVER TRÊN GOOGLE COLAB KÈM NGROK

Trên notebook Google Colab của bạn (chạy GPU T4 / A100 miễn phí hoặc Colab Pro):

### Bước 1: Cài đặt llama.cpp và ngrok
```python
# Tải binary llama.cpp mới nhất hỗ trợ CUDA
!git clone https://github.com/ggerganov/llama.cpp
!cd llama.cpp && cmake -B build -DGGML_CUDA=ON && cmake --build build --config Release -j4

# Cài ngrok
!pip install pyngrok
```

### Bước 2: Tải model GGUF (Ví dụ Qwen2.5-Coder hoặc Llama-3-8B)
```python
!huggingface-cli download Qwen/Qwen2.5-Coder-7B-Instruct-GGUF qwen2.5-coder-7b-instruct-q4_k_m.gguf --local-dir .
```

### Bước 3: Thiết lập domain tĩnh ngrok và khởi động server
```python
import os
from pyngrok import ngrok

# Thiết lập ngrok authtoken của bạn
!ngrok config add-authtoken YOUR_NGROK_AUTHTOKEN

# Chạy llama-server ở chế độ nền (port 8080)
!nohup ./llama.cpp/build/bin/llama-server \
    -m qwen2.5-coder-7b-instruct-q4_k_m.gguf \
    -c 4096 \
    --host 0.0.0.0 \
    --port 8080 \
    --n-gpu-layers 99 > server.log 2>&1 &

# Mở tunnel ngrok với DOMAIN TĨNH miễn phí của bạn
# (Lấy domain tĩnh miễn phí tại dashboard.ngrok.com/domains)
public_url = ngrok.connect(8080, domain="ten-domain-cua-toi.ngrok-free.app")
print("Upstream API URL:", f"{public_url}/v1")
```

Với cấu hình này:
- Mỗi khi bạn bật Colab, domain ngrok tĩnh `https://ten-domain-cua-toi.ngrok-free.app/v1` không bao giờ đổi.
- Gateway của bạn tự động kết nối và trừ token chính xác theo số liệu `usage` trả về.

---

## 🛡️ CƠ CHẾ BẢO VỆ VÀ XỬ LÝ SỰ CỐ CỦA GATEWAY

1. **Khi Colab đang tắt hoặc ngrok tunnel chưa bật:**
   - Gateway phản hồi ngay lập tức mã lỗi **HTTP 503 (Service Unavailable)** với thông báo rõ ràng bằng tiếng Việt: *"Không thể kết nối tới máy chủ AI (Google Colab / llama.cpp). Server có thể đang tắt hoặc ngrok tunnel chưa hoạt động."*
   - Không làm treo hoặc đơ client OpenCode.

2. **Khi hội viên hết token (`token_balance <= 0`):**
   - Gateway từ chối ngay lập tức tại bước kiểm tra đầu vào với mã lỗi **HTTP 402 (Payment Required)**: *"Tài khoản của bạn đã hết token. Vui lòng liên hệ Admin để nạp thêm."*
   - Không forward request vô ích lên Colab, tiết kiệm tài nguyên GPU.

3. **Khi số dư token còn ít nhưng request trả về dài:**
   - Gateway cho phép request đi qua bình thường để đảm bảo trải nghiệm mượt mà không bị ngắt giữa chừng.
   - Sau khi hoàn thành, số dư bị trừ thành âm nhẹ (ví dụ: -250 token).
   - Ngay ở request tiếp theo, hệ thống kiểm tra thấy balance <= 0 và khoá lại cho đến khi được Admin nạp thêm.

4. **Khi hội viên gửi quá nhiều request cùng lúc (Spam):**
   - Rate limit (mặc định 60 req/phút trên mỗi key) chặn spam và trả về mã lỗi **HTTP 429 (Too Many Requests)**.
