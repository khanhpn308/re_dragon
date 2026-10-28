# RE Dragon — kế hoạch vận hành tự động từ xa và chương trình sau Android E2E

Phiên bản kế hoạch: 2026-10-28. **Đây là đặc tả công việc, chưa phải bằng chứng tính năng đã triển khai.**

## 0. Baseline và nguyên tắc không thay đổi

- Repo local: `/home/khanh/returnsaiyan-re`.
- Project đang thực hiện: `6181397b27b247e9`, mục tiêu `RS-UH-V2-ANDROID-PLAYABILITY`.
- Tại 06:03 ngày 2026-10-28: 2/6 VERIFIED; `p3-e2e-gameplay-orchestrator` RUNNING; `p4-e2e-gameplay-action-verification`, `p5-e2e-db-persistence-audit`, `p6-final-playability-audit` PENDING.
- V2 đã nghiệm thu làm baseline bất biến: giữ ReturnSaiyan + hero tương thích từ Global theo bằng chứng; không tạo APK/ảnh chứng cứ giả; không truy cập server bên thứ ba; không thay thế thử nghiệm Android bằng mock.
- Thiết bị kiểm thử: Realme RMX3461, serial ADB `10b3139c`; Android kết nối qua **Windows ADB server** `tcp:127.0.0.1:5037` từ WSL (mirrored networking); `adb reverse tcp:30001 tcp:30001`, `tcp:30008 tcp:30008`. Hai reverse tunnel cần kiểm tra mỗi lần kết nối lại USB.
- Watchdog, Telegram và SQLite checkpoint phải nhất quán; chạy tối đa **một CLI Agent thực thi** trên cùng workspace/project; không chuyển project khi đang có turn đang chạy.
- Không lưu token, cookies, key, tài khoản thật trong log và evidence; dùng test account phù hợp.

## 1. Hoàn tất project Android E2E hiện tại — ưu tiên cao nhất

1. P3: xác minh APK ký đúng, cài trên RMX3461, khởi động; đăng nhập server Go trên localhost; tạo/chọn nhân vật; vào thế giới game; di chuyển và chiến đấu; chạy kịch bản có timestamp và screenshot Android thực sự; gắn log client, Go server và PostgreSQL tương ứng.
2. P4: kiểm tra từng hành động gameplay với kết quả server-authoritative, không chỉ UI hoặc animation; bằng chứng client ↔ Go ↔ PostgreSQL khớp nhau.
3. P5: kiểm chứng persistence qua reconnect, app restart, server restart có kiểm soát; kiểm tra dữ liệu nhân vật, inventory, quest/level nếu được triển khai; migrations và rollback.
4. P6: reviewer độc lập kiểm chứng bằng chứng, hash/ABI/signature APK, chức năng, bug regression và phạm vi kết luận; `ACCEPTED` chỉ khi tất cả task `VERIFIED` và tiêu chí nghiệm thu thực tế đạt.
5. Khi blocked do USB/quota/consent: báo rõ qua Telegram `NEEDS_USER`, không đánh dấu thành công, không nhấn nút hay giả lập bước nhạy cảm, không lặp vô hạn.

## 2. Project tiếp theo: RS-REMOTE-OPS-HARDENING — điều kiện trước chạy hàng loạt

Mục tiêu: có thể rời máy >24 giờ; sau sự cố phần mềm được phục hồi hữu hạn, giữ trạng thái, không cần ChatGPT để biết/chữa lỗi thông thường. Nghiệm thu phải dùng test gây lỗi có kiểm soát, không chỉ inspect mã nguồn.

### A. Hạ tầng Windows ↔ WSL ↔ Android
- Windows Task Scheduler khởi động lại đúng một service Watchdog và Telegram supervisor khi Windows reboot/login và WSL availability được xác minh; có lock chống duplicate; không mở nhiều `agy`.
- Windows ADB server tự khởi động ở localhost với cấu hình được phép, WSL kết nối qua `ADB_SERVER_SOCKET=tcp:127.0.0.1:5037`; kiểm tra `adb devices`, serial, authorization, ADB reverse sau disconnect/replug; tránh phụ thuộc `usbipd attach` nếu Windows ADB đã ổn định.
- Xác minh service app Go/DB có đủ listener, local ports và readiness trước Android test; TCP reverse chỉ có ý nghĩa nếu service đích hoạt động. Health checks không sử dụng tài khoản thật.
- Power/USB: Windows sleep/hibernation = off khi cắm nguồn, USB selective suspend theo kiểm thử, dây dữ liệu ổn định; phát hiện USB thực sự rút hoặc xác thực mất thì `NEEDS_USER` (không tự suy diễn là đã cắm lại được).

