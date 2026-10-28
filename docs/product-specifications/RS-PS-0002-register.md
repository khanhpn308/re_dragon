| Index | Trường | Nội dung | Trạng thái |
|---|---|---|---|
| `F01` | Chức năng | đăng ký | ĐÃ CHỐT |
| `F02` | Đầu vào | email (optional), tài khoản, mật khẩu, xác thực lại mật khẩu, chữ cái từ a-z, A-Z, số từ 0-9 | ĐÃ CHỐT |
| `F03` | Hành động | ấn nút đăng ký, gửi code xác thực đến email, nhập code vào để hoàn tất đăng ký | ĐÃ CHỐT |
| `F04` | Đầu ra | đăng ký thành công, dữ liệu được lưu vào database, | ĐÃ CHỐT |
| `F05` | Trạng thái lỗi | tài khoản mật khẩu không nằm trong khoảng từ 8 đến 12 ký tự, không được sử dụng ký tự đặc biệt, sai định dạng @gmail.com | ĐÃ CHỐT |
| `F06` | Dữ liệu lưu trữ | tài khoản, mật khẩu, email | ĐÃ CHỐT |
| `U01` | Cần làm rõ F02, F03 | Email là optional nhưng có bước bắt buộc gửi và nhập code xác thực: quy trình khi không cung cấp email | CHƯA XÁC ĐỊNH |
| `U02` | Cần làm rõ F02, F05 | Quy định @gmail.com áp dụng bắt buộc cho email được cung cấp hay chỉ là ví dụ định dạng | CHƯA XÁC ĐỊNH |
| `U03` | Cần làm rõ F02, F05 | Xử lý khi mật khẩu và xác thực lại mật khẩu không khớp | CHƯA XÁC ĐỊNH |
| `U04` | Cần làm rõ F05 | Xử lý khi tài khoản hoặc email đã tồn tại | CHƯA XÁC ĐỊNH |
| `U05` | Cần làm rõ F03 | Thời hạn code xác thực, số lần nhập sai, gửi lại code và lỗi gửi email | CHƯA XÁC ĐỊNH |
| `U06` | Cần làm rõ F04, F06 | Cấu trúc bản ghi database, thời điểm ghi, trạng thái khi đăng ký chưa xác thực và cách lưu mật khẩu an toàn | CHƯA XÁC ĐỊNH |
| `U07` | Cần xác minh F01–F06 | Màn hình trong APK, luồng giao thức/callback, cách xử lý thực tế và phép thử nghiệm thu chi tiết | CHƯA XÁC ĐỊNH |
