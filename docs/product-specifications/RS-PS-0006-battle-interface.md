| Index | Trường | Nội dung | Trạng thái |
|---|---|---|---|
| `F01` | Chức năng | vào giao diện chiến đấu | ĐÃ CHỐT |
| `F02` | Đầu vào | người chơi hoàn thành hướng dẫn tân thủ, ấn vào UI chiến đấu | ĐÃ CHỐT |
| `F03` | Hành động | truy xuất database từ 2 bảng tiến trình trò chơi, trả về UI của trò chơi | ĐÃ CHỐT |
| `F04` | Đầu ra | hiển thị ngay tại màn chơi người chơi đã hoàn thành, thông thường hoặc tinh anh | ĐÃ CHỐT |
| `F05` | Trạng thái lỗi | không có | ĐÃ CHỐT |
| `F06` | Dữ liệu lưu trữ | bảng 1: cấp độ thông thường, tham chiếu trực tiếp đến nhân vật, lưu tiến trình người chơi đã hoàn thành tới chapter, stage thứ mấy; bảng 2: cấp độ tinh anh, tham chiếu trực tiếp đến nhân vật, lưu tiến trình của người chơi: đã hoàn thành tới chapter, stage thứ mấy; người chơi click vào UI chiến đấu trên app | ĐÃ CHỐT |
| `U01` | Cần làm rõ F04 | Màn hình được hiển thị tại stage vừa hoàn thành hay stage tiếp theo; cách xác định chế độ thông thường/tinh anh | CHƯA XÁC ĐỊNH |
| `U02` | Cần làm rõ F03, F06 | Khóa tham chiếu nhân vật, cấu trúc hai bảng tiến trình, định danh chapter và stage | CHƯA XÁC ĐỊNH |
| `U03` | Cần làm rõ F04 | Cách hiển thị khi nhân vật chưa hoàn thành chapter/stage nào | CHƯA XÁC ĐỊNH |
| `U04` | Cần làm rõ F02, F04 | Điều kiện mở hoặc chuyển giữa chế độ thông thường và tinh anh | CHƯA XÁC ĐỊNH |
| `U05` | Cần làm rõ F03, F05 | Hành vi khi truy xuất dữ liệu thất bại hoặc mất kết nối | CHƯA XÁC ĐỊNH |
| `U06` | Cần làm rõ F06 | Thời điểm và thao tác cập nhật tiến trình sau khi hoàn thành màn chơi | CHƯA XÁC ĐỊNH |
| `U07` | Cần xác minh F01–F06 | Giao diện APK, callback/giao thức, dữ liệu lưu thực tế và phép thử nghiệm thu | CHƯA XÁC ĐỊNH |