### B. Harness và quota/session
- Bổ sung API trạng thái cho `BLOCKED -> REWORK` bằng bằng chứng khắc phục, log/audit, reviewer policy, rollback; không update SQLite thô để bypass gate.
- Watchdog chỉ retry lỗi vận chuyển/quota hợp lệ, có exponential backoff và hạn mức; giữ checkpoint và phát Telegram event có dedupe.
- Đổi tài khoản phải là thao tác được người dùng cho phép, dùng chính thức CLI; không vượt giới hạn quota bằng cách tự động xoay hàng loạt tài khoản. Khi phiên cũ không thuộc tài khoản hiện tại, bootstrap conversation mới và ràng buộc vào project ID; giữ VERIFIED.
- Khi nguồn tài nguyên không khả dụng phải dừng an toàn. Không tự tắt chặn an toàn hoặc tạo bằng chứng giả.

### C. Telegram operations & observability
- Lệnh có mô tả: `/help`, `/status`, `/progress`, `/tasks`, `/taskdetail`, `/incidents`, `/incident`, `/report`, `/approvals`, `/pause`, `/resume`, `/projects`.
- Nâng cấp `status` gồm timestamp heartbeat, PID, pinned goal, trạng thái từng gate, ADB reachability, Go/DB health, quota, số retry; luôn nêu nguyên nhân và next action khi stop.
- Incident auto-classification: network/DNS, USB/ADB, stale lock, missing marker, quota, agent crash, review dispute; gửi thông báo Telegram có rate limit, correlation ID, digest logs redacted; các incident cũ chỉ RESOLVED khi có bằng chứng sửa tương ứng.
- Báo cáo buổi sáng một lần và báo khẩn khi `NEEDS_USER`/rủi ro dữ liệu, không spam.

### D. Kiểm thử chaos/remote readiness
- Tạo test matrix: tắt Telegram worker; chặn tạm DNS; rút/cắm USB có người giám sát; restart Windows ADB; kill Agent giữa turn; quota wait; log rotation; Windows reboot; PG/Go restart.
- PASS nếu sau các sự cố tự phục hồi được, hoặc dừng `NEEDS_USER` với chẩn đoán chính xác, **không mất checkpoint, không có 2 Agent, không tự động vượt gate**. Có log và screenshot/test report. Phân biệt lỗi recoverable và cần thao tác vật lý.

## 3. Hàng đợi dự án tiếp theo sau RemoteOps (chỉ chạy khi đã được phê duyệt trước)

| Mã | Mục tiêu | Tiêu chí tối thiểu |
|---|---|---|
| RS-GAMEPLAY-COMPLETENESS | Hoàn thiện vòng lặp gameplay Go: login/session, role, world, quest, combat, hero, inventory, progression; map resource từ ReturnSaiyan/Global theo manifest | E2E Android, server-authoritative, lưu DB và reviewer độc lập |
| RS-DB-PERFORMANCE | PostgreSQL schema/index, pool, transactions, WAL/backup, hot path, contention, reconnect/resume | Benchmark nhiều tải có SLO đã thống nhất, metrics p50/p95/p99, explain analyze, backup/restore/rollback |
| RS-SECURITY-RELEASE | Authentication/session, API boundaries, secure config, build reproducibility, Android signing, offline updates, schema migration strategy | Pen-test theo phạm vi cho phép, SBOM/hash, release candidate GO/NO-GO, rollback drills |
| RS-SOAK-RESILIENCE | Thử nghiệm dài hạn với tải mô phỏng, disconnect Android/reconnect và server restart | Soak/chaos logs, no data loss, no false ACCEPTED, incident history |
| RS-RELEASE-AUDIT | End-to-end acceptance độc lập, checklist tài nguyên/tác quyền, package manifest, installer/signing và tài liệu vận hành | APK + logs/screenshots thực, independent reviewer, GO/NO-GO rõ ràng |

Không cam kết sức tải hoặc độ trễ tuyệt đối trước khi đo. Không đụng dịch vụ hoặc máy chủ bên thứ ba không được phép.

## 4. Thiết kế `Approved Goal Queue` — hiện CHƯA có trong Harness

Code hiện tại cho `/newgoal`: yêu cầu Confirm trong 10 phút, project create/switch từ chối khi Watchdog lock hoặc Agent đang chạy; `/task`: chuyển mô tả cho project đang pinned, không phải multi-project scheduling. Do đó **không thể mặc nhiên gửi 5 `/newgoal` và kỳ vọng chúng tự chạy nối tiếp**.

