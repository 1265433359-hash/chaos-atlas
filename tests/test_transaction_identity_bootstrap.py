import json
from pathlib import Path

import pytest

from chaosatlas.oracles.identity_bootstrap import (
    BootstrapResponse,
    KubernetesIdentityEnvironment,
    MEDUSA_KEY_QUERY,
    bootstrap_erpnext,
    bootstrap_immich,
    bootstrap_medusa,
    bootstrap_rocketchat,
)
from scripts.run_transaction_identity_acceptance import _scan_persisted_values


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _no_identity_bootstrap_sleep(monkeypatch):
    monkeypatch.setattr("chaosatlas.oracles.identity_bootstrap.time.sleep", lambda _seconds: None)


class FakeEnvironment:
    def __init__(self, *, secrets=None, responses=None, postgres=None):
        self.secrets = secrets or {}
        self.responses = list(responses or [])
        self.postgres = postgres or {}
        self.requests = []
        self.bindings = []

    def read_secret(self, name, key):
        return self.secrets[(name, key)]

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        response = self.responses.pop(0)
        return BootstrapResponse(response[0], response[1], {})

    def postgres_json(self, sql):
        assert sql == MEDUSA_KEY_QUERY
        return self.postgres

    def bind_secret(self, name, role, principal_id, values):
        self.bindings.append((name, role, principal_id, values))
        for key, value in values.items():
            self.secrets[(name, key)] = value
        return {
            "secret_name": name,
            "secret_uid": "uid-1",
            "key_names": sorted(values),
            "binding_source": "lease_owned_secret_ref",
        }


def _assert_report_has_no_values(report, *values):
    encoded = json.dumps(report, sort_keys=True)
    for value in values:
        assert value not in encoded


def test_sensitive_value_scan_ignores_runtime_templates_but_flags_materialized_credentials(tmp_path):
    template = tmp_path / "template.json"
    template.write_text(
        json.dumps({"authorization": "token ${api-key}:${api-secret}"}), encoding="utf-8",
    )
    assert _scan_persisted_values(tmp_path) == []

    materialized = tmp_path / "materialized.json"
    materialized.write_text(
        json.dumps({"authorization": "token concrete-key:concrete-secret"}), encoding="utf-8",
    )
    assert _scan_persisted_values(tmp_path) == ["materialized.json"]


def test_bootstrap_immich_binds_new_user_api_key_without_reporting_credentials():
    environment = FakeEnvironment(
        secrets={
            ("immich-bootstrap-identity", "admin-password"): "admin-password-value",
            ("immich-bootstrap-identity", "user-password"): "user-password-value",
        },
        responses=[
            (200, {"isInitialized": False}),
            (201, {"id": "admin"}),
            (201, {"accessToken": "admin-token"}),
            (201, {"id": "user-1"}),
            (201, {"userId": "user-1", "accessToken": "user-token"}),
            (201, {"secret": "api-key-value"}),
        ],
    )
    report, fixtures = bootstrap_immich(environment)
    assert fixtures == {}
    assert environment.bindings == [(
        "immich-transaction-auth", "transaction-test-user", "user-1",
        {"x-api-key": "api-key-value"},
    )]
    assert report["principal_id"] == "user-1"
    _assert_report_has_no_values(report, "admin-password-value", "user-password-value", "admin-token", "user-token", "api-key-value")


def test_bootstrap_rocketchat_binds_synthetic_user_without_reporting_credentials():
    environment = FakeEnvironment(
        secrets={
            ("rocketchat-bootstrap-identity", "user-password"): "user-password-value",
        },
        responses=[
            (200, {"user": {"_id": "user-1"}}),
            (200, {"data": {"authToken": "user-token", "userId": "user-1"}}),
        ],
    )
    report, fixtures = bootstrap_rocketchat(environment)
    assert fixtures == {}
    assert environment.bindings == [(
        "rocketchat-transaction-auth", "transaction-test-user", "user-1",
        {"x-auth-token": "user-token", "x-user-id": "user-1"},
    )]
    assert environment.requests[0][1] == "/api/v1/users.register"
    _assert_report_has_no_values(report, "user-password-value", "user-token")


