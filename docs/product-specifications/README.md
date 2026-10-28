# ReturnSaiyan — Ma trận đặc tả sản phẩm đã phê duyệt

**Nguồn chuẩn:** mỗi file `RS-PS-NNNN-*.md` chứa ma trận sáu trường đã được người dùng phê duyệt (các ô `F01–F06`) và ma trận thông tin chưa xác định (`Uxx`). Bảng tổng hợp dưới đây chỉ để tra cứu; khi có mâu thuẫn, dùng giá trị trong file đặc tả được phê duyệt.

## Ma trận chức năng tổng

| Index chức năng | F01 — Chức năng | F02 — Đầu vào | F03 — Hành động | F04 — Đầu ra | F05 — Trạng thái lỗi | F06 — Dữ liệu lưu trữ | Phê duyệt | APK/REA |
|---|---|---|---|---|---|---|---|---|
| [`RS-PS-0001`](./RS-PS-0001-login.md) | đăng nhập | tài khoản, mật khẩu, người dùng ấn đăng nhập | tùy vào trạng thái server: hoạt động tốt, bảo trì | hoạt động tốt - đưa vào màn hình đăng nhập, hiện danh sách server, tên nhân vật, level, vip, server | không có kết nối mạng, thông tin tài khoản mật khẩu không chính xác | lưu phiên đăng nhập | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0002`](./RS-PS-0002-register.md) | đăng ký | email (optional), tài khoản, mật khẩu, xác thực lại mật khẩu, chữ cái từ a-z, A-Z, số từ 0-9 | ấn nút đăng ký, gửi code xác thực đến email, nhập code vào để hoàn tất đăng ký | đăng ký thành công, dữ liệu được lưu vào database, | tài khoản mật khẩu không nằm trong khoảng từ 8 đến 12 ký tự, không được sử dụng ký tự đặc biệt, sai định dạng @gmail.com | tài khoản, mật khẩu, email | `USER_APPROVED` | `NOT_YET_VERIFIED` |

## Quy ước index

| Index | Ý nghĩa |
|---|---|
| `RS-PS-NNNN` | Một chức năng trong ứng dụng do người dùng khai báo |
| `RS-PS-NNNN-F01..F06` | Từng trường đã chốt, giữ nguyên nội dung |
| `RS-PS-NNNN-U01..` | Chi tiết chưa xác định, không tự điền |
| `USER_APPROVED` | Đã được người dùng phê duyệt |
| `NOT_YET_VERIFIED` | Chưa có xác minh kỹ thuật APK/REA MCP |

**Quy trình:** mỗi phiên một form; người dùng chốt mới lưu file riêng và bổ sung một hàng vào ma trận tổng. Không tự sinh Work Package từ dữ liệu suy đoán. Bảng 68 WP trước đây chưa được duyệt, không phải nguồn đặc tả chính thức.
