# RS-PS-0001 — Đăng nhập

**Trạng thái phê duyệt:** `USER_APPROVED` (đã được người dùng chốt ngày 2026-10-28)  
**Sự hiện diện trong ứng dụng:** `USER_CONFIRMED`  
**Mức xác minh bằng APK/REA MCP:** `NOT_YET_VERIFIED`  
**Phiên bản đặc tả:** `1.0`  
**Loại tài liệu:** Product Specification (đặc tả sản phẩm); **không phải Work Package triển khai**.

## A. Nội dung được người dùng phê duyệt — nguyên văn

1. CHỨC NĂNG: đăng nhập

2. ĐẦU VÀO: tài khoản, mật khẩu, người dùng ấn đăng nhập

3. HÀNH ĐỘNG: tùy vào trạng thái server: hoạt động tốt, bảo trì

4. ĐẦU RA: hoạt động tốt - đưa vào màn hình đăng nhập, hiện danh sách server, tên nhân vật, level, vip, server

5. TRẠNG THÁI LỖI: không có kết nối mạng, thông tin tài khoản mật khẩu không chính xác

6. DỮ LIỆU LƯU TRỮ: thông tin người dùng ( tài khoản, mật khẩu, vip, server)

## B. Chi tiết CHƯA XÁC ĐỊNH (không tự điền và không tính là quy tắc đã chốt)

- Hành vi, giao diện và thông báo cụ thể khi server đang **bảo trì**: **CHƯA XÁC ĐỊNH**.
- Cách chuyển màn hình khi đăng nhập thành công và quan hệ giữa "màn hình đăng nhập" với danh sách server/nhân vật: **CHƯA XÁC ĐỊNH**. Giữ nguyên câu đầu ra của người dùng, không diễn giải lại.
- Nội dung thông báo UI trong hai trường hợp lỗi đã nêu: **CHƯA XÁC ĐỊNH**.
- Cấu trúc dữ liệu, nơi lưu và vòng đời lưu trữ (client/server) cho tài khoản, mật khẩu, VIP và server: **CHƯA XÁC ĐỊNH**.
- Cơ chế bảo vệ mật khẩu, lưu phiên/xác thực và yêu cầu bảo mật dữ liệu: **CHƯA XÁC ĐỊNH**. Việc liệt kê "mật khẩu" không phải là yêu cầu hoặc sự phê duyệt lưu **mật khẩu thô**; quá trình triển khai cần bảo vệ bí mật đăng nhập.
- Phép thử nghiệm thu chi tiết: **CHƯA XÁC ĐỊNH**.
- C2S/S2C opcode, payload, callback Lua/native, quy tắc truy cập và sơ đồ database: **CHƯA XÁC ĐỊNH**; Agent phải xác minh kỹ thuật từ APK/REA, không được giả định.

## C. Quy tắc sử dụng đặc tả

1. Người dùng xác nhận chức năng tồn tại trong app; đây là bằng chứng **yêu cầu sản phẩm**, không tự động là bằng chứng hàm/opcode từ mã máy.
2. Bảo toàn nguyên văn mục A. Không thay đổi quy tắc đã chốt, không tự thêm tính năng hay trường hợp sử dụng.
3. `CHƯA XÁC ĐỊNH` trong mục B chỉ có thể đóng bằng sự chốt bổ sung của người dùng hoặc bằng chứng kỹ thuật **nếu đó là thông tin triển khai thực tế**; không lẫn lộn hành vi APK với ý định thiết kế.
4. Tài liệu này là nguồn đầu vào được phê duyệt cho reverse engineering và lập Work Package **sau giai đoạn khảo sát/phân rã**; không là lệnh triển khai tự động. Registry 68 Work Package trước đó **NOT_APPROVED — DO NOT EXECUTE**.
5. Không lưu hoặc commit thông tin tài khoản/mật khẩu thật, token hoặc dữ liệu cá nhân thực tế vào repository.

**Nguồn phê duyệt:** người dùng gửi biểu mẫu hoàn chỉnh kèm tuyên bố "Tôi CHỐT và phê duyệt đặc tả chức năng ReturnSaiyan" trong cuộc hội thoại, ngày 2026-10-28.
