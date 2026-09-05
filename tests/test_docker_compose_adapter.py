from pathlib import Path

from tools.docker_compose_adapter import DockerComposeAdapter, redact_text


def test_redacts_secret_like_assignments():
    value = redact_text("PASSWORD=hidden TOKEN:abc123 status=ok")
    assert "hidden" not in value
    assert "abc123" not in value
    assert "status=ok" in value


def test_preflight_and_inventory_use_allowlisted_services(tmp_path: Path):
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text("services:\n  api:\n    image: example/api\n  redis:\n    image: redis\n", encoding="utf-8")

    def runner(args, timeout):
        if args[-2:] == ["config", "--services"]:
            return 0, "api\nredis\n", ""
        if "ps" in args:
            return 0, '{"Service":"api","Name":"dify-api","ID":"id1","Image":"example/api","State":"running","Health":"healthy"}\n{"Service":"db_postgres","Name":"db","ID":"id2"}\n', ""
        raise AssertionError(args)

    adapter = DockerComposeAdapter(compose_dir=tmp_path, compose_file="docker-compose.yaml", allowed_services={"api", "redis"}, runner=runner)
    assert adapter.preflight()["status"] == "ready_for_injection"
    inventory = adapter.inventory()
    assert [item["service"] for item in inventory["targets"]] == ["api"]


def test_service_outside_allowlist_is_rejected(tmp_path: Path):
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text("services:\n  api:\n    image: example/api\n", encoding="utf-8")
    adapter = DockerComposeAdapter(compose_dir=tmp_path, compose_file="docker-compose.yaml", allowed_services={"api"}, runner=lambda args, timeout: (0, "api\n", ""))
    result = adapter.run_service_canary("worker")
    assert result["status"] == "method_invalid"


def test_sandbox_string_ok_health_response_is_accepted(tmp_path: Path):
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text("services:\n  sandbox:\n    image: example/sandbox\n", encoding="utf-8")

    def runner(args, timeout):
        if "exec" in args:
            return 0, '"ok"\n', ""
        if "ps" in args:
            return 0, '{"Service":"sandbox","Name":"sandbox","State":"running","Health":"healthy"}\n', ""
        return 0, "sandbox\n", ""

    adapter = DockerComposeAdapter(compose_dir=tmp_path, compose_file="docker-compose.yaml", allowed_services={"sandbox"}, runner=runner)
    assert adapter.probe("sandbox")["oracle"]["status"] == "pass"


def test_preflight_rejects_changed_compose_digest(tmp_path: Path):
    compose = tmp_path / "docker-compose.yaml"
    compose.write_text("services:\n  api:\n    image: example/api\n", encoding="utf-8")
    adapter = DockerComposeAdapter(
        compose_dir=tmp_path,
        compose_file="docker-compose.yaml",
        allowed_services={"api"},
        expected_compose_sha256="0" * 64,
        runner=lambda args, timeout: (0, "api\n", ""),
    )
    assert adapter.preflight()["status"] == "environment_blocked"
