# ReturnSaiyan — Ma trận đặc tả sản phẩm đã phê duyệt

**Nguồn chuẩn:** mỗi file `RS-PS-NNNN-*.md` chứa ma trận sáu trường đã được người dùng phê duyệt (các ô `F01–F06`) và ma trận thông tin chưa xác định (`Uxx`). Bảng tổng hợp dưới đây chỉ để tra cứu; khi có mâu thuẫn, dùng giá trị trong file đặc tả được phê duyệt.

## Ma trận chức năng tổng

| Index chức năng | F01 — Chức năng | F02 — Đầu vào | F03 — Hành động | F04 — Đầu ra | F05 — Trạng thái lỗi | F06 — Dữ liệu lưu trữ | Phê duyệt | APK/REA |
|---|---|---|---|---|---|---|---|---|
| [`RS-PS-0001`](./RS-PS-0001-login.md) | đăng nhập | tài khoản, mật khẩu, người dùng ấn đăng nhập | tùy vào trạng thái server: hoạt động tốt, bảo trì | hoạt động tốt - đưa vào màn hình đăng nhập, hiện danh sách server, tên nhân vật, level, vip, server | không có kết nối mạng, thông tin tài khoản mật khẩu không chính xác | lưu phiên đăng nhập | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0002`](./RS-PS-0002-register.md) | đăng ký | email (optional), tài khoản, mật khẩu, xác thực lại mật khẩu, chữ cái từ a-z, A-Z, số từ 0-9 | ấn nút đăng ký, gửi code xác thực đến email, nhập code vào để hoàn tất đăng ký | đăng ký thành công, dữ liệu được lưu vào database, | tài khoản mật khẩu không nằm trong khoảng từ 8 đến 12 ký tự, không được sử dụng ký tự đặc biệt, sai định dạng @gmail.com | tài khoản, mật khẩu, email | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0003`](./RS-PS-0003-password-recovery.md) | lấy lại mật khẩu | email, tên đăng nhập | gửi code reset mật khẩu | cho user nhập mật khẩu mới khi nhập code xác thực thành công | email không chính xác, nhập lại mật khẩu xác thực mới không chính xác | ghi đè vào trường mật khẩu cũ của user | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0004`](./RS-PS-0004-character-select.md) | chọn nhân vật đăng nhập | đăng nhập thành công | truy xuất database các nhân vật của tài khoản | hiển thị các danh sách nhân vật trong database gồm có: tên, avatar, vip. lực chiến, server | đăng nhập thất bại | database là bảng nhân vật tham chiếu theo tài khoản đăng nhập | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0005`](./RS-PS-0005-new-player-tutorial.md) | hướng dẫn tân thủ | chọn nhân vật thành công | có thể bỏ qua, khi mới vào sẽ có một phần chơi hướng dẫn ngắn, có thể có dữ liệu trong app, yêu cầu agent dịch ngược | hoàn thành phần chơi hướng dẫn, người chơi có thể thao tác và bắt đầu chơi một cách bình thường | không có | trạng thái tài khoản: đã qua giai đoạn hướng dẫn | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0006`](./RS-PS-0006-battle-interface.md) | vào giao diện chiến đấu | người chơi hoàn thành hướng dẫn tân thủ, ấn vào UI chiến đấu | truy xuất database từ 2 bảng tiến trình trò chơi, trả về UI của trò chơi | hiển thị ngay tại màn chơi người chơi đã hoàn thành, thông thường hoặc tinh anh | không có | bảng 1: cấp độ thông thường, tham chiếu trực tiếp đến nhân vật, lưu tiến trình người chơi đã hoàn thành tới chapter, stage thứ mấy; bảng 2: cấp độ tinh anh, tham chiếu trực tiếp đến nhân vật, lưu tiến trình của người chơi: đã hoàn thành tới chapter, stage thứ mấy; người chơi click vào UI chiến đấu trên app | `USER_APPROVED` | `NOT_YET_VERIFIED` |
| [`RS-PS-0007`](./RS-PS-0007-pve-stage-combat.md) | chiến đấu với quái PvE trong mục chiến đấu (đi ải) | người chơi ấn chọn màn chơi tương ứng với độ khó (thông thường/tinh anh), chapter, stage | tiêu hao một lượng thể lực nhất định (3) để bắt đầu một màn chơi; dựa vào chapter/stage, độ khó thông thường hoặc tinh anh, chỉ số quái vật được điều chỉnh theo độ khó (có thể chỉnh sửa được trong tương lai); hoàn thành màn chơi với không có anh hùng nào chết thì được 3 sao, 1 anh hùng chết thì 2 sao, 2 anh hùng chết trở lên thì chỉ được 1 sao | thông báo chiến thắng, phần thưởng sau khi hoàn thành màn chơi, tiêu diệt hết quái vật hoặc thông báo thất bại khi anh hùng bị tiêu diệt hết; dựa vào tổng số sao khi hoàn thành 10 màn sẽ được phần thưởng thêm: mốc 9 sao, 18 sao và 30 sao | CHƯA XÁC ĐỊNH | gồm các bảng: phần thưởng đặc biệt khi hoàn thành với mốc 9 sao, 18 sao và 30 sao; số EXP, vàng khi hoàn thành màn chơi; lượng thể lực tiêu thụ khi bắt đầu một màn | `USER_APPROVED` | `NOT_YET_VERIFIED` |

## Quy ước index

| Index | Ý nghĩa |
|---|---|
| `RS-PS-NNNN` | Một chức năng trong ứng dụng do người dùng khai báo |
| `RS-PS-NNNN-F01..F06` | Từng trường đã chốt, giữ nguyên nội dung |
| `RS-PS-NNNN-U01..` | Chi tiết chưa xác định, không tự điền |
| `USER_APPROVED` | Đã được người dùng phê duyệt |
| `NOT_YET_VERIFIED` | Chưa có xác minh kỹ thuật APK/REA MCP |

**Quy trình:** mỗi phiên một form; người dùng chốt mới lưu file riêng và bổ sung một hàng vào ma trận tổng. Không tự sinh Work Package từ dữ liệu suy đoán. Bảng 68 WP trước đây chưa được duyệt, không phải nguồn đặc tả chính thức.