def test_bootstrap_erpnext_binds_token_and_keeps_session_out_of_report():
    authorization = "token api-key-value:api-secret-value"
    environment = FakeEnvironment(
        secrets={("erpnext-bootstrap-identity", "authorization"): authorization},
        responses=[
            (200, {"data": []}),
            *[(200, {"data": []}) for _ in range(12)],
        ],
    )
    report, fixtures = bootstrap_erpnext(environment)
    assert fixtures == {}
    assert environment.bindings == [(
        "erpnext-transaction-auth", "transaction-todo-user", "chaosatlas-oracle@example.com",
        {"authorization": authorization},
    )]
    assert {request[0] for request in environment.requests} == {"GET"}
    assert report["authorization_stability_checks"] == 12
    _assert_report_has_no_values(report, authorization)


def test_bootstrap_erpnext_retries_only_transient_read_only_authorization_checks(monkeypatch):
    monkeypatch.setattr("chaosatlas.oracles.identity_bootstrap.time.sleep", lambda _seconds: None)
    authorization = "token api-key-value:api-secret-value"
    environment = FakeEnvironment(
        secrets={("erpnext-bootstrap-identity", "authorization"): authorization},
        responses=[
            (502, {}),
            (401, {}),
            (200, {"data": []}),
            *[(200, {"data": []}) for _ in range(12)],
        ],
    )
    bootstrap_erpnext(environment)
    methods_and_paths = [(method, path) for method, path, _kwargs in environment.requests]
    assert methods_and_paths == [("GET", "/api/resource/ToDo")] * 15


def test_bootstrap_erpnext_retries_the_documented_token_scheme_without_reporting_credentials(monkeypatch):
    monkeypatch.setattr("chaosatlas.oracles.identity_bootstrap.time.sleep", lambda _seconds: None)
    authorization = "token api-key-value:api-secret-value"
    environment = FakeEnvironment(
        secrets={("erpnext-bootstrap-identity", "authorization"): authorization},
        responses=[
            (401, {}),
            (200, {"data": []}),
            *[(200, {"data": []}) for _ in range(12)],
        ],
    )

    report, _fixtures = bootstrap_erpnext(environment)

    assert environment.bindings[0][3]["authorization"] == authorization
    assert environment.requests[0][2]["headers"]["Authorization"] == authorization
    assert environment.requests[1][2]["headers"]["Authorization"] == authorization
    _assert_report_has_no_values(report, authorization)


def test_bootstrap_erpnext_failed_auth_reports_only_safe_user_diagnostics(monkeypatch):
    monkeypatch.setattr("chaosatlas.oracles.identity_bootstrap.time.sleep", lambda _seconds: None)
    authorization = "token api-key-value:api-secret-value"
    environment = FakeEnvironment(
        secrets={("erpnext-bootstrap-identity", "authorization"): authorization},
        responses=[
            *[(401, {}) for _ in range(11)],
        ],
    )

    with pytest.raises(ValueError) as raised:
        bootstrap_erpnext(environment)

    message = str(raised.value)
    assert message == "ERPNext pre-web API credential verification failed with HTTP 401"
    _assert_report_has_no_values(message, authorization)


def test_bootstrap_erpnext_retries_transient_401_after_exact_secret_readback(monkeypatch):
    monkeypatch.setattr("chaosatlas.oracles.identity_bootstrap.time.sleep", lambda _seconds: None)
    authorization = "token api-key-value:api-secret-value"
    environment = FakeEnvironment(
        secrets={("erpnext-bootstrap-identity", "authorization"): authorization},
        responses=[
            (200, {"data": []}),
            (401, {}),
            *[(200, {"data": []}) for _ in range(12)],
        ],
    )

    report, _fixtures = bootstrap_erpnext(environment)

    assert report["status"] == "initialized"
    assert [request[0:2] for request in environment.requests[-13:]] == [
        ("GET", "/api/resource/ToDo")
    ] * 13


def test_bootstrap_erpnext_rejects_non_token_bootstrap_credential_before_http():
    environment = FakeEnvironment(
        secrets={("erpnext-bootstrap-identity", "authorization"): "Basic unsupported"},
    )

    with pytest.raises(ValueError, match="token scheme"):
        bootstrap_erpnext(environment)

    assert environment.requests == []


