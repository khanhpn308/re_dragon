| Index | Trường | Nội dung | Trạng thái |
|---|---|---|---|
| `F01` | Chức năng | đăng nhập | ĐÃ CHỐT |
| `F02` | Đầu vào | tài khoản, mật khẩu, người dùng ấn đăng nhập | ĐÃ CHỐT |
| `F03` | Hành động | tùy vào trạng thái server: hoạt động tốt, bảo trì | ĐÃ CHỐT |
| `F04` | Đầu ra | hoạt động tốt - đưa vào màn hình đăng nhập, hiện danh sách server, tên nhân vật, level, vip, server | ĐÃ CHỐT |
| `F05` | Trạng thái lỗi | không có kết nối mạng, thông tin tài khoản mật khẩu không chính xác | ĐÃ CHỐT |
| `F06` | Dữ liệu lưu trữ | lưu phiên đăng nhập | ĐÃ CHỐT |
| `C01` | Làm rõ F06 | Thông tin tài khoản, mật khẩu, VIP và server chỉ truy xuất từ database; không thuộc dữ liệu yêu cầu lưu riêng của chức năng này | ĐÃ CHỐT |
| `U01` | Cần làm rõ F03 | Hành vi, giao diện và thông báo cụ thể khi server bảo trì | CHƯA XÁC ĐỊNH |
| `U02` | Cần làm rõ F04 | Cách chuyển màn hình khi đăng nhập thành công và quan hệ giữa màn hình đăng nhập với danh sách server/nhân vật | CHƯA XÁC ĐỊNH |
| `U03` | Cần làm rõ F05 | Nội dung thông báo UI khi không có kết nối mạng hoặc tài khoản/mật khẩu không chính xác | CHƯA XÁC ĐỊNH |
| `U04` | Cần làm rõ F06 | Cấu trúc và vòng đời phiên đăng nhập; nơi lưu, thời hạn, gia hạn và thu hồi phiên | CHƯA XÁC ĐỊNH |
| `U05` | Cần làm rõ F02, F06 | Cơ chế bảo mật phiên/xác thực và cách truy xuất, xử lý thông tin tài khoản, mật khẩu, VIP, server từ database | CHƯA XÁC ĐỊNH |
| `U06` | Cần làm rõ F01–F06 | Phép thử nghiệm thu chi tiết | CHƯA XÁC ĐỊNH |
| `U07` | Cần xác minh F01–F06 | C2S/S2C opcode, payload, callback Lua/native, quy tắc truy cập và sơ đồ database | CHƯA XÁC ĐỊNH |
