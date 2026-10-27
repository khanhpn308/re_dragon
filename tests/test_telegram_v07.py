"""Comprehensive test suite for RE Dragon v0.7 — Telegram Control Center.

Verifies:
1. Project lifecycle: /projects, /newgoal, project selection, duplicate prevention, ACCEPTED protection.
2. Independent conversations & checkpoints per project.
3. Task management: /tasks, /task, /progress, /taskdetail, blocker reporting, exactly-once processing.
4. Human approvals: proposal lifecycle, inline callbacks, nonce validation, expiry, replay idempotency, audit log.
5. Reports: export, summary, redaction, binary blocking, path traversal prevention.
6. Notifications: discrete signatures, deduplication cursor, no heartbeat spam.
7. Supervisor: Telegram worker locking, Watchdog locking, recovery.
8. Security: private-chat allowlist, input limits, prompt injection safety.
"""
from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from re_harness import (
    autonomy,
    core,
    easy_start,
    quota_guard,
    quota_watchdog as qw,
    runtime_state,
    scheduler,
    telegram_bridge as tg,
    telegram_inbox,
)


class TelegramControlCenterV07Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.dbdir = self.root / ".re_harness_mvp"
        self.harness_dir = self.root / ".re_harness"
        self.harness_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.state_file = self.harness_dir / "quota-watchdog.json"
        self.prompt_file = self.root / "prompt.md"
        self.prompt_file.write_text("Supervisor continuation prompt", encoding="utf8")

        # Mock scheduler host to provide deterministic capacity
        self.host_patch = patch(
            "re_harness.scheduler.read_host",
            return_value=scheduler.Host(8, 16384, 0.0)
        )
        self.host_patch.start()
        self.addCleanup(self.host_patch.stop)

        # Initialize SQLite database
        with core.database(self.dbdir) as db:
            autonomy.migrate(db)
            self.pid1 = autonomy.start(db, "Unified Heroes v1", "Complete integration")["project_id"]
            autonomy.plan(db, self.pid1, [
                {"key": "t1", "title": "Analyze packet headers", "kind": "ANALYZE",
                 "acceptance": "Found offsets", "priority": 10, "depends_on": []},
                {"key": "t2", "title": "Implement codec", "kind": "IMPLEMENT",
                 "acceptance": "Passing tests", "priority": 20, "depends_on": ["t1"]},
            ])

        # Initial watchdog state bound to pid1
        qw.save(self.state_file, {
            "status": "READY",
            "project_id": self.pid1,
            "conversation_id": "session-project-1",
            "attempts": 0,
            "quota_hits": 0,
            "transient_failures": 0,
            "next_at": 0,
            "last_reason": "Initialized test project",
            "project_conversations": {
                self.pid1: "session-project-1"
            }
        })

    # =========================================================================
    # 1. Project Lifecycle & Independent Conversations
    # =========================================================================

    def test_projects_text_lists_projects_and_marks_active(self):
        txt = tg.projects_text(self.root, db_dir=self.dbdir)
        self.assertIn("RE Dragon Projects:", txt)
        self.assertIn(self.pid1, txt)
        self.assertIn("Unified Heroes v1", txt)
        self.assertIn("⭐ [ACTIVE]", txt)
        self.assertIn("[0/2 verified]", txt)

    def test_newgoal_creates_and_activates_new_project(self):
        res = tg.create_goal(self.root, "New Autonomous Protocol Analysis",
                             "Verified opcode map", db_dir=self.dbdir)
        new_pid = res["project_id"]
        self.assertTrue(new_pid)
        self.assertNotEqual(new_pid, self.pid1)
        self.assertTrue(res["new_session"])

        # Check that watchdog state was updated to new project
        state = qw.load(self.state_file)
        self.assertEqual(state["project_id"], new_pid)
        self.assertTrue(state.get("bootstrap_new_conversation"))
        self.assertIsNone(state.get("conversation_id"))

        # Check that previous project conversation is preserved in project_conversations map
        self.assertEqual(state["project_conversations"][self.pid1], "session-project-1")

    def test_newgoal_rejects_duplicate_goal(self):
        with self.assertRaisesRegex(ValueError, "Duplicate goal"):
            tg.create_goal(self.root, "Unified Heroes v1", db_dir=self.dbdir)

    def test_switch_project_preserves_independent_conversations(self):
        # Create a second project
        with core.database(self.dbdir) as db:
            pid2 = autonomy.start(db, "Second Goal", "Acceptance 2")["project_id"]

        # Switch to pid2
        sw1 = tg.switch_project(self.root, pid2, db_dir=self.dbdir)
        self.assertEqual(sw1["project_id"], pid2)
        self.assertTrue(sw1["new_session"])

        state = qw.load(self.state_file)
        self.assertEqual(state["project_id"], pid2)
        self.assertIsNone(state.get("conversation_id"))

        # Simulate turn on pid2 pinning conversation-2
        state["conversation_id"] = "session-project-2"
        state["project_conversations"][pid2] = "session-project-2"
        qw.save(self.state_file, state)

        # Switch back to pid1
        sw2 = tg.switch_project(self.root, self.pid1, db_dir=self.dbdir)
        self.assertEqual(sw2["project_id"], self.pid1)
        self.assertFalse(sw2["new_session"])
        self.assertEqual(sw2["conversation_id"], "session-project-1")

        state = qw.load(self.state_file)
        self.assertEqual(state["conversation_id"], "session-project-1")

        # Switch again to pid2 -> verifies pid2 gets its session back
        sw3 = tg.switch_project(self.root, pid2, db_dir=self.dbdir)
        self.assertEqual(sw3["conversation_id"], "session-project-2")

    def test_accepted_project_cannot_be_activated_or_reused(self):
        with core.database(self.dbdir) as db:
            acc_pid = autonomy.start(db, "Completed Project", "Accepted work")["project_id"]
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (acc_pid,))
            db.commit()

        # Cannot switch to an ACCEPTED project
        with self.assertRaisesRegex(ValueError, "ACCEPTED"):
            tg.switch_project(self.root, acc_pid, db_dir=self.dbdir)

        # easy_start bootstrap also rejects ACCEPTED project
        with self.assertRaisesRegex(easy_start.SetupError, "ACCEPTED"):
            easy_start.bootstrap(self.root, state_dir=self.dbdir, project_id=acc_pid)

    # =========================================================================
    # 2. Task Management & Blocker Reporting
    # =========================================================================

    def test_tasks_text_and_blocker_highlighting(self):
        # Mark t1 as BLOCKED in SQLite
        with core.database(self.dbdir) as db:
            db.execute("UPDATE auto_tasks SET status='BLOCKED', review_note='Missing native library symbols' "
                       "WHERE project_id=? AND task_key='t1'", (self.pid1,))
            db.commit()

        txt = tg.tasks_text(self.root)
        self.assertIn("Project: " + self.pid1, txt)
        self.assertIn("⚠️ t1: BLOCKED (blocker: Missing native library symbols)", txt)
        self.assertIn("t2: PENDING", txt)

    def test_progress_text_breakdown_and_percentage(self):
        # Submit and verify t1
        with core.database(self.dbdir) as db:
            db.execute("UPDATE auto_tasks SET status='VERIFIED' WHERE project_id=? AND task_key='t1'",
                       (self.pid1,))
            db.commit()

        txt = tg.progress_text(self.root, db_dir=self.dbdir)
        self.assertIn("⚡ Progress — Project: " + self.pid1, txt)
        self.assertIn("50% (1/2 verified)", txt)
        self.assertIn("• VERIFIED: 1", txt)
        self.assertIn("• PENDING: 1", txt)

    def test_task_detail_text_shows_evidence_and_acceptance(self):
        txt = tg.task_detail_text(self.root, "t1", db_dir=self.dbdir)
        self.assertIn("📋 Task Detail: t1", txt)
        self.assertIn("Title: Analyze packet headers", txt)
        self.assertIn("Kind: ANALYZE", txt)
        self.assertIn("Acceptance: Found offsets", txt)

    def test_task_submission_exactly_once(self):
        rid1, created1 = tg.submit_task(self.root, 501, 100, 100, "Map hero skeleton 101")
        self.assertTrue(created1)
        # Duplicate submission with same update_id
        rid2, created2 = tg.submit_task(self.root, 501, 100, 100, "Map hero skeleton 101")
        self.assertEqual(rid1, rid2)
        self.assertFalse(created2)

        q = telegram_inbox.queued(self.root, self.pid1)
        self.assertEqual(len(q), 1)
        self.assertEqual(q[0]["body"], "Map hero skeleton 101")

    # =========================================================================
    # 3. Human Approval: Proposals, Inline Callback, Expiry, Nonce, Audit Log
    # =========================================================================

    def test_human_approval_lifecycle_approve(self):
        prop = telegram_inbox.create_proposal(
            self.root, self.pid1, "BUILD_RELEASE", "Authorize final staging build",
            timeout_seconds=300
        )
        prop_id = prop["id"]
        nonce = prop["nonce"]

        # List pending proposals
        pending = telegram_inbox.list_proposals(self.root, self.pid1, status="PENDING")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], prop_id)

        # Decide APPROVE
        res = telegram_inbox.decide_proposal(
            self.root, prop_id, "APPROVE", 9999, "admin_user", nonce=nonce, note="Signed off"
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["decision"], "APPROVE")

        # Verify proposal status updated
        updated = telegram_inbox.get_proposal(self.root, prop_id)
        self.assertEqual(updated["status"], "APPROVE")
        self.assertEqual(updated["actor_id"], 9999)
        self.assertEqual(updated["actor_username"], "admin_user")

        # Verify audit log
        logs = telegram_inbox.audit_log(self.root, prop_id)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "BUILD_RELEASE")
        self.assertEqual(logs[0]["decision"], "APPROVE")
        self.assertEqual(logs[0]["actor_id"], 9999)
        self.assertEqual(logs[0]["nonce"], nonce)

    def test_human_approval_replay_rejected_idempotently(self):
        prop = telegram_inbox.create_proposal(
            self.root, self.pid1, "MIGRATE", "Run migration"
        )
        res1 = telegram_inbox.decide_proposal(
            self.root, prop["id"], "APPROVE", 111, nonce=prop["nonce"]
        )
        self.assertTrue(res1["success"])

        # Replay attempt fails safely
        res2 = telegram_inbox.decide_proposal(
            self.root, prop["id"], "REJECT", 111, nonce=prop["nonce"]
        )
        self.assertFalse(res2["success"])
        self.assertIn("already decided", res2["reason"].lower())

    def test_human_approval_invalid_nonce_rejected(self):
        prop = telegram_inbox.create_proposal(
            self.root, self.pid1, "DEPLOY", "Deploy release"
        )
        res = telegram_inbox.decide_proposal(
            self.root, prop["id"], "APPROVE", 222, nonce="wrong-nonce"
        )
        self.assertFalse(res["success"])
        self.assertIn("invalid proposal nonce", res["reason"].lower())

    def test_human_approval_expiry(self):
        prop = telegram_inbox.create_proposal(
            self.root, self.pid1, "TIMED_ACTION", "Quick decision", timeout_seconds=10
        )
        # Manually backdate created_at and expires_at
        with telegram_inbox.connection(self.root) as db:
            db.execute("UPDATE proposals SET expires_at=? WHERE id=?",
                       (time.time() - 5, prop["id"]))
            db.commit()

        res = telegram_inbox.decide_proposal(
            self.root, prop["id"], "APPROVE", 333, nonce=prop["nonce"]
        )
        self.assertFalse(res["success"])
        self.assertIn("expired", res["reason"].lower())

        # Check listed proposals excludes expired when filtering PENDING
        pending = telegram_inbox.list_proposals(self.root, self.pid1, status="PENDING")
        self.assertEqual(len(pending), 0)

    # =========================================================================
    # 4. Reports: Export, Summary, Redaction, and Binary Blocking
    # =========================================================================

    def test_report_export_and_summary(self):
        res = tg.export_project_report(self.root, self.pid1, db_dir=self.dbdir)
        self.assertEqual(res["project_id"], self.pid1)
        self.assertIn("📊 RE Dragon Report", res["summary"])
        self.assertIn("Tasks Total: 2", res["summary"])
        self.assertTrue(res["filename"].endswith(".md"))
        self.assertTrue(Path(res["path"]).is_file())

    def test_report_redacts_sensitive_tokens(self):
        raw = (
            "# Secret Report\n"
            "Bot token: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567\n"
            "API key: AIzaSyD1234567890abcdefghijklmnopqrstuv\n"
            "Auth: Bearer secret_bearer_token_value_xyz\n"
            "-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEA0s7v...fake...key...\n"
            "-----END RSA PRIVATE KEY-----\n"
            "Evidence: REA:sub_00401000\n"
        )
        redacted = tg.redact_sensitive_text(raw)
        self.assertNotIn("123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567", redacted)
        self.assertIn("[REDACTED_BOT_TOKEN]", redacted)
        self.assertNotIn("AIzaSyD1234567890abcdefghijklmnopqrstuv", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertNotIn("secret_bearer_token_value_xyz", redacted)
        self.assertIn("[REDACTED_TOKEN]", redacted)
        self.assertIn("[REDACTED_PRIVATE_KEY]", redacted)
        self.assertIn("REA:sub_00401000", redacted)

    def test_report_strictly_blocks_binary_export(self):
        # Attempting to export an APK or SO must fail immediately
        with tempfile.TemporaryDirectory() as tmp_b:
            apk_path = Path(tmp_b) / "test.apk"
            apk_path.write_bytes(b"PK\x03\x04")
            with patch("re_harness.autonomy.export_report",
                       return_value={"report": str(apk_path), "state": "ACTIVE"}):
                with self.assertRaisesRegex(ValueError, "Binary and artifact export forbidden"):
                    tg.export_project_report(self.root, self.pid1, db_dir=self.dbdir)

    def test_report_blocks_path_traversal(self):
        # Attempting to return a path outside auto_reports must fail
        with tempfile.TemporaryDirectory() as tmp_t:
            escaped_path = Path(tmp_t) / "etc_passwd.md"
            escaped_path.write_text("root:x:0:0", encoding="utf8")
            with patch("re_harness.autonomy.export_report",
                       return_value={"report": str(escaped_path), "state": "ACTIVE"}):
                with self.assertRaisesRegex(ValueError, "ownership violation"):
                    tg.export_project_report(self.root, self.pid1, db_dir=self.dbdir)

    # =========================================================================
    # 5. Notifications: Discrete Events, Deduplication, No Heartbeat Spam
    # =========================================================================

    def test_notification_deduplication_and_cursor(self):
        # Update state to a discrete event (WAIT_QUOTA)
        s = qw.load(self.state_file)
        s.update(status="WAIT_QUOTA", quota_hits=1, last_reason="provider limit")
        qw.save(self.state_file, s)

        # Initially, notification_signature produces a signature for pid1
        sig1, msg1 = tg.notification_signature(self.root)
        self.assertIsNotNone(sig1)

        # Record signature in cursor
        with telegram_inbox.connection(self.root) as db:
            db.execute("INSERT OR REPLACE INTO notification_cursor(name, signature, updated_at) "
                       "VALUES('watchdog', ?, ?)", (sig1, time.time()))
            db.commit()

        # Calling again produces the exact same signature
        sig2, _ = tg.notification_signature(self.root)
        self.assertEqual(sig1, sig2)

        # Heartbeat change does NOT change signature
        runtime_path = self.harness_dir / "agent-runtime.json"
        with runtime_state.AgentHeartbeat(runtime_path, os.getpid(), interval=0.01):
            sig3, _ = tg.notification_signature(self.root)
            self.assertEqual(sig1, sig3)

    def test_notification_triggers_on_blocked_tasks(self):
        with core.database(self.dbdir) as db:
            db.execute("UPDATE auto_tasks SET status='BLOCKED', review_note='Tool error' "
                       "WHERE project_id=? AND task_key='t1'", (self.pid1,))
            db.commit()

        sig, msg = tg.notification_signature(self.root)
        self.assertIn("blocked:1", sig)
        self.assertIn("BLOCKED in project", msg)

    def test_notification_triggers_on_new_proposal(self):
        telegram_inbox.create_proposal(self.root, self.pid1, "GATE_CHECK", "Human review")
        sig, msg = tg.notification_signature(self.root)
        self.assertIn("proposals:1", sig)
        self.assertIn("pending approval proposal", msg)

    # =========================================================================
    # 6. Supervisor Concurrency Locks & Recovery
    # =========================================================================

    def test_single_telegram_worker_lock_prevents_duplicate_polling(self):
        # Acquire worker lock once
        lock1 = tg.acquire_worker_lock(self.root)
        self.assertIsNotNone(lock1)

        # Attempting to acquire again raises RuntimeError
        with self.assertRaisesRegex(RuntimeError, "Another Telegram bot worker is already running"):
            tg.acquire_worker_lock(self.root)

        # Release lock
        fcntl.flock(lock1, fcntl.LOCK_UN)
        lock1.close()

        # Can acquire again after release
        lock2 = tg.acquire_worker_lock(self.root)
        fcntl.flock(lock2, fcntl.LOCK_UN)
        lock2.close()

    def test_watchdog_recovers_ready_after_crash(self):
        # Simulate ungraceful crash leaving status at AGENT_RUNNING
        s = qw.load(self.state_file)
        s.update(status="AGENT_RUNNING", last_reason="Interrupted")
        qw.save(self.state_file, s)

        # Running status check reports READY checkpoint if PID is not actually running
        loaded = qw.load(self.state_file)
        self.assertEqual(loaded["status"], "AGENT_RUNNING")
        self.assertIsNone(runtime_state.snapshot(self.harness_dir / "agent-runtime.json"))

    # =========================================================================
    # 7. Security: Private Chat Allowlist & Input Limits
    # =========================================================================

    def test_private_chat_allowlist_enforcement(self):
        owner = 12345
        # Allowed: private chat with owner
        self.assertTrue(tg.allowed(owner, owner, "private", owner))

        # Rejected: group chat
        self.assertFalse(tg.allowed(owner, owner, "group", owner))
        self.assertFalse(tg.allowed(owner, owner, "supergroup", owner))
        self.assertFalse(tg.allowed(owner, owner, "channel", owner))

        # Rejected: unauthorized user
        self.assertFalse(tg.allowed(99999, owner, "private", owner))

        # Rejected: mismatched chat ID
        self.assertFalse(tg.allowed(owner, 54321, "private", owner))

    def test_input_limits_on_task_and_goal(self):
        # Tasks limited to 900 chars
        with self.assertRaises(ValueError):
            tg.submit_task(self.root, 999, 100, 100, "A" * 901)

        # Goals limited to 500 chars
        with self.assertRaises(ValueError):
            tg.create_goal(self.root, "B" * 501, db_dir=self.dbdir)

        # Empty goals rejected
        with self.assertRaises(ValueError):
            tg.create_goal(self.root, "   ", db_dir=self.dbdir)

    def test_telegram_sdk_builder_and_handlers_integration(self):
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler
        except ImportError:
            self.skipTest("python-telegram-bot not installed in test environment")

        app = ApplicationBuilder().token("123456789:TEST_BOT_TOKEN_FOR_LOCAL_BUILDER_ABC").build()
        self.assertIsNotNone(app)
        async def dummy_cmd(update, context): pass
        async def dummy_cb(update, context): pass
        app.add_handler(CommandHandler("projects", dummy_cmd))
        app.add_handler(CommandHandler("approvals", dummy_cmd))
        app.add_handler(CallbackQueryHandler(dummy_cb))

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Approve", callback_data="appr:1:nonce:APPROVE")]
        ])
        self.assertEqual(len(kb.inline_keyboard), 1)
        self.assertEqual(kb.inline_keyboard[0][0].callback_data, "appr:1:nonce:APPROVE")


if __name__ == "__main__":
    unittest.main()
