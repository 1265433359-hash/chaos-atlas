import json

from tools.compile_scenario_node import compile_scenario
from tools.native_resource_fault_executor import NativeResourceFaultExecutor, build_native_mutation
from tests.test_extended_network_faults import _scenario


def test_resource_faults_compile_to_native_fault_intents():
    expected = {
        "disk_pressure": {"path": "/tmp/chaosatlas-pressure", "size_mb": 16},
        "file_descriptor_exhaustion": {"count": 32},
        "process_exhaustion": {"count": 8},
    }
    for family, parameters in expected.items():
        result = compile_scenario(_scenario(family, parameters))
        assert result["status"] == "verified"
        manifest = result["manifests"][0]
        assert manifest["kind"] == "ChaosAtlasNativeFault"
        assert manifest["spec"]["faultFamily"] == family
        assert manifest["spec"]["parameters"] == parameters
        assert manifest["spec"]["targetSelector"] == {"app": "web"}


def test_native_resource_mutation_rejects_unsafe_path_and_bounds():
    try:
        build_native_mutation("disk_pressure", {"path": "../outside", "size_mb": 1})
    except ValueError as exc:
        assert "path" in str(exc)
    else:
        raise AssertionError("unsafe disk path must fail closed")

    try:
        build_native_mutation("process_exhaustion", {"count": 0})
    except ValueError as exc:
        assert "count" in str(exc)
    else:
        raise AssertionError("invalid process count must fail closed")


def test_native_resource_executor_requires_isolated_live_approval():
    executor = NativeResourceFaultExecutor(namespace="lab", allowed_namespaces={"lab"}, allow_live=False)
    result = executor({
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasNativeFault",
        "metadata": {"name": "resource-fault", "namespace": "lab"},
        "spec": {
            "faultFamily": "process_exhaustion",
            "targetRef": {"kind": "Deployment", "name": "web"},
            "parameters": {"count": 8},
        },
    })
    assert result["status"] == "environment_blocked"
    assert "isolated" in result["errors"][0]


def test_native_resource_executor_runs_bounded_lifecycle_with_injected_runner():
    calls = []
    pod = {"metadata": {"name": "web-abc"}, "status": {"phase": "Running"}}

    def runner(args, timeout=30, kube_context=None):
        calls.append(args)
        if args[:4] == ["get", "pods", "-n", "lab"]:
            return 0, json.dumps({"items": [pod]}), ""
        if args[0] == "exec":
            return 0, "", ""
        raise AssertionError(args)

    executor = NativeResourceFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: {"status": "pass", "samples": [{"phase": phase}]},
        capability_probe=lambda pod: {"status": "ready", "pod": pod},
        target_selector={"app": "web"},
    )
    result = executor({
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasNativeFault",
        "metadata": {"name": "resource-fault", "namespace": "lab"},
        "spec": {
            "faultFamily": "process_exhaustion",
            "targetRef": {"kind": "Deployment", "name": "web"},
            "targetSelector": {"app": "web"},
            "parameters": {"count": 2},
        },
    })
    assert result["status"] == "executed"
    assert result["attestation"]["valid"] is True
    assert result["cleanup_confirmed"] is True
    assert result["cleanup"]["verified"] is True
    assert any("test ! -e" in str(arg) for call in calls if call[0] == "exec" for arg in call)
    assert any(call[0] == "exec" for call in calls)


def test_native_resource_executor_requires_capability_probe():
    pod = {"metadata": {"name": "web-abc"}, "status": {"phase": "Running"}}

    def runner(args, timeout=30, kube_context=None):
        if args[:4] == ["get", "pods", "-n", "lab"]:
            return 0, json.dumps({"items": [pod]}), ""
        raise AssertionError(args)

    executor = NativeResourceFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: {"status": "pass", "samples": [{"phase": phase}]},
        target_selector={"app": "web"},
    )
    result = executor({
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasNativeFault",
        "metadata": {"name": "resource-fault", "namespace": "lab"},
        "spec": {
            "faultFamily": "process_exhaustion",
            "targetSelector": {"app": "web"},
            "parameters": {"count": 2},
        },
    })

    assert result["status"] == "environment_blocked"
    assert "capability" in result["errors"][0]