def test_bootstrap_medusa_binds_seed_channel_and_emits_only_business_fixtures():
    environment = FakeEnvironment(
        postgres={"token": "publishable-token", "api_key_id": "apk-1", "sales_channel_id": "sc-1"},
        responses=[
            (200, {"regions": [{"id": "reg-1", "currency_code": "eur"}]}),
            (200, {"products": [{"variants": [{"id": "var-1", "calculated_price": {"calculated_amount": 1234}}]}]}),
        ],
    )
    report, fixtures = bootstrap_medusa(environment)
    assert fixtures == {
        "synthetic_region_id": "reg-1",
        "synthetic_variant_id": "var-1",
        "fixture_currency": "eur",
        "fixture_unit_price": 1234,
    }
    assert environment.bindings == [(
        "medusa-transaction-auth", "transaction-sales-channel", "sc-1",
        {"x-publishable-api-key": "publishable-token"},
    )]
    _assert_report_has_no_values(report, "publishable-token")


class FakePostgresProvider:
    def __init__(self):
        self.args = None

    def _run(self, _plan, args, **_kwargs):
        self.args = args
        return 0, '{"token":"redacted"}', ""


def test_kubernetes_postgres_query_is_exactly_allowlisted_and_passed_to_psql():
    provider = FakePostgresProvider()
    environment = object.__new__(KubernetesIdentityEnvironment)
    environment.lease = {"project_id": "medusa", "plan": {}}
    environment.namespace = "ca-l2-medusa"
    environment.provider = provider
    assert environment.postgres_json(MEDUSA_KEY_QUERY) == {"token": "redacted"}
    assert MEDUSA_KEY_QUERY in provider.args[-1]
    with pytest.raises(ValueError, match="reviewed Medusa"):
        environment.postgres_json("select current_user")


@pytest.mark.parametrize(("project", "secret_name", "role", "keys"), [
    ("immich", "immich-transaction-auth", "transaction-test-user", {"x-api-key"}),
    ("medusa", "medusa-transaction-auth", "transaction-sales-channel", {"x-publishable-api-key"}),
    ("rocketchat", "rocketchat-transaction-auth", "transaction-test-user", {"x-auth-token", "x-user-id"}),
    ("erpnext", "erpnext-transaction-auth", "transaction-todo-user", {"authorization"}),
])
def test_project_blueprint_declares_empty_lease_owned_transaction_secret(project, secret_name, role, keys):
    path = REPO_ROOT / "projects" / "chaosatlas-apps" / project / "isolation" / "l2-blueprint.json"
    blueprint = json.loads(path.read_text(encoding="utf-8"))
    secret = next(item for item in blueprint["resources"] if item.get("kind") == "Secret" and item["metadata"].get("name") == secret_name)
    assert secret["metadata"]["annotations"] == {
        "chaosatlas.dev/principal-role": role,
        "chaosatlas.dev/principal-id": "pending-bootstrap",
    }
    assert set(secret["runtimeGenerate"]["keys"]) == keys
    assert "stringData" not in secret and "data" not in secret


def test_erpnext_blueprint_prepares_identity_before_web_workloads_without_literal_credentials():
    path = REPO_ROOT / "projects" / "chaosatlas-apps" / "erpnext" / "isolation" / "l2-blueprint.json"
    blueprint = json.loads(path.read_text(encoding="utf-8"))
    resources = blueprint["resources"]
    bootstrap_secret = next(
        item for item in resources
        if item.get("kind") == "Secret" and item["metadata"].get("name") == "erpnext-bootstrap-identity"
    )
    assert bootstrap_secret["runtimeGenerate"] == {
        "keys": ["api-key", "api-secret"],
        "templates": {"authorization": "token ${api-key}:${api-secret}"},
    }
    create_site_index = next(
        index for index, item in enumerate(resources)
        if item.get("kind") == "Job" and item["metadata"].get("name") == "erpnext-create-site"
    )
    gunicorn_index = next(
        index for index, item in enumerate(resources)
        if item.get("kind") == "Deployment" and item["metadata"].get("name") == "erpnext-gunicorn"
    )
    assert create_site_index < gunicorn_index
    job = resources[create_site_index]["spec"]["template"]["spec"]
    env = {item["name"]: item["valueFrom"]["secretKeyRef"] for item in job["containers"][0]["env"]}
    assert env["CHAOSATLAS_API_KEY"] == {"name": "erpnext-bootstrap-identity", "key": "api-key"}
    assert env["CHAOSATLAS_API_SECRET"] == {"name": "erpnext-bootstrap-identity", "key": "api-secret"}
    encoded = json.dumps(blueprint, sort_keys=True)
    assert "api-key-value" not in encoded and "api-secret-value" not in encoded
