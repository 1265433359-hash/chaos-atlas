from chaosatlas.orchestration.workflow_executor import WorkflowBoundFaultExecutor


class Workflow:
    def __init__(self, *, cleanup=True):
        self.events = []
        self.cleanup = cleanup

    def prepare_fixture(self, context):
        self.events.append(("prepare", context["run_id"]))
        return {"status": "prepared"}

    def probe(self, phase, context):
        self.events.append(("probe", phase))
        return {"status": "pass", "samples": [{"status": 200}]}

    def collect_evidence(self, context):
        self.events.append(("collect", context["run_id"]))
        return {"status": "collected"}

    def cleanup_fixture(self, context):
        self.events.append(("cleanup", context["run_id"]))
        return {"status": "cleaned" if self.cleanup else "cleanup_failed", "cleanup_confirmed": self.cleanup}


class Executor:
    def __init__(self, workflow):
        self.workflow = workflow
        self.probe = None

    def __call__(self, _manifest, _phase, _fault):
        baseline = self.probe("baseline")
        observed = self.probe("observe")
        recovered = self.probe("recovery")
        return {
            "status": "executed", "lifecycle": ["baseline", "inject", "observe", "recover", "cleanup"],
            "baseline": baseline, "observation": observed,
            "recovery": {"confirmed": recovered["status"] == "pass"},
            "cleanup": {"confirmed": True}, "cleanup_confirmed": True,
            "injection_confirmed": True, "injected_count": 1,
            "promotion_allowed": True,
            "attestation": {"valid": True, "cleanup": True, "comparison_eligible": True, "missing": []},
        }


def _manifest():
    return {"metadata": {"name": "action-1", "namespace": "ca-l2-demo"}}


def test_specialized_executor_uses_complete_workflow_lifecycle():
    workflow = Workflow()
    executor = Executor(workflow)
    executor.probe = lambda phase: workflow.probe(phase, _manifest())

    result = WorkflowBoundFaultExecutor(executor, workflow)(_manifest())

    assert result["status"] == "executed"
    assert result["cleanup_confirmed"] is True
    assert result["business_evidence"]["status"] == "collected"
    assert [event[0] for event in workflow.events] == [
        "prepare", "probe", "probe", "probe", "collect", "cleanup",
    ]


def test_business_cleanup_failure_revokes_specialized_attestation():
    workflow = Workflow(cleanup=False)
    executor = Executor(workflow)
    executor.probe = lambda phase: workflow.probe(phase, _manifest())

    result = WorkflowBoundFaultExecutor(executor, workflow)(_manifest())

    assert result["status"] == "cleanup_failed"
    assert result["cleanup_confirmed"] is False
    assert result["promotion_allowed"] is False
    assert result["attestation"]["valid"] is False
    assert "cleanup" in result["attestation"]["missing"]


def test_prepare_failure_blocks_specialized_fault():
    workflow = Workflow()
    workflow.prepare_fixture = lambda _context: {
        "status": "prepare_failed", "cleanup": {"cleanup_confirmed": True},
    }
    called = []

    result = WorkflowBoundFaultExecutor(
        lambda *_args: called.append(True) or {}, workflow,
    )(_manifest())

    assert result["status"] == "business_fixture_prepare_failed"
    assert result["injection_confirmed"] is False
    assert result["cleanup_confirmed"] is True
    assert called == []
