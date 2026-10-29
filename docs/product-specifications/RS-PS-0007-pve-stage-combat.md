| Index | Trường | Nội dung | Trạng thái |
|---|---|---|---|
| `F01` | Chức năng | chiến đấu với quái PvE trong mục chiến đấu (đi ải) | ĐÃ CHỐT |
| `F02` | Đầu vào | người chơi ấn chọn màn chơi tương ứng với độ khó (thông thường/tinh anh), chapter, stage | ĐÃ CHỐT |
| `F03` | Hành động | tiêu hao một lượng thể lực nhất định (3) để bắt đầu một màn chơi; dựa vào chapter/stage, độ khó thông thường hoặc tinh anh, chỉ số quái vật được điều chỉnh theo độ khó (có thể chỉnh sửa được trong tương lai); hoàn thành màn chơi với không có anh hùng nào chết thì được 3 sao, 1 anh hùng chết thì 2 sao, 2 anh hùng chết trở lên thì chỉ được 1 sao | ĐÃ CHỐT |
| `F04` | Đầu ra | thông báo chiến thắng, phần thưởng sau khi hoàn thành màn chơi, tiêu diệt hết quái vật hoặc thông báo thất bại khi anh hùng bị tiêu diệt hết; dựa vào tổng số sao khi hoàn thành 10 màn sẽ được phần thưởng thêm: mốc 9 sao, 18 sao và 30 sao | ĐÃ CHỐT |
| `F05` | Trạng thái lỗi | CHƯA XÁC ĐỊNH | CHƯA XÁC ĐỊNH |
| `F06` | Dữ liệu lưu trữ | gồm các bảng: phần thưởng đặc biệt khi hoàn thành với mốc 9 sao, 18 sao và 30 sao; số EXP, vàng khi hoàn thành màn chơi; lượng thể lực tiêu thụ khi bắt đầu một màn | ĐÃ CHỐT |
| `U01` | Cần làm rõ F02, F03 | Xử lý khi thể lực hiện tại dưới 3 hoặc màn chơi chưa được mở khóa | CHƯA XÁC ĐỊNH |
| `U02` | Cần làm rõ F03, F04 | Cách tính kết quả khi người chơi rời trận, mất kết nối hoặc quái vật và toàn bộ anh hùng bị tiêu diệt cùng thời điểm | CHƯA XÁC ĐỊNH |
| `U03` | Cần làm rõ F03, F04 | Số lượng EXP/vàng, vật phẩm thưởng, cách tính thưởng khi chơi lại và tiến trình sao của mỗi màn | CHƯA XÁC ĐỊNH |
| `U04` | Cần làm rõ F04, F06 | Phạm vi nhóm 10 màn và từng độ khó/chapter; điều kiện nhận, số lần nhận và trạng thái đã nhận thưởng mốc 9/18/30 sao | CHƯA XÁC ĐỊNH |
| `U05` | Cần làm rõ F03 | Bộ chỉ số quái vật theo chapter/stage và độ khó; dữ liệu/cơ chế cấu hình để điều chỉnh sau này | CHƯA XÁC ĐỊNH |
| `U06` | Cần làm rõ F03, F06 | Sơ đồ bảng/khóa tham chiếu, nơi lưu lượng thể lực, EXP, vàng, tiến trình sao; thời điểm ghi khi bắt đầu/kết thúc trận | CHƯA XÁC ĐỊNH |
| `U07` | Cần xác minh F01–F06 | Luồng APK, màn PvE thực tế, opcode/callback, dữ liệu đối chiếu và phép thử nghiệm thu | CHƯA XÁC ĐỊNH |