def test_native_resource_executor_passes_fault_family_to_capability_probe():
    pod = {"metadata": {"name": "web-abc"}, "status": {"phase": "Running"}}
    seen = []

    def runner(args, timeout=30, kube_context=None):
        if args[:4] == ["get", "pods", "-n", "lab"]:
            return 0, json.dumps({"items": [pod]}), ""
        raise AssertionError(args)

    def capability_probe(target_pod, family):
        seen.append((target_pod, family))
        return {"status": "blocked", "reason": "family capability unavailable"}

    executor = NativeResourceFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: {"status": "pass", "samples": [{"phase": phase}]},
        capability_probe=capability_probe,
        target_selector={"app": "web"},
    )
    result = executor({
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasNativeFault",
        "metadata": {"name": "resource-fault", "namespace": "lab"},
        "spec": {
            "faultFamily": "process_exhaustion",
            "targetSelector": {"app": "web"},
            "parameters": {"count": 2},
        },
    })

    assert result["status"] == "environment_blocked"
    assert seen == [("web-abc", "process_exhaustion")]


def test_disk_capability_probe_does_not_require_process_limit():
    commands = []

    def runner(args, timeout=30, kube_context=None):
        commands.append(args)
        return 0, "open_files=1048576\n", ""

    executor = NativeResourceFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        runner=runner,
    )
    result = executor._default_capability_probe("web-abc", "disk_pressure")

    assert result["status"] == "ready"
    assert commands and "ulimit -u" not in commands[0][-1]


def test_process_capability_probe_uses_bash_for_ulimit_user_processes():
    commands = []

    def runner(args, timeout=30, kube_context=None):
        commands.append(args)
        return 0, "max_processes=4096\n", ""

    executor = NativeResourceFaultExecutor(namespace="lab", allowed_namespaces={"lab"}, runner=runner)
    result = executor._default_capability_probe("web-abc", "process_exhaustion")

    assert result["status"] == "ready"
    assert commands[0][0:2] == ["exec", "web-abc"]
    assert "bash" in commands[0]


def test_process_capability_probe_accepts_unlimited_bounded_by_executor():
    def runner(args, timeout=30, kube_context=None):
        return 0, "max_processes=unlimited\n", ""

    executor = NativeResourceFaultExecutor(namespace="lab", allowed_namespaces={"lab"}, runner=runner)
    result = executor._default_capability_probe("web-abc", "process_exhaustion")

    assert result["status"] == "ready"
    assert result["limits"]["max_processes"] == "unlimited"


def test_native_resource_executor_blocks_when_cleanup_marker_remains():
    pod = {"metadata": {"name": "web-abc"}, "status": {"phase": "Running"}}

    def runner(args, timeout=30, kube_context=None):
        if args[:4] == ["get", "pods", "-n", "lab"]:
            return 0, json.dumps({"items": [pod]}), ""
        if args[0] == "exec" and "test ! -e" in args[-1]:
            return 1, "", "marker remains"
        if args[0] == "exec":
            return 0, "", ""
        raise AssertionError(args)

    executor = NativeResourceFaultExecutor(
        namespace="lab",
        allowed_namespaces={"lab"},
        allow_live=True,
        isolated=True,
        runner=runner,
        probe=lambda phase: {"status": "pass", "samples": [{"phase": phase}]},
        target_selector={"app": "web"},
    )
    result = executor({
        "apiVersion": "chaosatlas.dev/v1alpha1",
        "kind": "ChaosAtlasNativeFault",
        "metadata": {"name": "resource-fault", "namespace": "lab"},
        "spec": {
            "faultFamily": "process_exhaustion",
            "targetSelector": {"app": "web"},
            "parameters": {"count": 2},
        },
    })

    assert result["cleanup_confirmed"] is False
    assert result["attestation"]["valid"] is False


def test_minikube_control_plane_mutator_fails_closed_without_owned_profile():
    from tools.minikube_control_plane_mutator import MinikubeControlPlaneMutator

    mutator = MinikubeControlPlaneMutator(
        profile="shared",
        context="shared",
        runner=lambda *_args, **_kwargs: (0, "", ""),
        disposable=False,
    )
    result = mutator(latency_ms=100, manifest={"kind": "ChaosAtlasControlPlaneFault"})
    assert result["status"] == "environment_blocked"
    assert "disposable" in result["errors"][0]


