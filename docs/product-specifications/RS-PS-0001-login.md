# RS-PS-0001 — Đăng nhập

| Index | Thuộc tính | Giá trị |
|---|---|---|
| `RS-PS-0001` | Chức năng | đăng nhập |
| `META-01` | Trạng thái phê duyệt | `USER_APPROVED` — người dùng chốt ngày 2026-10-28 |
| `META-02` | Xác nhận có trong ứng dụng | `USER_CONFIRMED` |
| `META-03` | Kiểm chứng kỹ thuật APK/REA MCP | `NOT_YET_VERIFIED` |
| `META-04` | Phiên bản tài liệu | `1.2` — cập nhật F06 theo xác nhận sửa đổi của người dùng ngày 2026-10-28 |
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
| `RS-PS-0001-F06` | Dữ liệu lưu trữ | lưu phiên đăng nhập | `USER_APPROVED — REVISED` |

**Làm rõ được người dùng phê duyệt cho F06:** “các thông tin trên chỉ là truy xuất từ database thôi” — tức thông tin tài khoản, mật khẩu, VIP và server thuộc dữ liệu truy xuất từ database, không phải dữ liệu mà chức năng này được yêu cầu lưu riêng. Điều này không cho phép suy diễn cơ chế đọc, xử lý hay trả về mật khẩu.

## B. Ma trận khoảng trống thông tin

Các dòng này **không phải quy tắc được người dùng phê duyệt**. Chúng chỉ ghi rõ điều chưa đủ dữ kiện, không tự tạo hành vi mới.

| Index | Liên kết yêu cầu | Thông tin cần làm rõ/xác minh | Trạng thái |
|---|---|---|---|
| `RS-PS-0001-U01` | `RS-PS-0001-F03` | Hành vi, giao diện và thông báo cụ thể khi server đang **bảo trì** | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U02` | `RS-PS-0001-F04` | Cách chuyển màn hình khi đăng nhập thành công và quan hệ giữa "màn hình đăng nhập" với danh sách server/nhân vật | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U03` | `RS-PS-0001-F05` | Nội dung thông báo UI trong hai trường hợp lỗi đã nêu | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U04` | `RS-PS-0001-F06` | Cấu trúc và vòng đời phiên đăng nhập; nơi lưu, thời hạn, gia hạn, thu hồi phiên | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U05` | `RS-PS-0001-F02`, `RS-PS-0001-F06` | Cơ chế bảo mật phiên/xác thực và cách truy xuất, xử lý thông tin tài khoản, mật khẩu, VIP, server từ database | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U06` | `RS-PS-0001-F01–F06` | Phép thử nghiệm thu chi tiết | **CHƯA XÁC ĐỊNH** |
| `RS-PS-0001-U07` | `RS-PS-0001-F01–F06` | C2S/S2C opcode, payload, callback Lua/native, quy tắc truy cập và sơ đồ database | **CHƯA XÁC ĐỊNH** |

**Chú thích cho `RS-PS-0001-U02`:** Giữ nguyên câu đầu ra đã phê duyệt; không tự quyết định trình tự màn hình.

**Chú thích bảo mật cho `RS-PS-0001-U05`:** Việc dữ liệu xác thực có liên quan đến database không phải yêu cầu lưu mật khẩu thô hoặc trả mật khẩu về client. Phương thức xác minh mật khẩu và bảo vệ phiên chưa được chốt.

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

## D. Lịch sử sửa đổi yêu cầu

| Phiên bản | Index | Nội dung trước | Nội dung sau | Lý do |
|---|---|---|---|---|
| `1.0` | `RS-PS-0001-F06` | thông tin người dùng ( tài khoản, mật khẩu, vip, server) | — | Nội dung phê duyệt lần đầu |
| `1.1` | — | — | — | Chuyển cách trình bày sang ma trận, không sửa yêu cầu |
| `1.2` | `RS-PS-0001-F06` | thông tin người dùng ( tài khoản, mật khẩu, vip, server) | lưu phiên đăng nhập | Người dùng sửa F06 và làm rõ thông tin tài khoản, mật khẩu, VIP, server chỉ truy xuất từ database |

**Nguồn phê duyệt:** Biểu mẫu người dùng đã chốt ngày 2026-10-28; sửa đổi F06 do người dùng yêu cầu trực tiếp ngày 2026-10-28.
