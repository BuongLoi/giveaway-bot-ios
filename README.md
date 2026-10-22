# 🎁 Giveaway Hunter Bot (Windows + iOS + macOS + Game)

Hệ thống tự động **thu thập phần mềm bản quyền Windows/macOS, ứng dụng & game iOS đang miễn phí tạm thời (Apps Gone Free / Promo Code)** từ hơn 25 nguồn uy tín (RSS, Reddit API, Telegram Channels), tự động bóc tách License Key, phân loại nền tảng, lọc trùng SQLite và gửi thông báo về Telegram — đi kèm **Web App chuẩn PWA cho iPhone** và **GitHub Actions tự động đóng gói file `.ipa` (Unsigned)** cho ESign / TrollStore.

---

## ✨ Tính năng nổi bật

1. **Đa nền tảng (Windows + iOS + macOS + Game)**:
   - **🍎 Chuyên iOS / iPadOS / macOS**: `AppAdvice` (Apps Gone Free), `TouchArcade`, `iDownloadBlog`, `9to5Toys`, `r/AppHookup`, `r/iosgaming`.
   - **🪟 Chuyên Phần mềm Bản quyền PC/Mac**: `SharewareOnSale`, `GiveawayOfTheDay`, `TickCoupon`, `WinningPC`, `Comss.ru`, `NSANE Forums`, `FreeAppsForMe`, `GeckoAndFly`, `gHacks`, `BetaNews`, `Softpedia`.
   - **🎮 Game Miễn phí**: `Steam`, `r/FreeGameFindings`, `r/eFreebies`, `r/giveaways`, `r/PromoCode`.
2. **Trích xuất chính xác cao (`bot/extractor.py`)**:
   - Quét cả trong văn bản bài viết lẫn bên trong thẻ `<code>`, `<pre>`, `<kbd>`.
   - Tự động loại bỏ bài báo tin tức thông thường không phải giveaway (`is_relevant_giveaway`).
   - Nhận diện mẫu giảm giá đặc thù của App Store (`[$4.99 -> Free]`, `100% Off`, `Apps Gone Free`) và tính điểm tin cậy đa tầng (`0–100`).
   - Tự động gắn nhãn nền tảng (`🍎 iOS`, `🪟 Windows`, `🍏 macOS`, `🎮 Game`).
3. **Giao diện Web App chuẩn PWA & iOS Native Wrapper**:
   - Lọc nhanh theo từng hệ điều hành: **Tất cả**, **🍎 iOS / iPadOS**, **🪟 Windows**, **🍏 macOS**, **🎮 Game Free**, **🔑 Có Key**.
   - Hiển thị trực tiếp **License Key** kèm nút **📋 Chép Key 1 chạm** (có phản hồi rung Haptic trên iPhone).
   - Hỗ trợ cài trực tiếp lên màn hình chính iPhone qua Safari (**Add to Home Screen**) hoặc đóng gói thành file **`GiveawayHunter.ipa`** qua GitHub Actions.

---

## 🚀 Hướng dẫn Cài đặt Backend (VPS / Local)

1. Tạo môi trường ảo và cài đặt thư viện:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. Cấu hình biến môi trường:
   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

3. Chạy thử quét 1 lần (Dry-run):
   ```bash
   python main.py --once --dry-run
   ```

4. Khởi chạy Web App / Admin UI (Mặc định cổng `5000`):
   ```bash
   python web_admin.py
   ```

---

## 📱 Hướng dẫn Cài đặt lên iPhone (2 Cách)

### Cách 1: Cài nhanh qua PWA (Không cần ký chứng chỉ)
1. Mở **Safari** trên iPhone, truy cập địa chỉ Web của bạn (ví dụ `https://giveaway.buongloi.live/giveaways` hoặc `http://<IP_VPS>:5000/giveaways`).
2. Bấm nút **Chia sẻ (Share)** ở thanh dưới cùng ➔ Chọn **Thêm vào MH chính (Add to Home Screen)**.
3. Mở biểu tượng **GiveawayBot** trên màn hình chính để dùng toàn màn hình với thanh TabBar dưới đáy chuẩn iOS.

### Cách 2: Build file `.ipa` qua GitHub Actions (Cài bằng ESign / TrollStore)
Dự án đã tích hợp sẵn `.github/workflows/build-ios.yml` và `project.yml` (Xcode 16 + XcodeGen):
1. Đẩy thư mục dự án lên GitHub repository của bạn (nhánh `main` hoặc `master`).
2. Vào tab **Actions** trên GitHub ➔ Chọn workflow **`Build iOS (.ipa)`** ➔ Tải file **`GiveawayHunter-ipa.zip`** trong mục **Artifacts**.
3. Giải nén lấy `GiveawayHunter.ipa`, ký và cài bằng **ESign** hoặc **TrollStore**.
4. Khi mở app lần đầu, bấm biểu tượng **⚙️ Máy chủ** ở góc phải trên để nhập địa chỉ IP VPS hoặc tên miền Cloudflare Tunnel của bạn (không cần build lại `.ipa` khi đổi tên miền).

---

## 🧪 Kiểm thử (Unit Tests)
```bash
pytest tests/
```
