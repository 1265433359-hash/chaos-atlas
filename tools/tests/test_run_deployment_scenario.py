from __future__ import annotations

from tools.run_deployment_scenario import run_scenario
from tools.tests.test_deployment_capability import scenario
from tools.compile_scenario_node import compile_scenario


def test_dry_run_only_emits_lifecycle_without_executor():
    value = scenario()
    result = run_scenario(value, compiled=compile_scenario(value), dry_run=True)
    assert result["status"] == "dry_run"
    assert result["phases"][0]["phase_id"] == "kill"
    assert result["phases"][0]["faults"][0]["injection_confirmed"] is False


def test_executor_failure_is_not_a_defense():
    value = scenario()
    result = run_scenario(value, compiled=compile_scenario(value), dry_run=False, executor=lambda *_: {"status": "environment_blocked"})
    assert result["status"] == "environment_blocked"
    assert result["verdict"] not in {"availability_defended", "confirmed_weakness"}


def test_executor_exception_is_preserved_at_fault_boundary():
    value = scenario()

    def failing_executor(*_args):
        raise RuntimeError("baseline port-forward failed")

    result = run_scenario(
        value,
        compiled=compile_scenario(value),
        dry_run=False,
        executor=failing_executor,
    )

    fault = result["phases"][0]["faults"][0]
    assert fault["status"] == "environment_blocked"
    assert fault["error"] == "RuntimeError: baseline port-forward failed"
    assert fault["errors"] == ["RuntimeError: baseline port-forward failed"]


def test_executor_mechanism_evidence_is_preserved_for_rca():
    value = scenario()
    evidence = [{"evidence_id": "mechanism-1", "kind": "runtime_log", "source_ref": "runtime/log.txt", "interpretation": "fault reached the selected process"}]
    result = run_scenario(
        value,
        compiled=compile_scenario(value),
        dry_run=False,
        executor=lambda *_: {
            "status": "executed",
            "injection_confirmed": True,
            "injected_count": 1,
            "cleanup_confirmed": True,
            "mechanism_evidence": evidence,
        },
    )
    assert result["phases"][0]["faults"][0]["mechanism_evidence"] == evidence
