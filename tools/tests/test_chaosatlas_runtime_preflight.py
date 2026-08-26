from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.chaosatlas_runtime_preflight import KubernetesPreflight


PROFILE = {
    "project_id": "sock-shop",
    "namespace_policy": {"allowed_namespaces": ["sock-shop-lab"], "isolation_required": True},
    "business_oracles": [{"id": "home", "kind": "http", "entrypoint": "/", "success_contract": "http_200"}],
    "observability": {"logs": {"provider": "kubectl", "required": True}, "events": {"provider": "kubectl", "required": True}},
    "recovery": {"deadline_s": 180, "require_business_probe": True, "require_cleanup": True},
    "cleanup": {"owner": "chaosatlas", "must_be_empty": True},
}


def _runner(responses: dict[tuple[str, ...], tuple[int, Any, str]]):
    calls: list[tuple[str, ...]] = []

    def run(args: list[str], timeout: int = 30, input_text: str | None = None):
        del timeout, input_text
        key = tuple(args)
        calls.append(key)
        code, value, error = responses.get(key, (1, "", "unexpected command"))
        stdout = value if isinstance(value, str) else json.dumps(value)
        return code, stdout, error

    return run, calls


def _healthy_responses() -> dict[tuple[str, ...], tuple[int, Any, str]]:
    responses = {
        ("config", "current-context"): (0, "minikube\n", ""),
        ("get", "namespace", "sock-shop-lab", "-o", "json"): (0, {"metadata": {"name": "sock-shop-lab"}}, ""),
        ("get", "deployments", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": [{"metadata": {"name": "front-end"}, "status": {"availableReplicas": 1}}]}, ""),
        ("get", "services", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": [{"metadata": {"name": "front-end"}}]}, ""),
        ("get", "pods", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": [{"metadata": {"name": "front-end-1", "uid": "uid-1"}, "status": {"phase": "Running"}}]}, ""),
        ("get", "events", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": []}, ""),
        ("get", "podchaos", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": []}, ""),
        ("get", "networkchaos", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": []}, ""),
        ("get", "stresschaos", "-n", "sock-shop-lab", "-o", "json"): (0, {"items": []}, ""),
    }
    for resource in ("httpchaos", "dnschaos", "iochaos", "timechaos", "schedules", "workflows"):
        responses[("get", resource, "-n", "sock-shop-lab", "-o", "json")] = (0, {"items": []}, "")
    return responses


def test_preflight_is_read_only_and_returns_ready_when_contracts_are_present() -> None:
    runner, calls = _runner(_healthy_responses())

    result = KubernetesPreflight(profile=PROFILE, runner=runner).run()

    assert result["status"] == "ready_for_injection"
    assert result["checks"]["namespace"]["status"] == "pass"
    assert result["checks"]["business_oracle"]["status"] == "configured"
    assert result["residual_resources"]["status"] == "clean"
    assert not any(args[0] in {"apply", "delete", "patch", "create"} for args in calls)


def test_preflight_fails_closed_on_kubeconfig_or_namespace_failure() -> None:
    responses = _healthy_responses()
    responses[("config", "current-context")] = (1, "", "current-context unavailable")
    runner, _ = _runner(responses)

    result = KubernetesPreflight(profile=PROFILE, runner=runner).run()

    assert result["status"] == "environment_blocked"
    assert result["checks"]["context"]["status"] == "blocked"


def test_preflight_blocks_on_residual_chaos_resources() -> None:
    responses = _healthy_responses()
    responses[("get", "podchaos", "-n", "sock-shop-lab", "-o", "json")] = (0, {"items": [{"metadata": {"name": "stale"}}]}, "")
    runner, _ = _runner(responses)

    result = KubernetesPreflight(profile=PROFILE, runner=runner).run()

    assert result["status"] == "environment_blocked"
    assert result["residual_resources"]["status"] == "residual"


def test_preflight_blocks_when_workload_has_no_running_pods() -> None:
    responses = _healthy_responses()
    responses[("get", "deployments", "-n", "sock-shop-lab", "-o", "json")] = (
        0,
        {"items": [{"metadata": {"name": "front-end"}, "status": {"availableReplicas": 0}}]},
        "",
    )
    responses[("get", "pods", "-n", "sock-shop-lab", "-o", "json")] = (0, {"items": []}, "")

    runner, _ = _runner(responses)

    result = KubernetesPreflight(profile=PROFILE, runner=runner).run()

    assert result["status"] == "environment_blocked"
    assert any("running pods" in error for error in result["errors"])


def test_preflight_pins_all_calls_to_explicit_kube_context() -> None:
    base = _healthy_responses()
    responses = {
        ("--context", "minikube", *key): value
        for key, value in base.items()
    }
    runner, calls = _runner(responses)

    result = KubernetesPreflight(profile=PROFILE, runner=runner, kube_context="minikube").run()

    assert result["status"] == "ready_for_injection"
    assert calls and all(args[:2] == ("--context", "minikube") for args in calls)


def test_preflight_reports_requested_context_instead_of_process_default() -> None:
    base = _healthy_responses()
    responses = {
        ("--context", "minikube", *key): value
        for key, value in base.items()
        if key != ("config", "current-context")
    }
    runner, _ = _runner(responses)

    result = KubernetesPreflight(profile=PROFILE, runner=runner, kube_context="minikube").run()

    assert result["checks"]["context"] == {"status": "pass", "value": "minikube", "error": None}


def test_preflight_blocks_grpc_oracle_when_client_dependencies_are_unavailable() -> None:
    client = Path(__file__).resolve()
    profile = {
        **PROFILE,
        "business_oracles": [{
            "id": "place-order",
            "kind": "grpc",
            "service": "checkout",
            "remote_port": 5050,
            "entrypoint": "/oteldemo.CheckoutService/PlaceOrder",
            "success_contract": "grpc_place_order_order_id_and_shipping_tracking_id",
            "client": str(client),
            "supporting_services": [{"service": "cart", "remote_port": 7070}],
        }],
    }
    runner, _ = _runner(_healthy_responses())

    def oracle_runner(command: list[str], cwd: Path) -> tuple[int, str, str]:
        assert cwd == client.parent
        return 1, "", "ModuleNotFoundError: No module named 'google.protobuf'"

    result = KubernetesPreflight(profile=profile, runner=runner, oracle_runner=oracle_runner).run()

    assert result["status"] == "environment_blocked"
    assert result["checks"]["business_oracle"]["status"] == "blocked"
    assert "google.protobuf" in result["checks"]["business_oracle"]["error"]
    assert any("client dependencies unavailable" in error for error in result["errors"])
