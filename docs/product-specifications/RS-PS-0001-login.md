# RS-PS-0001 — Đăng nhập

| Index | Trường | Nội dung đã chốt |
|---|---|---|
| `F01` | Chức năng | đăng nhập |
| `F02` | Đầu vào | tài khoản, mật khẩu, người dùng ấn đăng nhập |
| `F03` | Hành động | tùy vào trạng thái server: hoạt động tốt, bảo trì |
| `F04` | Đầu ra | hoạt động tốt - đưa vào màn hình đăng nhập, hiện danh sách server, tên nhân vật, level, vip, server |
| `F05` | Trạng thái lỗi | không có kết nối mạng, thông tin tài khoản mật khẩu không chính xác |
| `F06` | Dữ liệu lưu trữ | lưu phiên đăng nhập |

**Làm rõ F06:** Thông tin tài khoản, mật khẩu, VIP và server chỉ truy xuất từ database; chức năng này lưu phiên đăng nhập.

## Chưa xác định

| Index | Nội dung |
|---|---|
| `U01` | Hành vi khi server bảo trì |
| `U02` | Trình tự chuyển màn hình sau đăng nhập |
| `U03` | Nội dung thông báo lỗi |
| `U04` | Vị trí lưu, thời hạn và vòng đời phiên đăng nhập |
| `U05` | Cơ chế xác thực, bảo vệ phiên và xử lý dữ liệu từ database |
| `U06` | Phép thử nghiệm thu chi tiết |
| `U07` | Opcode, payload, Lua/native callback và schema database |

**Lịch sử:** F06 được sửa theo yêu cầu ngày 2026-10-28 (v1.2). Giá trị cũ được lưu trong Git history.
