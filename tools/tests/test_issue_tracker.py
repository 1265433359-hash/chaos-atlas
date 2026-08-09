import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from issue_tracker import (
    TRACKER_PATH,
    init,
    load,
    record_response,
    set_submitted,
)


class IssueTrackerTests(unittest.TestCase):
    def setUp(self):
        # isolate ALL reflow writes from the real knowledge libraries and the
        # real issue tracker (phase-3 remediation: tests must never touch
        # versioned artifacts). TRACKER_PATH was previously unpatched, so
        # init()/set_submitted()/record_response() wrote the REAL tracker.
        tmp = Path(tempfile.mkdtemp())
        self._tracker = tmp / "issue_tracker.json"
        self._se = tmp / "selection_experience.json"
        self._se.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8")
        self._je = tmp / "judgment_experience.json"
        self._je.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8")
        self._audit = tmp / "knowledge_audit_log.json"
        self._audit.write_text(json.dumps({"schema_version": 1, "entries": []}), encoding="utf-8")
        self._patchers = [
            patch("issue_tracker.TRACKER_PATH", self._tracker),
            patch("issue_tracker.SE_PATH", self._se),
            patch("issue_tracker.JE_PATH", self._je),
            patch("issue_tracker.AUDIT_PATH", self._audit),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()
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
        # seed a matching SE entry in the isolated library so reflow has a target.
        # The seed MUST reference ISSUE-001's supported_by candidate so the match
        # works against the isolated tracker (phase-3 isolation exposed that the
        # old seed referenced an unrelated candidate and only passed because it
        # read the REAL tracker's historical supported_by).
        se = json.loads(self._se.read_text(encoding="utf-8"))
        se["entries"].append({
            "id": "SE-NETWORK-FAMILY-001", "confidence": "medium",
            "experiment_evidence": ["OTEL-SHIPPING-DELAY-2000"],
        })
        self._se.write_text(json.dumps(se, ensure_ascii=True), encoding="utf-8")
        record_response("ISSUE-001", "confirmed", note="upstream confirmed")
        se = json.loads(self._se.read_text(encoding="utf-8"))
        hit = [e for e in se["entries"] if e.get("external_confirmation") == ["ISSUE-001"]]
        self.assertTrue(hit, "external confirmation should be recorded on matching SE entries")

    def test_audit_log_records_external_events(self):
        init()
        record_response("ISSUE-002", "no_response", note="silent")
        log = json.loads(self._audit.read_text(encoding="utf-8"))
        events = [e for e in log["entries"] if e.get("change") == "external_no_response"]
        self.assertTrue(any("ISSUE-002" in e.get("source", "") for e in events))


if __name__ == "__main__":
    unittest.main()
