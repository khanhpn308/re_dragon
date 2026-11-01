# Windows Game Worker Adapter — ReturnSaiyan / DragonBall test build

| Index | Nội dung | Trạng thái |
|---|---|---|
| W01 | Game mục tiêu: `DragonBall.exe`, bản Win64 người dùng cung cấp | USER_PROVIDED |
| W02 | Điều khiển: Windows PowerShell 5.1 + Win32 API trong desktop session đang mở game | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| W03 | Bridge WSL2: `python3 -m re_harness.windows_worker_dispatch <action>` → `wslpath` → `powershell.exe` | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| W04 | Orchestrator MCP: `harness_windows_survey`, chỉ hoạt động khi project ACTIVE và agent sở hữu lease RUNNING của task | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| W05 | Lệnh: `probe`, `fingerprint`, `capture`, `click` (tọa độ client, yêu cầu `-EnableInput` nội bộ) | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| W06 | Bằng chứng: `events.jsonl`, PNG trước/sau; baseline bổ sung cho click; SHA-256; thông tin PID và binary | IMPLEMENTED_NOT_RUNTIME_VERIFIED |
| W07 | Thư mục mặc định: `%LOCALAPPDATA%\REDragon\WindowsSurvey`. Không commit ảnh game/token/PCAP vào Git | DESIGN |
| W08 | Trạng thái worker `OBSERVED` chỉ tương đương `AGENT_OBSERVED`; không có tự động `USER_APPROVED`, `SOURCE_VERIFIED` hoặc `ACCEPTED` | ENFORCED_IN_CODE |
| W09 | Bắt gói Windows/PCAP và giải mã IL2CPP qua worker chuyên biệt | NOT_YET_IMPLEMENTED |
| W10 | Khảo sát thành công ba chức năng gameplay thật trên máy Windows | NOT_YET_VERIFIED |
| W11 | Dự án Android pilot cũ: `READY_FOR_FINAL_REVIEW` 6/6 VERIFIED nhưng chưa chứng minh ba chức năng gameplay | DO_NOT_AUTO_ACCEPT |

## Triển khai trên máy người dùng

Trong WSL2 (giữ nguyên repository và Harness):

```bash
cd /home/khanh/returnsaiyan-re
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_windows_*.py' -v
python3 -m re_harness.windows_worker_dispatch probe
python3 -m re_harness.windows_worker_dispatch fingerprint
python3 -m re_harness.windows_worker_dispatch capture
```

Đảm bảo game `DragonBall.exe` **đang chạy và nhìn thấy trong desktop Windows**, desktop không khóa màn hình. Worker không tự khởi chạy executable và không cần LDPlayer. Dùng Python trong WSL2, không dùng Python Windows nếu đã có bridge WSL.

Chỉ sau khi xác nhận probe và capture thành công, mới thử một cú click có quan sát trước/sau. Tọa độ X/Y là tọa độ trong **client area** của cửa sổ game, không phải tọa độ màn hình Windows:

```bash
python3 -m re_harness.windows_worker_dispatch click --x 1160 --y 650
```

Ví dụ tọa độ **không phải vị trí đã xác minh** trên UI của người dùng; chọn theo ảnh screenshot thực tế. Không click các chức năng nạp tiền/xóa dữ liệu nếu không có mục đích thử nghiệm rõ ràng.

## Sử dụng qua Harness Orchestrator (không gửi prompt thẳng cho worker)

Sau khi project được **REOPEN** bằng `harness_auto_final_review(... decision=REOPEN ...)` có lý do và bằng chứng, Orchestrator thêm task khảo sát Windows đúng scope đã duyệt. Tại mỗi task:

1. Agent executor gọi `harness_auto_tick` để nhận task lease và `claim_token`.
2. Agent gọi MCP tool `harness_windows_survey` với project ID, task key, agent ID, claim token, action và (nếu click) X/Y.
3. Windows process adapter ghi PNG/JSONL, trả `OBSERVED` hoặc `BLOCKED`. Harness lưu sự kiện; **không tự đánh dấu task VERIFIED**.
4. Agent kiểm tra hình ảnh trước/sau và mô tả một chức năng gameplay **thực sự tương tác thành công**, nối với PCAP/REA chỉ khi có bằng chứng tương ứng. Lưu đặc tả nháp F01–F06/C/U, không tự USER_APPROVED.
5. Agent `harness_auto_submit`; reviewer độc lập kiểm tra **nội dung ảnh** và bằng chứng mạng/code; `harness_auto_review` phê duyệt hoặc từ chối.
6. Final review kiểm tra ít nhất ba **chức năng gameplay** thực tế và đủ bằng chứng trước khi quyết định `ACCEPT`. Launcher, Unity splash, Recent Apps, PCAP capture không được tính là ba gameplay functions.

`harness_windows_survey` hiện chỉ điều phối một hành động Win32 trong quá trình task đang RUNNING; **chưa tự sinh DAG, chưa triển khai tự khảo sát menu liên tục**. Agent orchestrator vẫn phải lập task và quyết định từng thao tác.

## Điều kiện thất bại (fail-closed)

- Không tìm thấy duy nhất một process/window `DragonBall` đang hiển thị → `BLOCKED`.
- Desktop không tương tác, Windows từ chối foreground → `BLOCKED`; không giả lập trạng thái thành công.
- Tọa độ click vượt client area → `BLOCKED`.
- Không có claim token hợp lệ hoặc project chưa ACTIVE → không gọi worker.
- PNG có hash khác nhau chỉ phản ánh thay đổi pixel, **không** tự chứng minh click thành công về mặt gameplay.
- WSL interop bị tắt hoặc không có PowerShell → `BLOCKED`.
- Theo dõi traffic và phân tích server chạy trên môi trường được phép, không sửa bản build gốc.

## Các giới hạn chưa giải quyết

Phải có một desktop session Windows đang mở. Máy khóa màn hình, cửa sổ bị che, game chạy exclusive fullscreen hoặc các chính sách chống điều khiển có thể khiến ảnh chụp/nhấp không đáng tin cậy. Cần kiểm tra trực tiếp trên máy người dùng; kiểm thử offline bằng mock không thay thế nghiệm thu thực tế.