def test_minikube_control_plane_mutator_applies_and_restores_default_qdisc():
    from tools.minikube_control_plane_mutator import MinikubeControlPlaneMutator

    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        if args[:2] == ["docker", "ps"]:
            return 0, "cp123\n", ""
        if args[:5] == ["docker", "exec", "cp123", "tc", "qdisc"]:
            if "show" in args:
                return 0, "qdisc noqueue 0: root refcnt 2\n", ""
            return 0, "", ""
        if args[:2] == ["kubectl", "--context"]:
            return 0, "ok\n", ""
        raise AssertionError(args)

    result = MinikubeControlPlaneMutator(
        profile="chaosatlas-apiserver-canary",
        context="chaosatlas-apiserver-canary",
        runner=runner,
        disposable=True,
    )(latency_ms=100, manifest={"kind": "ChaosAtlasControlPlaneFault"})
    assert result["status"] == "executed"
    assert result["cleanup_confirmed"] is True
    assert any("replace" in call for call in calls)
    assert any("del" in call for call in calls)


def test_minikube_control_plane_mutator_observes_while_delay_is_active():
    from tools.minikube_control_plane_mutator import MinikubeControlPlaneMutator

    events = []

    def runner(args, **_kwargs):
        if args[:2] == ["docker", "ps"]:
            return 0, "cp123\n", ""
        if args[:5] == ["docker", "exec", "cp123", "tc", "qdisc"]:
            if "show" in args:
                return 0, "qdisc noqueue 0: root refcnt 2\n", ""
            events.append("qdisc")
            return 0, "", ""
        if args[:2] == ["kubectl", "--context"]:
            events.append("health")
            return 0, "ok\n", ""
        raise AssertionError(args)

    def probe(phase):
        events.append(f"probe:{phase}")
        return {"status": "pass", "samples": [{"status_code": 200}]}

    result = MinikubeControlPlaneMutator(
        profile="chaosatlas-apiserver-canary",
        context="chaosatlas-apiserver-canary",
        runner=runner,
        disposable=True,
    )(latency_ms=100, manifest={"kind": "ChaosAtlasControlPlaneFault"}, probe=probe)

    assert result["status"] == "executed"
    assert result["observation"]["status"] == "pass"
    assert events.index("probe:observe") < events.index("health")


def test_minikube_control_plane_mutator_uses_valid_docker_format_template():
    from tools.minikube_control_plane_mutator import MinikubeControlPlaneMutator

    calls = []

    def runner(args, **_kwargs):
        calls.append(args)
        if args[:2] == ["docker", "ps"]:
            return 0, "cp123\n", ""
        if args[:5] == ["docker", "exec", "cp123", "tc", "qdisc"]:
            return 0, "qdisc noqueue 0: root\n", ""
        if args[:2] == ["kubectl", "--context"]:
            return 0, "ok\n", ""
        raise AssertionError(args)

    MinikubeControlPlaneMutator(
        profile="chaosatlas-apiserver-canary",
        context="chaosatlas-apiserver-canary",
        runner=runner,
        disposable=True,
    )(latency_ms=100, manifest={"kind": "ChaosAtlasControlPlaneFault"})

    docker_ps = next(call for call in calls if call[:2] == ["docker", "ps"])
    assert docker_ps[-1] == "{{.ID}}"


def test_control_plane_executor_projects_probe_and_cleanup_into_attestation():
    from tools.kubernetes_fault_executor import ControlPlaneDelayExecutor

    observed_phases = []

    def probe(phase):
        observed_phases.append(phase)
        return {"status": "pass", "samples": [{"status_code": 200, "latency_ms": 120}]}

    def mutator(*, latency_ms, manifest, probe):
        assert latency_ms == 100
        assert manifest["kind"] == "ChaosAtlasControlPlaneFault"
        observation = probe("observe")
        return {
            "status": "executed",
            "injection_confirmed": True,
            "cleanup_confirmed": True,
            "observation": observation,
            "recovery": {"confirmed": True},
            "cleanup": {"confirmed": True, "verified": True},
        }

    result = ControlPlaneDelayExecutor(
        allow_live=True,
        disposable_cluster=True,
        mutator=mutator,
        probe=probe,
    )({
        "kind": "ChaosAtlasControlPlaneFault",
        "metadata": {"name": "api-delay", "namespace": "chaosatlas-run-api-delay"},
        "spec": {"faultFamily": "api_server_delay", "parameters": {"latency_ms": 100}},
    })

    assert observed_phases == ["baseline", "observe"]
    assert result["status"] == "executed"
    assert result["injection_confirmed"] is True
    assert result["attestation"]["valid"] is True
    assert result["attestation"]["comparison_eligible"] is True
