# Telegram: /account và /usage

Hai lệnh **chỉ đọc**, chỉ áp dụng cho private chat đã được RE Dragon Telegram allowlist cho phép. Không thay đổi project, checkpoint, quota, token hoặc tài khoản.

| Lệnh | Dữ liệu | Điều kiện |
|---|---|---|
| `/account` | Danh tính phiên Watchdog nếu ID trùng; nếu khác, hiện danh tính CLI tương tác **có nhãn chưa xác minh Watchdog** | AGY statusLine hook đã gửi dữ liệu mới trong 15 phút |
| `/usage` | Phần trăm quota còn lại theo nhóm và thời điểm reset | Ưu tiên statusLine đúng phiên; nếu agent không chạy, đọc `agy -p /usage --output-format json` trên CLI hỗ trợ |
| `/help` | Danh sách lệnh hiện có | Bot đã tải phiên bản mới |

## Đồng bộ và kích hoạt tại WSL2

```bash
cd /home/khanh/returnsaiyan-re
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_agy_telemetry.py' -v
python3 -m re_harness.agy_telemetry install
./dragon telegram stop
./dragon telegram start
./dragon telegram status
```

`install` chỉ thêm `statusLine` nếu chưa có. Nếu đã có statusLine, báo lỗi và **không ghi đè** cấu hình; cần tích hợp thủ công vào hook hiện tại. Có bản sao `settings.json.before-re-dragon` trước lần thay đổi đầu tiên.

**Khi /account = UNKNOWN nhưng /usage có số liệu:** `/usage` có thể dùng headless CLI, còn `/account` cần statusLine từ TUI. Thực hiện `install` (nếu chưa có), mở `agy` tương tác trên cùng WSL user để statusLine phát dữ liệu, rồi kiểm tra `/account`. Nếu session ID khác, bot hiển thị tài khoản CLI cục bộ với nhãn **không xác minh được tài khoản phiên Watchdog**. Đừng `/resume` hay xóa checkpoint chỉ để kiểm tra tài khoản. Nếu cấu hình đã có statusLine, không chạy cài đè; cần tích hợp vào hook hiện tại.

AGY CLI cung cấp thông tin `email`, `plan_tier`, `quota`, `conversation_id` qua statusLine JSON. Hook lưu **email đã che**, không lưu token/khóa truy cập, vào file cục bộ `.re_harness/agy-telemetry.json` (mode 600). Đây là số liệu quan sát gần nhất, không phải phép xác thực đăng nhập từ xa.

CLI đang chạy có thể chưa tự nhận thay đổi `settings.json` cho đến phiên CLI tiếp theo. Không tự `/resume` hoặc đổi project chỉ để tạo telemetry.

**Cảnh báo:** không nhầm `/usage` của bot với số `Quota hits` trong `/status`. Quota hits là số sự kiện Watchdog phát hiện, không phải phần trăm quota Antigravity.

Nguồn: https://antigravity.google/docs/cli/statusline/ và https://antigravity.google/docs/cli/reference/
