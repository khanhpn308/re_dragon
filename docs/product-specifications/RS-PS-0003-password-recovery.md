| Index | Trường | Nội dung | Trạng thái |
|---|---|---|---|
| `F01` | Chức năng | lấy lại mật khẩu | ĐÃ CHỐT |
| `F02` | Đầu vào | email, tên đăng nhập | ĐÃ CHỐT |
| `F03` | Hành động | gửi code reset mật khẩu | ĐÃ CHỐT |
| `F04` | Đầu ra | cho user nhập mật khẩu mới khi nhập code xác thực thành công | ĐÃ CHỐT |
| `F05` | Trạng thái lỗi | email không chính xác, nhập lại mật khẩu xác thực mới không chính xác | ĐÃ CHỐT |
| `F06` | Dữ liệu lưu trữ | ghi đè vào trường mật khẩu cũ của user | ĐÃ CHỐT |
| `U01` | Cần làm rõ F02 | Cách đối chiếu email với tên đăng nhập; hành vi nếu tài khoản không có email | CHƯA XÁC ĐỊNH |
| `U02` | Cần làm rõ F03 | Kênh nhận code xác thực, thời hạn hiệu lực, giới hạn gửi và gửi lại code | CHƯA XÁC ĐỊNH |
| `U03` | Cần làm rõ F03, F04 | Xử lý code sai, hết hạn hoặc đã sử dụng | CHƯA XÁC ĐỊNH |
| `U04` | Cần làm rõ F04, F05 | Yêu cầu nhập và xác nhận mật khẩu mới; quy tắc độ dài, ký tự cho mật khẩu mới | CHƯA XÁC ĐỊNH |
| `U05` | Cần làm rõ F05 | Nội dung thông báo lỗi và giới hạn số lần xác thực sai | CHƯA XÁC ĐỊNH |
| `U06` | Cần làm rõ F06 | Thời điểm cập nhật mật khẩu, cách bảo vệ giá trị mật khẩu trong database và xử lý phiên đăng nhập cũ | CHƯA XÁC ĐỊNH |
| `U07` | Cần xác minh F01–F06 | Giao diện APK, giao thức/callback và phép thử nghiệm thu thực tế | CHƯA XÁC ĐỊNH |
