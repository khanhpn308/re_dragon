"""Read-only project audit tests with local temporary SQLite checkpoints."""
import json
import tempfile
import unittest
from pathlib import Path

from re_harness import autonomy, core, project_audit


class ProjectAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".re_harness").mkdir()
        self.dbdir = self.root / ".re_harness_mvp"

    def seed(self):
        with core.database(self.dbdir) as db:
            autonomy.migrate(db)
            pid = autonomy.start(db, "Survey pilot", "Evidence review")["project_id"]
            autonomy.plan(db, pid, [{
                "key": "survey-preflight",
                "title": "ADB preflight",
                "kind": "TEST",
                "acceptance": "Root and screenshots proven",
                "depends_on": [],
            }])
            db.execute(
                "UPDATE auto_tasks SET status='VERIFIED',producer='producer-1',"
                "producer_session='session-A',reviewer='reviewer-1',"
                "reviewer_session='session-B',"
                "evidence_json='[\"evidence/test.json\"]' WHERE project_id=?",
                (pid,),
            )
            db.commit()
        (self.root / ".re_harness" / "quota-watchdog.json").write_text(
            json.dumps({"project_id": pid, "status": "NEEDS_USER"}),
            encoding="utf-8",
        )
        return pid

    def test_verified_does_not_imply_accepted(self):
        pid = self.seed()
        result = project_audit.audit_text(self.root)
        self.assertIn(pid, result)
        self.assertIn("Tasks VERIFIED: 1/1", result)
        self.assertIn("Final ACCEPTED: NO", result)
        self.assertIn("Final review pending", result)
        self.assertIn("Reviewer metadata distinct actor/session: 1/1", result)
        self.assertIn("NOT independently attested", result)

    def test_final_review_event_required_for_accepted(self):
        pid = self.seed()
        with core.database(self.dbdir) as db:
            autonomy.final_review(db, pid, "external-reviewer", "ACCEPT",
                                  "Primary evidence inspected")
        result = project_audit.audit_text(self.root)
        self.assertIn("Final ACCEPTED: YES", result)
        self.assertIn("Last final review event: PROJECT_ACCEPT", result)

    def test_missing_checkpoint_is_read_only_unknown(self):
        result = project_audit.audit_text(self.root)
        self.assertIn("UNKNOWN", result)
        self.assertFalse((self.dbdir / "state.sqlite3").exists())

    def test_bad_reviewer_session_metadata_not_independent(self):
        pid = self.seed()
        with core.database(self.dbdir) as db:
            db.execute("UPDATE auto_tasks SET reviewer_session=producer_session "
                       "WHERE project_id=?", (pid,))
            db.commit()
        result = project_audit.audit_text(self.root)
        self.assertIn("Reviewer metadata distinct actor/session: 0/1", result)
