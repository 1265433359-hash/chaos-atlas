import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from issue_tracker import (
    TRACKER_PATH,
    init,
    load,
    record_response,
    set_submitted,
)


class IssueTrackerTests(unittest.TestCase):
    def test_init_creates_two_ready_issues(self):
        doc = init()
        issues = doc["issues"]
        self.assertEqual(len(issues), 2)
        self.assertTrue(all(i["status"] == "ready" for i in issues))

    def test_mark_submitted_records_url(self):
        init()
        doc = set_submitted("ISSUE-001", "https://github.com/x/y/issues/1")
        target = next(i for i in doc["issues"] if i["issue_id"] == "ISSUE-001")
        self.assertEqual(target["status"], "submitted")
        self.assertEqual(target["url"], "https://github.com/x/y/issues/1")

    def test_response_must_be_valid(self):
        with self.assertRaises(SystemExit):
            record_response("ISSUE-001", "maybe")

    def test_confirmed_reflow_upgrades_se_confidence(self):
        init()
        record_response("ISSUE-001", "confirmed", note="upstream confirmed")
        se = json.loads(Path("artifacts/experiments/selection_experience.json").read_text(encoding="utf-8"))
        hit = [e for e in se["entries"] if e.get("external_confirmation") == ["ISSUE-001"]]
        self.assertTrue(hit, "external confirmation should be recorded on matching SE entries")

    def test_audit_log_records_external_events(self):
        init()
        record_response("ISSUE-002", "no_response", note="silent")
        log = json.loads(Path("artifacts/experiments/knowledge_audit_log.json").read_text(encoding="utf-8"))
        events = [e for e in log["entries"] if e.get("change") == "external_no_response"]
        self.assertTrue(any("ISSUE-002" in e.get("source", "") for e in events))


if __name__ == "__main__":
    unittest.main()
