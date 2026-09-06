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


REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_bootstrap_immich_binds_new_user_api_key_without_reporting_credentials():
    environment = FakeEnvironment(
        secrets={
            ("immich-bootstrap-identity", "admin-password"): "admin-password-value",
            ("immich-bootstrap-identity", "user-password"): "user-password-value",
        },
        responses=[
            (200, {"isInitialized": False}),
            (201, {"id": "admin"}),
            (200, {"accessToken": "admin-token"}),
            (201, {"id": "user-1"}),
            (200, {"userId": "user-1", "accessToken": "user-token"}),
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
            ("rocketchat-bootstrap-identity", "admin-password"): "admin-password-value",
            ("rocketchat-bootstrap-identity", "user-password"): "user-password-value",
        },
        responses=[
            (200, {"data": {"authToken": "admin-token", "userId": "admin-id"}}),
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
    _assert_report_has_no_values(report, "admin-password-value", "user-password-value", "admin-token", "user-token")


def test_bootstrap_erpnext_binds_token_and_keeps_session_out_of_report(monkeypatch):
    values = iter(("api-key-value", "api-secret-value"))
    monkeypatch.setattr("chaosatlas.oracles.identity_bootstrap.secrets.token_hex", lambda _size: next(values))
    environment = FakeEnvironment(
        secrets={("erpnext-runtime-secrets", "admin-password"): "admin-password-value"},
        responses=[
            (200, {"message": "Logged In", "__cookie": "sid=session-value"}),
            (200, {"data": {"name": "chaosatlas-oracle@invalid"}}),
            (200, {"data": {"name": "chaosatlas-oracle@invalid"}}),
            (200, {"data": []}),
        ],
    )
    report, fixtures = bootstrap_erpnext(environment)
    assert fixtures == {}
    authorization = "token api-key-value:api-secret-value"
    assert environment.bindings == [(
        "erpnext-transaction-auth", "transaction-todo-user", "chaosatlas-oracle@invalid",
        {"authorization": authorization},
    )]
    _assert_report_has_no_values(report, "admin-password-value", "session-value", authorization)


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
