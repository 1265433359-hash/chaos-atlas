import base64

from tools.compile_scenario_node import compile_scenario
from tests.test_extended_network_faults import _scenario


def test_http_delay_compiles_to_httpchaos_delay():
    result = compile_scenario(_scenario("http_delay", {"latency_ms": 300, "port": 80, "path": "/"}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "HTTPChaos"
    assert "action" not in manifest["spec"]
    assert manifest["spec"]["delay"] == "300ms"


def test_http_abort_compiles_to_httpchaos_abort():
    result = compile_scenario(_scenario("http_abort", {"port": 80, "path": "/"}))
    assert result["status"] == "verified"
    spec = result["manifests"][0]["spec"]
    assert "action" not in spec
    assert spec["abort"] is True


def test_http_status_error_compiles_to_httpchaos_replace_code():
    result = compile_scenario(_scenario("http_status_error", {"port": 80, "path": "/", "status_code": 503}))
    assert result["status"] == "verified"
    spec = result["manifests"][0]["spec"]
    assert "action" not in spec
    assert spec["replace"]["code"] == 503


def test_http_response_corrupt_compiles_to_httpchaos_replace_body():
    result = compile_scenario(_scenario("http_response_corrupt", {"port": 80, "path": "/", "body": "broken"}))
    assert result["status"] == "verified"
    spec = result["manifests"][0]["spec"]
    assert "action" not in spec
    assert spec["replace"]["body"] == base64.b64encode(b"broken").decode("ascii")


def test_dependency_error_compiles_to_explicit_downstream_error():
    result = compile_scenario(_scenario("dependency_error", {"port": 80, "path": "/", "status_code": 503}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "HTTPChaos"
    assert manifest["metadata"]["labels"]["chaosatlas.dev/semantic-fault"] == "dependency_error"
    assert manifest["spec"]["replace"]["code"] == 503


def test_http_rate_limit_compiles_to_native_http_control_fault():
    result = compile_scenario(_scenario("http_rate_limit", {"requests_per_window": 2, "window_s": 10, "status_code": 429}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "ChaosAtlasNativeHttpFault"
    assert manifest["spec"]["faultFamily"] == "http_rate_limit"
    assert manifest["spec"]["parameters"]["requests_per_window"] == 2


def test_business_dependency_unreachable_compiles_to_native_http_control_fault():
    result = compile_scenario(_scenario("business_dependency_unreachable", {}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "ChaosAtlasNativeHttpFault"
    assert manifest["spec"]["faultFamily"] == "business_dependency_unreachable"


def test_connection_reset_compiles_to_explicit_http_session_abort():
    result = compile_scenario(_scenario("connection_reset", {"port": 80, "path": "/"}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "HTTPChaos"
    assert manifest["metadata"]["labels"]["chaosatlas.dev/semantic-fault"] == "connection_reset"
    assert manifest["spec"]["abort"] is True


def test_replica_reduction_compiles_to_kubernetes_api_mutation():
    result = compile_scenario(_scenario("replica_reduction", {"replicas": 0}))
    assert result["status"] == "verified"
    manifest = result["manifests"][0]
    assert manifest["kind"] == "ChaosAtlasKubernetesFault"
    assert manifest["spec"]["faultFamily"] == "replica_reduction"
    assert manifest["spec"]["parameters"]["replicas"] == 0


def test_config_faults_compile_to_kubernetes_api_mutations():
    for family, parameters in (("config_reload", {"reload_token": "r1"}), ("config_drift", {"value": "drift"})):
        result = compile_scenario(_scenario(family, parameters))
        assert result["status"] == "verified"
        manifest = result["manifests"][0]
        assert manifest["kind"] == "ChaosAtlasKubernetesFault"
        assert manifest["spec"]["faultFamily"] == family
