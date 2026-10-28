# RS-PS-0001 — Đăng nhập

| Index | Thuộc tính | Giá trị |
|---|---|---|
| `RS-PS-0001` | Chức năng | đăng nhập |
| `META-01` | Trạng thái phê duyệt | `USER_APPROVED` — người dùng chốt ngày 2026-10-28 |
| `META-02` | Xác nhận có trong ứng dụng | `USER_CONFIRMED` |
| `META-03` | Kiểm chứng kỹ thuật APK/REA MCP | `NOT_YET_VERIFIED` |
| `META-04` | Phiên bản tài liệu | `1.1` — chỉ đổi cấu trúc trình bày, không sửa yêu cầu phiên 1.0 |
| `META-05` | Loại tài liệu | Product Specification — không phải Work Package triển khai |

## A. Ma trận yêu cầu đã phê duyệt

**Nguồn:** Nội dung người dùng đã chốt, giữ nguyên từng giá trị; không diễn giải lại.

| Index | Trường | Nội dung người dùng phê duyệt (nguyên văn) | Trạng thái |
|---|---|---|---|
| `RS-PS-0001-F01` | Chức năng | đăng nhập | `USER_APPROVED` |
| `RS-PS-0001-F02` | Đầu vào | tài khoản, mật khẩu, người dùng ấn đăng nhập | `USER_APPROVED` |
| `RS-PS-0001-F03` | Hành động | tùy vào trạng thái server: hoạt động tốt, bảo trì | `USER_APPROVED` |
| `RS-PS-0001-F04` | Đầu ra | hoạt động tốt - đưa vào màn hình đăng nhập, hiện danh sách server, tên nhân vật, level, vip, server | `USER_APPROVED` |
| `RS-PS-0001-F05` | Trạng thái lỗi | không có kết nối mạng, thông tin tài khoản mật khẩu không chính xác | `USER_APPROVED` |
| `RS-PS-0001-F06` | Dữ liệu lưu trữ | thông tin người dùng ( tài khoản, mật khẩu, vip, server) | `USER_APPROVED` |

## B. Ma trận khoảng trống thông tin

Các dòng này **không phải quy tắc được người dùng phê duyệt**. Chúng chỉ ghi rõ điều chưa đủ dữ kiện, không tự tạo hành vi mới.

| Index | Liên kết yêu cầu | Thông tin cần làm rõ/xác minh | Trạng thái |
|---|---|---|---|
| `RS-PS-0001-U01` | `RS-PS-0001-F03` | Hành vi, giao diện và thông báo cụ thể khi server đang **bảo trì** | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U02` | `RS-PS-0001-F04` | Cách chuyển màn hình khi đăng nhập thành công và quan hệ giữa "màn hình đăng nhập" với danh sách server/nhân vật | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U03` | `RS-PS-0001-F05` | Nội dung thông báo UI trong hai trường hợp lỗi đã nêu | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U04` | `RS-PS-0001-F06` | Cấu trúc dữ liệu, nơi lưu và vòng đời lưu trữ (client/server) cho tài khoản, mật khẩu, VIP và server | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U05` | `RS-PS-0001-F06` | Cơ chế bảo vệ mật khẩu, lưu phiên/xác thực và yêu cầu bảo mật dữ liệu | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U06` | `RS-PS-0001-F01–F06` | Phép thử nghiệm thu chi tiết | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U07` | `RS-PS-0001-F01–F06` | C2S/S2C opcode, payload, callback Lua/native, quy tắc truy cập và sơ đồ database | **CHƯA XÁC ĐỊNH** |

**Chú thích cho `RS-PS-0001-U02`:** Giữ nguyên câu đầu ra đã phê duyệt; không tự quyết định trình tự màn hình.

**Chú thích bảo mật cho `RS-PS-0001-U05`:** Cụm từ “mật khẩu” trong yêu cầu không phải sự phê duyệt lưu mật khẩu thô; mọi triển khai phải bảo vệ bí mật xác thực. Chưa chốt vị trí hoặc cơ chế lưu trữ.

**Chú thích kỹ thuật cho `RS-PS-0001-U07`:** Agent phải xác minh opcode, payload, Lua/native callback và schema database từ APK/REA; không được điền bằng suy đoán.

## C. Quy tắc định danh và truy vết

| Dạng index | Ý nghĩa |
|---|---|
| `RS-PS-NNNN` | Đặc tả của một chức năng, định danh bất biến |
| `RS-PS-NNNN-F01..F06` | Sáu trường nội dung đã được người dùng chốt |
| `RS-PS-NNNN-U01..` | Các điểm chưa xác định, gắn với trường tương ứng |
| `META-XX` | Metadata tài liệu, không phải luật gameplay |

1. Người dùng xác nhận chức năng có trong app; đó là **xác nhận yêu cầu sản phẩm**, chưa tự động là bằng chứng hàm/opcode từ mã máy.
2. Không sửa giá trị `F01–F06` khi chỉ chuẩn hóa hình thức; các thay đổi sản phẩm sau này cần người dùng phê duyệt phiên bản mới và lưu lịch sử.
3. Các mục `Uxx` chỉ được giải quyết bằng phê duyệt bổ sung cho hành vi sản phẩm, hoặc bằng bằng chứng kỹ thuật khi đó là chi tiết triển khai thực tế. Không đánh đồng hai nguồn.
4. Tài liệu là nguồn đầu vào cho reverse engineering và phân rã Work Package **sau khi có đủ cơ sở và được phê duyệt**. Registry 68 WP trước đó **NOT_APPROVED — DO NOT EXECUTE**.
5. Không lưu hoặc commit tài khoản, mật khẩu thật, token hoặc dữ liệu cá nhân của người chơi vào repository.

**Nguồn phê duyệt:** Người dùng gửi biểu mẫu hoàn chỉnh kèm lời xác nhận “Tôi CHỐT và phê duyệt đặc tả chức năng ReturnSaiyan” ngày 2026-10-28.
