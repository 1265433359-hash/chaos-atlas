from scripts.run_httpchaos_runtime_canary import _effect, _manifest


def test_manifest_is_namespace_scoped_and_one_shot():
    manifest = _manifest(
        fault="http_status_error",
        namespace="chaosatlas-medusa",
        name="canary",
        selector={"app.kubernetes.io/name": "medusa-backend"},
        port=9000,
        path="/health",
    )
    assert manifest["kind"] == "HTTPChaos"
    assert manifest["spec"]["mode"] == "one"
    assert manifest["spec"]["selector"]["namespaces"] == ["chaosatlas-medusa"]
    assert manifest["spec"]["replace"]["code"] == 503


def test_effect_requires_fault_specific_observation():
    result = {"observation": {"samples": [{"status_code": 503, "body": "unavailable"}]}}
    assert _effect("http_status_error", result)["confirmed"] is True
    assert _effect("http_response_corrupt", result)["confirmed"] is False
