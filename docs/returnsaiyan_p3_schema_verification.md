# Báo cáo P3 — Kiểm định Cấu trúc Gói tin & Tương thích Giao thức Toàn diện

> **Mã điều tra Harness:** `18708f0e6e3d4d72`  
> **Mục tiêu nhị phân:** [`libaos_jogo.so`](file:///home/khanh/returnsaiyan-re/libaos_jogo.so) (AArch64, Android ELF 64-bit)  
> **Mã băm SHA-256:** `5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f`  
> **Bộ kiểm thử P3:** [`test_codec_p3.py`](file:///home/khanh/returnsaiyan-re/test_codec_p3.py) (7/7 bài kiểm thử PASS)  
> **Commit bàn giao P2:** [`2e9bb55`](https://github.com/khanhpn308/re_dragon/commit/2e9bb55) trên nhánh `main` của `khanhpn308/re_dragon`.

---

## 1. Tóm tắt Kiểm toán Toàn cục & Mục tiêu Giai đoạn P3

Giai đoạn P3 (**Packet Schema & Compatibility Verification**) tập trung vào kiểm định độc lập, sâu và khắt khe nhất đối với:
1. **Kiểm toán toàn cục ELF nhị phân:** Xác minh không có sự đếm trùng lặp hoặc sót opcode giữa các bảng đăng ký handler.
2. **Trích xuất cấu trúc trường (payload schema):** Ánh xạ 1:1 từng opcode với địa chỉ mã máy, vtable và chuỗi lời gọi phương thức giải mã tuần tự của `LeitorPacote`.
3. **Tính chất trạng thái mật mã (Cryptographic Statelessness):** Chứng minh tính phi trạng thái giữa các frame liên tiếp của cả hai cipher C2S và S2C.
4. **Kiểm thử chịu lỗi biên (Robustness & Fault Tolerance):** Mô phỏng ngắt ngang 1 byte ở header, payload bị phân mảnh nhiều phần, ghép dồn 10 frame liên tiếp và bảo vệ buffer trước các trường dữ liệu sai lệch độ dài.
5. **Ranh giới nhận thức nghiêm ngặt (Strict Epistemics):** Khẳng định các dữ kiện từ mã máy là `VERIFIED`, cấu trúc suy luận hình học là `INFERRED`, và ý nghĩa nguyên thủy phía server của 3 byte chào hỏi là `UNKNOWN` (không tự suy đoán).

---

## 2. Kiểm toán Toàn cục Opcode: Đảm bảo 27 Opcode Duy nhất (0 Trùng lặp)

Qua quá trình quét toàn bộ mã máy của thư viện 190MB `libaos_jogo.so`, điểm phân phối bản tin mạng qua hàm [`aos::Conexao::registrar`](file:///home/khanh/returnsaiyan-re/returnsaiyan_codec.py#L328-L360) (`0x006a8db0`) được kiểm toán tuyệt đối:

```text
Kiểm toán lệnh gọi bl 0x6a8db0 trên toàn bộ ELF:
- aos::registrarChat (0x0075eed4): Đúng 1 lệnh gọi tại 0x75ef0c (Opcode 0x29)
- aos::CProtocolManager::registrarTratadores (0x007ede44): Đúng 26 lệnh gọi từ 0x7ede8c đến 0x7ee604
Tổng số lệnh gọi Conexao::registrar trong toàn bộ binary: 27 lệnh gọi.
```

Tất cả 27 giá trị opcode truyền vào thanh ghi `w1` đều là các số nguyên độc lập, hoàn toàn phân biệt:
- **Tập hợp Hex:** `0x00, 0x01, 0x04, 0x05, 0x07, 0x08, 0x0A, 0x10, 0x12, 0x20, 0x21, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D, 0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x43`.
- **Tập hợp Thập phân:** `0, 1, 4, 5, 7, 8, 10, 16, 18, 32, 33, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 67`.
- **Tỷ lệ trùng lặp:** **0% (27/27 unique)**. Không có sự đếm trùng giữa `registrarTratadores` và `registrarChat`.

---

## 3. Bảng Ánh xạ Toàn diện: Opcode $\rightarrow$ Handler $\rightarrow$ Payload Schema $\rightarrow$ Bằng chứng

Toàn bộ 27 opcodes đã được đối chiếu trực tiếp qua vtable Itanium ABI (`.data.rel.ro`), trích xuất địa chỉ thực thi lambda thực tế, kích thước hàm và chuỗi lệnh gọi `LeitorPacote` trong phạm vi ranh giới hàm AArch64:

| Opcode | Tên Delegate / Lambda | Địa chỉ Thực thi | Địa chỉ Vtable | Chuỗi Giải mã (`LeitorPacote`) | Cấu trúc | Phân loại |
| :---: | :--- | :---: | :---: | :--- | :---: | :---: |
| `0x00` ( 0) | `$_5` | `0x007f06c8` | `0x014f0e60` | `str` | STATIC | `VERIFIED` |
| `0x01` ( 1) | `$_6` | `0x007f0a0c` | `0x014f0ee0` | `str -> u8` *(Header; theo sau là mảng nhân vật biến thiên)* | DYNAMIC | `PARTIAL` |
| `0x04` ( 4) | `$_7` | `0x007f4ba4` | `0x014f0f60` | `str -> str` | STATIC | `VERIFIED` |
| `0x05` ( 5) | `$_8` | `0x007f4de4` | `0x014f0fe0` | `str` | STATIC | `VERIFIED` |
| `0x07` ( 7) | `$_9` | `0x007f5060` | `0x014f1060` | `u8 -> str` | STATIC | `VERIFIED` |
| `0x08` ( 8) | `$_10` | `0x007f5604` | `0x014f10e0` | `u8` *(Tail-call `b LeitorPacote::u8`)* | STATIC | `VERIFIED` |
| `0x0A` (10) | `$_11` | `0x007f5690` | `0x014f1160` | `str` | STATIC | `VERIFIED` |
| `0x10` (16) | `$_13` | `0x007f5a8c` | `0x014f1260` | `i32 -> i64 -> i32[6] -> u8[2] -> i32 -> u8 -> str` *(Header; 62 calls buff rẽ nhánh)* | DYNAMIC | `PARTIAL` |
| `0x12` (18) | `$_12` | `0x007f57b0` | `0x014f11e0` | `u8 -> str` | STATIC | `VERIFIED` |
| `0x20` (32) | `$_14` | `0x007f7078` | `0x014f12e0` | `i16 -> i64 -> i32 -> i16 -> i16 -> i32 -> i64` | DYNAMIC | `PARTIAL` |
| `0x21` (33) | `$_15` | `0x007f7b9c` | `0x014f1360` | `str -> i32 -> u8 -> i32 -> u8[3] -> i32 -> u8` *(Header; vòng lặp battle entities)* | DYNAMIC | `PARTIAL` |
| `0x25` (37) | `$_16` | `0x007f7f00` | `0x014f13e0` | `i64 -> i32 -> i16 -> i16 -> u8 -> i32` | STATIC | `VERIFIED` |
| `0x26` (38) | `$_17` | `0x007f8058` | `0x014f1460` | `str -> u8 -> str -> u8` | STATIC | `VERIFIED` |
| `0x27` (39) | `$_18` | `0x007f85c8` | `0x014f14e0` | `i32` | STATIC | `VERIFIED` |
| `0x28` (40) | `$_19` | `0x007f94c4` | `0x014f1560` | `i32` | STATIC | `VERIFIED` |
| `0x29` (41) | `chat_$_1` (`CChatManager::receberChatUpdate`) | `0x0075eca4` | `0x014efa88` | `i64 -> str -> u8 -> str -> str -> u8 -> str -> str` | STATIC | `VERIFIED` |
| `0x2A` (42) | `$_20` | `0x007f9c2c` | `0x014f15e0` | `u8 -> i32[3]` *(Header; vòng lặp inventory slots)* | DYNAMIC | `PARTIAL` |
| `0x2B` (43) | `$_21` | `0x007fd6fc` | `0x014f16d0` | `str -> u8[2] -> i32[2]` *(Header; tiến trình nhiệm vụ)* | DYNAMIC | `PARTIAL` |
| `0x2C` (44) | `$_28` | `0x0080203c` | `0x014f1a50` | `i64 -> u8 -> i16 -> i32[2] -> str -> i64 -> i16` | STATIC | `VERIFIED` |
| `0x2D` (45) | `$_22` | `0x007fed18` | `0x014f1750` | `u8[2] -> i32[2] -> i16` *(Header; thông báo sự kiện)* | DYNAMIC | `PARTIAL` |
| `0x2E` (46) | `$_23` | `0x007ffc28` | `0x014f17d0` | `u8 -> str[5]` | STATIC | `VERIFIED` |
| `0x2F` (47) | `$_29` | `0x00803800` | `0x014f1ad0` | `u8[2] -> str` *(Header; vòng lặp mail & attachments)* | DYNAMIC | `PARTIAL` |
| `0x30` (48) | `$_24` | `0x00800864` | `0x014f1850` | `u8 -> u8` | STATIC | `VERIFIED` |
| `0x31` (49) | `$_30` | `0x00806184` | `0x014f1b50` | `i32 -> str` | STATIC | `VERIFIED` |
| `0x32` (50) | `$_25` | `0x00800f04` | `0x014f18d0` | `u8[5] -> i32 -> u8` *(Header; thuộc tính popup)* | DYNAMIC | `PARTIAL` |
| `0x33` (51) | `$_26` | `0x00801828` | `0x014f1950` | `u8 -> str` | STATIC | `VERIFIED` |
| `0x43` (67) | `$_27` | `0x00801bac` | `0x014f19d0` | `u8[2] -> i32 -> u8[4] -> i32` | STATIC | `VERIFIED` |

> [!IMPORTANT]
> **Giải thích nguyên nhân sai khác ban đầu (Audited Discrepancy Reconciliation):**
> 1. Trong báo cáo P3 trước đó, một số handler có kích thước nhỏ (ví dụ `$_5` 704b, `$_7` 472b, `$_10` 8b, `$_11` 156b, `$_12` 600b, `$_24` 868b) bị phân tích tràn sang thân hàm kế tiếp do cửa sổ disassembly cố định. Việc đọc chính xác ranh giới hàm ELF (`.symtab`) và vtable Itanium ABI (`vtable + 0x40`) đã xác lập chính xác 100% các lệnh gọi thuộc về từng handler.
> 2. Phân biệt tường minh giữa **`STATIC`** (chuỗi giải mã tuyến tính, hoàn tất và bất biến) và **`DYNAMIC`** (chuỗi header xác thực được, theo sau bởi các vòng lặp đếm số phần tử hoặc các khối rẽ nhánh điều kiện). Việc không ép cấu trúc động thành mảng tuyến tính giúp codec xử lý an toàn và không bị exception khi gặp payload thực tế.

---

## 4. Bằng chứng về 3 Byte Handshake Server Greeting & Tính Bất biến

Thực hiện yêu cầu *"Truy vết ý nghĩa ba byte đầu Server Greeting nếu có đủ bằng chứng. Không tự suy đoán"*:

1. **Bằng chứng Mã máy (`VERIFIED`):**
   - Tại `0x007ea274..0x007ea360` ([`scratch/threadRecepcao.asm`](file:///home/khanh/.gemini/antigravity-cli/brain/cc56a9da-47c1-452d-afa1-8152d197f932/scratch/threadRecepcao.asm#L174-L230)), buffer 7 bytes được đọc vào `[x29 - 136]`.
   - Lệnh duy nhất truy cập buffer là `ldur w8, [x29, #-133]` (đọc offset `+3..+6`).
   - Bytes 0, 1, 2 **không bao giờ được nạp vào thanh ghi, so sánh, hoặc xác thực** bởi bất kỳ câu lệnh nào trong binary.
2. **Kiểm thử Tính Bất biến (`VERIFIED`):**
   - Bài test `test_server_greeting_prefix_invariance` trong [`test_codec_p3.py`](file:///home/khanh/returnsaiyan-re/test_codec_p3.py) đã thử nghiệm thay thế 3 byte đầu bằng 5 tiền tố khác nhau: `b'\x00\x05\x00'`, `b'AOS'`, `b'TCP'`, `b'\xFF\xFF\xFF'`, và `b'\x12\x34\x56'`.
   - Kết quả: **Khóa bí mật sinh ra hoàn toàn không thay đổi**. Client hoạt động 100% độc lập với nội dung 3 byte này.
3. **Kết luận Nhận thức Nghiêm ngặt:**
   - Ý nghĩa thực sự của 3 byte này ở phía server (liệu server gửi `0x000500` làm header unencrypted, hay chuỗi magic `AOS`, hay mã hiệu phiên bản protocol) **KHÔNG THỂ CHỨNG MINH ĐƯỢC** nếu chỉ dựa vào phân tích tĩnh file nhị phân của client.
   - Do đó, trạng thái ngữ nghĩa nguyên thủy phía server được giữ nguyên là **`UNKNOWN`** và **không đưa ra kết luận suy đoán**.

---

## 5. Xác minh Tính Phi Trạng thái của Mật mã (Cross-Packet Statelessness)

1. **Khẳng định Mã máy (`VERIFIED`):**
   - Trong `aos::cifrarC2S` (`0x007ec850`): Biến tích lũy `prev` luôn được khởi tạo lại bằng `w8 = w2` (`key`) ở đầu hàm (`0x7ec854: mov w8, w2`). Mỗi packet bắt đầu độc lập với $C[0] = P[0]$.
   - Trong `threadRecepcao` (`0x007ea4dc`): Lệnh `dup v0.16b, w8` nạp lại `key` từ `this->chave` cho từng frame nhận được.
   - Không có con trỏ trạng thái luồng (stream state context) nào được cập nhật giữa packet $N$ và packet $N+1$.
2. **Kiểm thử Thực nghiệm (`VERIFIED`):**
   - Bài test `test_cross_packet_xor_statelessness` đã chứng minh bản mã của gói tin thứ hai mã hóa liên tiếp hoàn toàn đồng nhất với khi mã hóa độc lập.
   - Điều này đảm bảo: Nếu một gói tin trung gian bị mất mát hoặc giải mã riêng lẻ, các gói tin kế tiếp vẫn được giải mã bình thường (miễn là không lệch biên giới socket framing).

---

## 6. Kết quả Thực thi Bộ Kiểm thử Toàn diện P3 ([`test_codec_p3.py`](file:///home/khanh/returnsaiyan-re/test_codec_p3.py))

```text
======================================================================
Running P3 Comprehensive Verification Suite
======================================================================
[P3 TEST 1] Verifying 27 Opcode Uniqueness & Boundary Values...
  -> PASS: All 27 opcodes are strictly distinct and registered.
[P3 TEST 2] TCP Stream with Truncated Header (1 byte split)...
  -> PASS: Split header successfully accumulated without desynchronization.
[P3 TEST 3] TCP Stream with Truncated Payload (Multi-part arrival)...
  -> PASS: Multi-chunk payload reassembled and verified.
[P3 TEST 4] PacketReader Safety against Malformed / Out-of-Bounds Buffers...
  -> PASS: Out-of-bounds reads handled safely without memory corruption.
[P3 TEST 5] Verification of Cross-Packet XOR Statelessness...
  -> PASS: Both C2S and S2C ciphers proven packet-stateless.
[P3 TEST 6] Server Greeting Bytes 0..2 Invariance Test...
  -> PASS: Client is 100% invariant to bytes 0..2 of server greeting.
[P3 TEST 7] TCP Burst Coalescing (10 back-to-back packets in single read)...
  -> PASS: 10 coalesced packets cleanly separated and dispatched in single read.
======================================================================
ALL P3 TESTS PASSED: Protocol Robustness & Streaming Integrity Verified!
======================================================================
```

---

## 7. Cập nhật Trạng thái Điều tra trong Harness MCP

Tiến trình điều tra `18708f0e6e3d4d72` đã đồng bộ các quan sát và phát hiện mới của P3:

- **Quan sát mới:**
  - `57b3293e131a42ed`: Kiểm toán toàn cục ELF nhị phân xác nhận 27 lệnh gọi `Conexao::registrar` và 27 opcode phân biệt 100%.
  - `aa8d357c50d54ab5`: Kiểm chứng tính phi trạng thái XOR và bộ kiểm thử biên P3 (7/7 test cases).
- **Findings mới:**
  - `35fb7ac007bc4d5b` (`VERIFIED`): Tập hợp 27 Opcode đăng ký trong `libaos_jogo.so` là hoàn chỉnh và duy nhất.
  - `a0f2a586a7764335` (`VERIFIED`): Tính chất Packet-Stateless Cryptography của mật mã ReturnSaiyan.
- **Cổng chất lượng Harness:** A0–A4 `PASS`, A5 `UNVERIFIED` (Agent receipts), A6 `REVIEW_REQUIRED`, `ready_for_review: true`.
