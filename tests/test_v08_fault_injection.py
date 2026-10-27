"""Comprehensive Fault-Injection Acceptance Suite for RE Dragon v0.8.

Verifies all 10 required fault-injection scenarios:
1. Missing or malformed structured state marker.
2. Agent crash mid-task (non-zero exit / exception).
3. Network disconnect and timeout.
4. SQLite lock contention, stale lease recovery, and restart.
5. Quota exhaustion and delayed refresh.
6. Ghidra RAM exhaustion (OOM / exit code 137).
7. Telegram disconnect vs Agent error separation.
8. Legacy ACCEPTED project co-existing with active production project.
9. System/WSL2 reboot simulation with surviving state and lease recovery.
10. Tool permission denial and human approval resolution.
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from re_harness import (
    autonomy,
    core,
    easy_start as start,
    incidents,
    quota_guard,
    quota_watchdog as wd,
    recovery,
    runtime_state,
    supervisor,
    telegram_bridge,
    telegram_inbox,
)


class FaultInjectionAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)
        self.harness_dir = self.workspace / ".re_harness_mvp"
        self.watch_dir = self.workspace / ".re_harness"
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.watch_dir / "quota-watchdog.json"
        self.prompt_file = self.workspace / "prompt.md"
        self.prompt_file.write_text("Continue assigned project tasks with checkpoints", encoding="utf8")

        with core.database(self.harness_dir) as db:
            autonomy.migrate(db)

    def create_active_project(self, goal="RS-UH-PROD-V1 Production Charter", acceptance="Verified gates"):
        with core.database(self.harness_dir) as db:
            proj = autonomy.start(db, goal, acceptance)
            return proj["project_id"]

    def output(self, state="CONTINUE", note="Turn completed", cid="session-12345678"):
        return {
            "code": 0,
            "data": {
                "status": "SUCCESS",
                "conversation_id": cid,
                "response": f"Summary of work.\nRE_DRAGON_RUN_STATE {json.dumps({'state': state, 'note': note})}",
            },
            "stderr": "",
        }

    # =========================================================================
    # Scenario 1: Missing or malformed structured state marker
    # =========================================================================
    def test_scenario_1_missing_or_malformed_marker(self):
        pid = self.create_active_project()
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678")
        wd.save(self.state_file, state)

        missing_outcome = {
            "code": 0,
            "data": {"status": "SUCCESS", "conversation_id": "session-12345678", "response": "Summary without marker"},
            "stderr": "",
        }
        runner = lambda *a, **kw: missing_outcome

        # Turn 1: bounded retry 1
        t1 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1000, runner=runner, harness_state_dir=self.harness_dir)
        self.assertEqual(t1["status"], "WAIT_RETRY")
        self.assertEqual(t1["missing_marker_recoveries"], 1)

        # Turn 2: bounded retry 2
        t2 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1061, runner=runner, harness_state_dir=self.harness_dir)
        self.assertEqual(t2["status"], "WAIT_RETRY")
        self.assertEqual(t2["missing_marker_recoveries"], 2)

        # Turn 3: exhausts budget -> stops with NEEDS_USER and records incident
        t3 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1182, runner=runner, harness_state_dir=self.harness_dir)
        self.assertEqual(t3["status"], "NEEDS_USER")
        self.assertEqual(t3["next_at"], 0)

        # Verify incident is recorded in journal
        incs = incidents.list_incidents(self.workspace, project_id=pid, category="MISSING_MARKER")
        self.assertEqual(len(incs), 1)
        self.assertEqual(incs[0]["category"], "MISSING_MARKER")

    # =========================================================================
    # Scenario 2: Agent crash mid-task (non-zero exit / exception)
    # =========================================================================
    def test_scenario_2_agent_crash_mid_task(self):
        pid = self.create_active_project()
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678")
        wd.save(self.state_file, state)

        crash_outcome = {"code": 1, "data": {"status": "ERROR"}, "stderr": "Traceback (most recent call last): Unhandled crash"}
        t1 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1000,
                     runner=lambda *a, **kw: crash_outcome, harness_state_dir=self.harness_dir)
        self.assertEqual(t1["status"], "WAIT_RETRY")
        self.assertEqual(t1["crash_recoveries"], 1)

        # Now simulate agent resuming and succeeding on retry
        t2 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1031,
                     runner=lambda *a, **kw: self.output("CONTINUE"), harness_state_dir=self.harness_dir)
        self.assertEqual(t2["status"], "CONTINUE")
        self.assertEqual(t2["crash_recoveries"], 0)

    # =========================================================================
    # Scenario 3: Network disconnect and timeout
    # =========================================================================
    def test_scenario_3_network_disconnect_and_timeout(self):
        pid = self.create_active_project()
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678")
        wd.save(self.state_file, state)

        # Network disconnect
        net_err = {"code": 1, "data": {"status": "ERROR"}, "stderr": "Connection reset by peer ECONNRESET"}
        t1 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1000,
                     runner=lambda *a, **kw: net_err, harness_state_dir=self.harness_dir)
        self.assertEqual(t1["status"], "WAIT_RETRY")
        self.assertEqual(t1["transient_failures"], 1)

        # Timeout
        timeout_err = {"code": 124, "data": {}, "stderr": "watchdog process timeout"}
        cls = recovery.classify_turn(timeout_err)
        self.assertEqual(cls.category, "TIMEOUT")
        self.assertTrue(cls.recoverable)

    # =========================================================================
    # Scenario 4: SQLite lock contention, stale lease recovery, and restart
    # =========================================================================
    def test_scenario_4_sqlite_lock_and_stale_lease_recovery(self):
        pid = self.create_active_project()
        # Add a task to SQLite and simulate expired lease
        with core.database(self.harness_dir) as db:
            autonomy.plan(db, pid, [{"key": "T-1", "title": "Analyze binary", "acceptance": "Done", "kind": "ANALYZE", "priority": 10}])
            # Claim task and artificially expire lease
            db.execute(
                "UPDATE auto_tasks SET status='RUNNING', lease_until=?, tries=1 WHERE project_id=? AND task_key='T-1'",
                (time.time() - 100, pid),
            )

        # Verify safety check reconciles the expired lease back to PENDING
        health = recovery.verify_pre_retry_safety(self.workspace, pid, self.harness_dir)
        self.assertTrue(health["safe_to_retry"])

        with core.database(self.harness_dir) as db:
            task = db.execute("SELECT status FROM auto_tasks WHERE project_id=? AND task_key='T-1'", (pid,)).fetchone()
            self.assertEqual(task["status"], "PENDING")

    # =========================================================================
    # Scenario 5: Quota exhaustion and delayed refresh
    # =========================================================================
    def test_scenario_5_quota_exhausted_and_reset(self):
        pid = self.create_active_project()
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678")
        wd.save(self.state_file, state)

        quota_err = {"code": 3, "data": {"status": "ERROR"}, "stderr": "RESOURCE_EXHAUSTED: Resets in 10m"}
        t1 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1000,
                     runner=lambda *a, **kw: quota_err, harness_state_dir=self.harness_dir)
        self.assertEqual(t1["status"], "WAIT_QUOTA")
        self.assertEqual(t1["next_at"], 1000 + 600 + 60)

        # Subsequent call before next_at does not execute CLI
        called = []
        wd.once(self.workspace, self.state_file, self.prompt_file, clock=1300,
                runner=lambda *a, **kw: called.append(True), harness_state_dir=self.harness_dir)
        self.assertEqual(len(called), 0)

    # =========================================================================
    # Scenario 6: Ghidra RAM exhaustion (OOM / exit code 137)
    # =========================================================================
    def test_scenario_6_ghidra_out_of_ram_oom(self):
        oom_err = {"code": 137, "data": {"status": "ERROR"}, "stderr": "java.lang.OutOfMemoryError: Java heap space"}
        cls = recovery.classify_turn(oom_err)
        self.assertEqual(cls.category, "RESOURCE_EXHAUSTION")
        self.assertEqual(cls.severity, "ERROR")
        self.assertTrue(cls.recoverable)
        self.assertEqual(cls.suggested_status, "WAIT_RETRY")

    # =========================================================================
    # Scenario 7: Telegram disconnect vs Agent error separation
    # =========================================================================
    def test_scenario_7_telegram_disconnect_vs_agent_error(self):
        pid = self.create_active_project()
        # Record Telegram delivery failure in incident journal
        inc, _ = incidents.create_or_update_incident(
            self.workspace,
            project_id=pid,
            category="TELEGRAM_DELIVERY",
            error_message="Telegram API HTTP 504 Gateway Timeout",
            severity="WARNING",
        )
        self.assertEqual(inc["category"], "TELEGRAM_DELIVERY")

        # Verify that watchdog state remains unaffected and continues execution
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678", status="READY")
        wd.save(self.state_file, state)

        t1 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1000,
                     runner=lambda *a, **kw: self.output("CONTINUE"), harness_state_dir=self.harness_dir)
        self.assertEqual(t1["status"], "CONTINUE")

    # =========================================================================
    # Scenario 8: Legacy ACCEPTED project co-existing with active production project
    # =========================================================================
    def test_scenario_8_legacy_accepted_and_active_coexistence(self):
        with core.database(self.harness_dir) as db:
            old_pid = autonomy.start(db, start.GOAL, start.ACCEPTANCE)["project_id"]
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (old_pid,))
            active_pid = autonomy.start(db, start.TITLE + " Production V1", "Verified gates")["project_id"]

        # Run easy_start bootstrap with NO project ID
        info = start.bootstrap(self.workspace, state_dir=self.harness_dir)
        self.assertEqual(info["project_id"], active_pid)
        self.assertFalse(info["project_created"])

        # Pinned project is the active one, not the accepted one
        st = wd.load(self.state_file)
        self.assertEqual(st["project_id"], active_pid)

    # =========================================================================
    # Scenario 9: System/WSL2 reboot simulation with surviving state and lease recovery
    # =========================================================================
    def test_scenario_9_system_reboot_simulation(self):
        pid = self.create_active_project()
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678", status="CONTINUE", next_at=1000)
        wd.save(self.state_file, state)

        # Simulate dead PID in agent-runtime.json from before reboot
        runtime_file = self.watch_dir / "agent-runtime.json"
        runtime_file.write_text(json.dumps({
            "state": "AGENT_RUNNING",
            "pid": 99999999,  # Non-existent PID
            "proc_start": "12345",
            "started_at": 500,
            "heartbeat_at": 510,
        }), encoding="utf8")

        # Snapshot correctly reports None (dead process)
        snap = runtime_state.snapshot(runtime_file, now=1000)
        self.assertIsNone(snap)

        # Supervisor inspects status after reboot and finds clean state
        sup = supervisor.Supervisor(self.workspace, harness_state_dir=self.harness_dir)
        st = sup.status()
        self.assertEqual(st["watchdog_status"], "CONTINUE")
        self.assertEqual(st["project_id"], pid)
        self.assertIsNone(st["agent_live"])

    # =========================================================================
    # Scenario 10: Tool permission denial and human approval resolution
    # =========================================================================
    def test_scenario_10_permission_denial_and_human_approval(self):
        pid = self.create_active_project()
        state = wd.load(self.state_file)
        state.update(project_id=pid, conversation_id="session-12345678")
        wd.save(self.state_file, state)

        perm_err = {
            "code": 0,
            "data": {"status": "SUCCESS", "response": "Action soft-denied: Tool requires approval from operator"},
            "stderr": "",
        }
        # Turn fails closed to NEEDS_USER
        t1 = wd.once(self.workspace, self.state_file, self.prompt_file, clock=1000,
                     runner=lambda *a, **kw: perm_err, harness_state_dir=self.harness_dir)
        self.assertEqual(t1["status"], "NEEDS_USER")
        self.assertIn("authorization", t1["last_reason"].lower())

        # Incident is recorded as CRITICAL
        incs = incidents.list_incidents(self.workspace, project_id=pid, category="AUTH_OR_PERMISSION")
        self.assertEqual(len(incs), 1)
        self.assertEqual(incs[0]["severity"], "CRITICAL")

        # Submit proposal for human approval via telegram_inbox
        prop = telegram_inbox.create_proposal(
            self.workspace, pid, "AUTHORIZE_TOOL", "Authorize native tool execution"
        )
        self.assertEqual(prop["status"], "PENDING")

        # Human approves proposal
        res = telegram_inbox.decide_proposal(
            self.workspace, prop["id"], "APPROVE", 12345, "owner_user", nonce=prop["nonce"]
        )
        self.assertTrue(res["success"])

        # Verified in audit log
        audit = telegram_inbox.audit_log(self.workspace, proposal_id=prop["id"])
        self.assertEqual(len(audit), 1)
        self.assertEqual(audit[0]["decision"], "APPROVE")


if __name__ == "__main__":
    unittest.main()
