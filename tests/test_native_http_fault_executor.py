import pytest

from tools.native_http_fault_executor import NativeHttpFaultExecutor, build_native_http_mutation
from chaosatlas.orchestration.engine import _classify_live_outcome, _live_lifecycle_evidence
from tools.project_onboarding import result_contract_from_classification


def test_rate_limit_mutation_is_explicit_and_bounded():
    mutation = build_native_http_mutation(
        "http_rate_limit",
        {"requests_per_window": 2, "window_s": 10, "status_code": 429},
    )

    assert mutation["fault_family"] == "http_rate_limit"
    assert mutation["control"]["mode"] == "rate_limit"
    assert mutation["control"]["requests_per_window"] == 2
    assert mutation["control"]["window_s"] == 10
    assert "cleanup_command" in mutation


def test_dependency_unreachable_mutation_requires_no_ambiguous_target():
    mutation = build_native_http_mutation("business_dependency_unreachable", {})

    assert mutation["control"] == {"mode": "dependency_unreachable"}
    assert mutation["parameters"] == {}


@pytest.mark.parametrize(
    "family,parameters",
    [
        ("http_rate_limit", {"requests_per_window": 0, "window_s": 10, "status_code": 429}),
        ("http_rate_limit", {"requests_per_window": 2, "window_s": 0, "status_code": 429}),
        ("http_rate_limit", {"requests_per_window": 2, "window_s": 10, "status_code": 200}),
        ("business_dependency_unreachable", {"unexpected": True}),
    ],
)
def test_native_http_mutation_rejects_invalid_parameters(family, parameters):
    with pytest.raises(ValueError):
        build_native_http_mutation(family, parameters)


def test_native_http_executor_requires_isolation_and_probe():
    executor = NativeHttpFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=False,
        runner=lambda *_args, **_kwargs: (0, "", ""),
        probe=lambda _phase: {"status": "pass", "samples": [{"status_code": 200}]},
    )
    result = executor(
        {
            "kind": "ChaosAtlasNativeHttpFault",
            "metadata": {"name": "x", "namespace": "lab"},
            "spec": {"faultFamily": "http_rate_limit", "targetSelector": {"app": "web"}, "parameters": {"requests_per_window": 2, "window_s": 10, "status_code": 429}},
        }
    )

    assert result["status"] == "environment_blocked"
    assert "isolated" in result["errors"][0]


def test_native_http_executor_completes_control_lifecycle_with_cleanup():
    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        if args[:4] == ["get", "pods", "-n", "lab"]:
            return 0, '{"items":[{"metadata":{"name":"web-1"},"status":{"phase":"Running"}}]}', ""
        return 0, "", ""

    phases = {
        "baseline": {"status": "pass", "samples": [{"status_code": 200}]},
        "observe": {"status": "business_unreachable", "samples": [{"status_code": 429}]},
        "recovery": {"status": "pass", "samples": [{"status_code": 200}]},
    }
    executor = NativeHttpFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: phases[phase],
        capability_probe=lambda pod: {"status": "ready", "pod": pod, "read_only": True},
    )
    result = executor({
        "kind": "ChaosAtlasNativeHttpFault",
        "metadata": {"name": "rate-limit", "namespace": "lab"},
        "spec": {"faultFamily": "http_rate_limit", "targetSelector": {"app": "web"}, "parameters": {"requests_per_window": 2, "window_s": 10, "status_code": 429}},
    })

    assert result["status"] == "executed"
    assert result["outcome_status"] == "rate_limit_observed"
    assert result["attestation"]["valid"] is True
    assert result["cleanup"]["verified"] is True
    assert result["recovery"]["business_probe"]["status"] == "pass"
    assert any("base64" in str(call) for call in calls)


def test_native_http_outcomes_have_fault_specific_classification():
    assert _classify_live_outcome("executed", True, "rate_limit_observed") == "rate_limit_observed"
    assert _classify_live_outcome("executed", True, "dependency_unreachable_observed") == "dependency_unreachable_observed"
    assert result_contract_from_classification("rate_limit_observed", claim_scope="deployment:web")["result"] == "weakness"
    assert result_contract_from_classification("dependency_unreachable_observed", claim_scope="deployment:web")["result"] == "weakness"


def test_native_http_lifecycle_evidence_accepts_fault_effect_observation(tmp_path):
    records = _live_lifecycle_evidence(
        output_root=tmp_path,
        evidence_prefix="r1",
        claim_scope="deployment:web",
        fault={
            "attestation": {"baseline": True, "injection": True, "observation": True, "recovery": True, "cleanup": True},
            "observation_contract": {"kind": "http_rate_limit", "threshold_reached": True, "threshold_status": 429},
            "observation": {"status": "business_unreachable", "samples": [{"status_code": 429}]},
        },
    )
    observation = next(item for item in records if item["evidence_id"] == "r1-observation")
    assert "observation" in observation["satisfies"]
    mechanism = next(item for item in records if item["evidence_id"] == "r1-http-boundary-mechanism")
    assert "mechanism_evidence" in mechanism["satisfies"]


def test_invalid_business_baseline_is_not_mislabeled_as_injection_failure():
    assert _classify_live_outcome(
        "business_not_reachable",
        False,
        "",
    ) == "business_not_reachable"
