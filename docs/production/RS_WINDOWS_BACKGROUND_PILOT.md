# Windows Background Interaction Pilot — DragonBall.exe

**Trạng thái:** IMPLEMENTED_NOT_RUNTIME_VERIFIED. Đây là phép thử tương thích Unity, **không phải bản nâng cấp đã nghiệm thu**.

| Bước | Điều kiện / kết quả | Phạm vi |
|---|---|---|
| B01 | Giữ game đang mở ở Windows desktop, không thu nhỏ và chưa khóa màn hình | Game Windows |
| B02 | Paused Harness qua Telegram `/pause` để không tiếp tục các click foreground đang lỗi | Không xóa checkpoint |
| B03 | Kiểm tra working tree trước khi `git pull --ff-only`; không reset/stash file chưa commit | Bảo toàn worktree |
| B04 | Chụp cửa sổ game bằng `PrintWindow` khi Chrome/Telegram chiếm foreground | Ứng viên, Unity có thể trả khung hình đen/stale |
| B05 | Chỉ khi B04 cho ảnh đúng và có thay đổi thật, thử *một* click nền được cho phép bằng `PostMessage` | CLI opt-in, chưa được MCP tự động click |
| B06 | Đối chiếu ảnh trước/sau với quan sát giao diện thật; `OBSERVED` chỉ là kết quả Win32, **không phải gameplay VERIFIED** | Reviewer |
| B07 | Nếu Unity bỏ qua `PostMessage` hoặc `PrintWindow` không có ảnh thật, chuyển sang VM desktop riêng | Không cố ép focus hoặc tiếp tục click mù |

## 1. Cài đặt và kiểm tra (WSL Ubuntu)

```bash
cd /home/khanh/returnsaiyan-re || exit 1
git status --short
# Chỉ pull nếu các thay đổi local đã được bạn kiểm tra/xử lý an toàn:
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_windows*.py' -v
```

Bộ nền là `scripts/windows_background_worker.ps1` với Python bridge `re_harness/windows_background_dispatch.py`. Chế độ mới **không dùng** SetForegroundWindow, SetCursorPos, mouse_event hoặc CopyFromScreen.

## 2. Kiểm thử mà không chiếm chuột

Để `DragonBall.exe` hiển thị bình thường, không thu nhỏ; mở Chrome hoặc Telegram lên trước game (không nhất thiết che toàn bộ game), rồi chạy:

```bash
python3 -m re_harness.windows_background_dispatch probe
python3 -m re_harness.windows_background_dispatch capture
```

Dữ liệu ghi tại: `%LOCALAPPDATA%\REDragon\WindowsBackgroundSurvey\`.

Trạng thái cần nhận được: `status=OBSERVED`, `game_was_foreground=false`, `no_global_mouse_input=true`, có `before.path` và SHA-256. Mở ảnh PNG để xác nhận đó **thật sự là hình game**, không phải ảnh đen, khung hình cũ hoặc màn hình của Chrome. Chỉ test `PrintWindow` thành công trên máy thật mới xem xét bước 3.

Nếu có `PRINTWINDOW_UNUSABLE_FRAME`, `PRINTWINDOW_FAILED`, `GAME_MINIMIZED` hoặc `INVALID_CLIENT_BOUNDS`: dừng pilot nền và cân nhắc VM; không tự retry.

## 3. Thử tương tác nền — tùy chọn, từng thao tác, chưa tích hợp tự động

Sau khi đã kiểm chứng ảnh chụp nền, chọn tọa độ client X/Y từ **ảnh thực tế**, kiểm tra đối tượng click không phải vật phẩm tiêu thụ, giao dịch, tài khoản hay hành động không thể đảo ngược:

```bash
python3 -m re_harness.windows_background_dispatch click --x X --y Y --enable-input
```

Thay `X`, `Y` bằng số nguyên tọa độ client thật. `PostMessage` có thể được Windows chấp nhận nhưng Unity vẫn không xử lý. `visual_changed=true` chỉ là thay đổi pixel, không chứng minh nút đã được game xử lý. So sánh ảnh trước/sau, game state và kiểm thử độc lập.

Nếu thao tác lỗi sau khi có `input_dispatched=true` **không click lại ngay**; xác minh trạng thái game trước để tránh thao tác trùng.

## 4. Tích hợp Harness

MCP `harness_windows_background` mới **chỉ** mở `probe` và `capture` cho task ACTIVE có claim token. Không tự thay thế `harness_windows_survey` foreground. Chế độ click nền qua Harness vẫn khóa cho đến khi pilot chứng minh được Unity nhận tương tác nền và reviewer xác nhận bằng chứng.

Các task đã `DISPUTED`, `BLOCKED`, `RUNNING` không tự được sửa; không đánh dấu VERIFIED hoặc ACCEPTED. Không tự tiếp tục Watchdog chỉ vì CI PASS.

## 5. Giới hạn

`PrintWindow` thường không ổn định với nội dung tăng tốc GPU/Unity; `PostMessage` không bảo đảm kích hoạt Unity Input System. Dùng VM có desktop riêng nếu phải làm việc song song ổn định và thử nghiệm nền không đạt.
