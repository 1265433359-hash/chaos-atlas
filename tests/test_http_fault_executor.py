from tools.http_fault_executor import execute_http_fault


def test_http_executor_requires_injected_lifecycle_runtime():
    result = execute_http_fault({"kind": "HTTPChaos", "metadata": {"name": "x"}})

    assert result["status"] == "method_invalid"
    assert "lifecycle_executor" in result["errors"][0]


def test_http_executor_rejects_non_http_manifest_before_runtime():
    result = execute_http_fault(
        {"kind": "NetworkChaos", "metadata": {"name": "x"}},
        lifecycle_executor=object(),
    )

    assert result["status"] == "method_invalid"
    assert "HTTPChaos" in result["errors"][0]
