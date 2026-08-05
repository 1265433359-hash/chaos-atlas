from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture_cgroup_cpu


class CgroupPodSelectionTest(unittest.TestCase):
    def test_multiple_ready_pods_are_rejected(self) -> None:
        payload = {
            "items": [
                {"metadata": {"name": "pod-a"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
                {"metadata": {"name": "pod-b"}, "status": {"conditions": [{"type": "Ready", "status": "True"}]}},
            ]
        }
        with patch.object(capture_cgroup_cpu, "run", return_value=(0, json.dumps(payload), "")):
            with self.assertRaises(RuntimeError):
                capture_cgroup_cpu.choose_pod("train-ticket-lab", "app=demo")


if __name__ == "__main__":
    unittest.main()
