# Telegram: /account và /usage

Hai lệnh **chỉ đọc**, chỉ áp dụng cho private chat đã được RE Dragon Telegram allowlist cho phép. Không thay đổi project, checkpoint, quota, token hoặc tài khoản.

| Lệnh | Dữ liệu | Điều kiện |
|---|---|---|
| `/account` | Danh tính phiên Watchdog nếu ID trùng; nếu khác, hiện danh tính CLI tương tác **có nhãn chưa xác minh Watchdog** | AGY statusLine hook đã gửi dữ liệu mới trong 15 phút |
| `/usage` | Phần trăm quota còn lại theo nhóm và thời điểm reset | Ưu tiên statusLine đúng phiên; nếu agent không chạy, đọc `agy -p /usage --output-format json` trên CLI hỗ trợ |
| `/audit` | Tình trạng nghiệm thu project, reviewer metadata và tham chiếu bằng chứng (chỉ đọc, không tự chấp nhận) | Harness SQLite và project pin đọc được |
| `/help` | Danh sách lệnh hiện có | Bot đã tải phiên bản mới |

## Đồng bộ và kích hoạt tại WSL2

```bash
cd /home/khanh/returnsaiyan-re
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_agy_telemetry.py' -v
python3 -m re_harness.agy_telemetry install --chain-existing
./dragon telegram stop
./dragon telegram start
./dragon telegram status
```

`install --chain-existing` chỉ hoạt động khi đã có statusLine kiểu command, đang bật. Nó tạo bản sao lưu cấu hình, lưu lệnh gốc trong file riêng chmod 600, rồi nối bộ thu thập telemetry và **giữ nguyên stdout, padding, stack_with_default của lệnh gốc**. Nếu statusLine không có, hãy dùng `install` không có `--chain-existing`. Nếu statusLine đang tắt hoặc không hợp lệ, công cụ từ chối sửa. Không tự cài lặp lại.

**Khi /account = UNKNOWN nhưng /usage có số liệu:** `/usage` có thể dùng headless CLI, còn `/account` cần statusLine từ TUI. Thực hiện `install` hoặc `install --chain-existing` tùy cấu hình, mở `agy` tương tác trên cùng WSL user để statusLine phát dữ liệu, rồi kiểm tra `/account`. Nếu session ID khác, bot hiển thị tài khoản CLI cục bộ với nhãn **không xác minh được tài khoản phiên Watchdog**. Đừng `/resume` hay xóa checkpoint chỉ để kiểm tra tài khoản. Nếu đã có statusLine, dùng tùy chọn nối có lưu bản sao `--chain-existing`; không xóa cấu hình gốc.

AGY CLI cung cấp thông tin `email`, `plan_tier`, `quota`, `conversation_id` qua statusLine JSON. Hook lưu **email đã che**, không lưu token/khóa truy cập, vào file cục bộ `.re_harness/agy-telemetry.json` (mode 600). Đây là số liệu quan sát gần nhất, không phải phép xác thực đăng nhập từ xa.

CLI đang chạy có thể chưa tự nhận thay đổi `settings.json` cho đến phiên CLI tiếp theo. Không tự `/resume` hoặc đổi project chỉ để tạo telemetry.

**Cảnh báo:** không nhầm `/usage` của bot với số `Quota hits` trong `/status`. Quota hits là số sự kiện Watchdog phát hiện, không phải phần trăm quota Antigravity.

Nguồn: https://antigravity.google/docs/cli/statusline/ và https://antigravity.google/docs/cli/reference/

## Kiểm tra final review / MISSING_MARKER

Nếu toàn bộ task đã `VERIFIED` nhưng project vẫn `ACTIVE`, chạy `/audit`. Kết quả **Final ACCEPTED: NO** yêu cầu kiểm chứng bằng chứng thực tế và gọi quy trình `harness_auto_final_review` có thẩm quyền. Bản vá Watchdog sẽ dừng với lý do `final project review required` thay vì lặp lỗi `MISSING_MARKER` trong trường hợp này. Lệnh `/audit` chỉ xem metadata, không xác thực danh tính reviewer thực tế hoặc chứng minh tính đúng đắn của ảnh/PCAP.
