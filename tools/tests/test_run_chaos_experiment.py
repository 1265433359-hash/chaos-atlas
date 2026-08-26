from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.run_chaos_experiment import (
    defense_conclusion_allowed,
    observation_failure_sample,
    wait_for_port,
)


class ExitedProcess:
    returncode = 1

    def poll(self):
        return self.returncode

    def communicate(self):
        return None, None


def test_wait_for_port_reports_exit_when_process_output_is_file_redirected() -> None:
    with pytest.raises(RuntimeError, match=r"port-forward exited with code 1:"):
        wait_for_port("127.0.0.1", 1, ExitedProcess(), 0.1)


def test_observation_failure_sample_preserves_transport_evidence() -> None:
    sample = observation_failure_sample(3, "pod is pending")
    assert sample["sample"] == 3
    assert sample["status_code"] is None
    assert sample["body"] is None
    assert sample["error"] == "pod is pending"


def test_defense_conclusion_requires_independent_baseline() -> None:
    lifecycle = {"injected": True}
    assert defense_conclusion_allowed(lifecycle, [{"status_code": None}], None) is False
    assert defense_conclusion_allowed(lifecycle, [{"status_code": 200}], {"requests": [{"status_code": 200}]}) is True