Implement sau khi review:
- Lưu `approved_goal_queue` riêng, có `goal_id`, `goal`, acceptance, dependencies, order, max_cost/time, reviewer, state, preapproved_by, created_at`, audit & immutable manifest digest.
- Người dùng có thể *duyệt trước một lần toàn bộ danh sách* qua Telegram; phê duyệt không bao gồm bypass quyền hệ thống, third-party access, phát hành production, tiêu dữ liệu hoặc cài đặt không thể đảo ngược.
- Chỉ auto-activate goal kế tiếp khi goal trước là `ACCEPTED`, `actual_completion()` true, không có Agent turn, không còn process lock; kiểm tra config/credential và resource budgets. Nếu `NEEDS_USER` phải dừng queue và thông báo rõ.
- Chống duplicate và double execution qua durable queue lease, transaction atomic, crash replay safe; không tự đổi pinned project nếu không có approved queue entry.
- Khi project completed, push Telegram report + evidence locations + next approved goal; báo rõ khi dừng vì no preapproval.
- Hàng đợi riêng cho tác vụ maintenance được duyệt trước, không can thiệp vòng acceptance bất biến.

## 5. Gate để người dùng có thể rời máy

- **REMOTE-READY = PASS** nếu: (a) Windows→WSL→Agent→Telegram recovery sau reboot; (b) ADB serial, authorization và 2 reverse tunnel verify; (c) HTTPS Telegram và CLI auth/usage thực tế; (d) task/checkpoint/incident saved; (e) rollback and bounded retry tested; (f) alerts Telegram delivered; (g) one-agent invariant tested; (h) không có yêu cầu nhập tay đang chờ.
- **BATCH-READY = PASS** nếu: REMOTE-READY, Approved Goal Queue implemented and tested, toàn bộ goal đã được phê duyệt trong phạm vi, kiểm soát stop/abort qua Telegram, dependencies & resource budgets validated.
- Trước hai gate này, chỉ có thể chạy unattended **một project** đang pinned; không hứa auto-chaining hoặc khôi phục mọi lỗi vật lý.

## 6. Hành động hiện tại

1. Để project `6181397b27b247e9` hoàn thành các task P3–P6; không tạo newgoal khi nó vẫn ACTIVE.
2. Giao một `/task` ngắn dưới 900 ký tự cho **cùng project** để chuẩn bị read-only readiness dossier và đề xuất project RemoteOps kế tiếp; không sửa acceptance của project hiện tại.
3. Khi project `ACCEPTED`, thông qua `/newgoal` với xác nhận Telegram để bắt đầu RS-REMOTE-OPS-HARDENING.
4. Sau khi RemoteOps BATCH-READY, nạp và phê duyệt hàng đợi từ mục 3 và chạy theo dependency graph.

> Mục tiêu của tài liệu là tránh các thao tác lặp thủ công. Không tuyên bố hoàn thành khi chỉ mới tạo tmux session hoặc khi chỉ có status RUNNING.

## 7. Mẫu lệnh Telegram dùng về sau (KHÔNG gửi khi E2E còn ACTIVE)

```text
/newgoal RS-REMOTE-OPS-HARDENING: Make ReturnSaiyan harness operate for 24h unattended with Windows/WSL auto-restart, persistent Windows ADB bridge, bounded recovery, incident telemetry and a preapproved sequential goal queue. Read docs/production/RE_DRAGON_REMOTE_AUTONOMY_MASTER_PLAN.md. Do not change ACCEPTED V2 or past evidence. | 24h unattended chaos-test PASS; durable checkpoint; one Agent; Windows ADB RMX3461 and 30001/30008 validated; Telegram incident alerts; authorized goal queue and rollback verified; no false VERIFIED, no bypass of reviewer or quota.
```

Bot sẽ gửi nút Confirm, chỉ nhấn sau khi project Android E2E đạt ACCEPTED, phiên Agent đã kết thúc và không có Watchdog lock. Nếu `Cannot prepare confirmation` hoặc `Watchdog is active`, không retry liên tục; kiểm tra `/status`, `/projects`, `/approvals` và thực hiện controlled drain theo runbook đã nghiệm thu.

Các lệnh vận hành từ xa đã có: `/status`, `/progress`, `/tasks`, `/incidents`, `/report`, `/approvals`, `/pause`, `/resume`, `/projects`, `/taskdetail <task-key>`, `/incident <id>` và `/help`. Đây không phải phép truy cập shell từ Telegram. Mọi yêu cầu thay đổi mức độ bảo mật/triển khai không thể đảo ngược vẫn cần approval riêng.
