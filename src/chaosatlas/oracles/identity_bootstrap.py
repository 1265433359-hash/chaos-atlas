"""Lease-scoped synthetic identity initialization for transaction Oracles."""

from __future__ import annotations

import base64
from copy import deepcopy
from dataclasses import dataclass
import hmac
import json
import re
import socket
import subprocess
import threading
import time
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from chaosatlas.isolation.manager import IsolationManager


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(frozen=True)
class BootstrapResponse:
    status: int
    json: dict[str, Any]
    headers: dict[str, str]
    method: str = ""
    path: str = ""


class IdentityEnvironment(Protocol):
    def read_secret(self, name: str, key: str) -> str: ...
    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None,
                headers: dict[str, str] | None = None,
                query: dict[str, Any] | None = None) -> BootstrapResponse: ...
    def postgres_json(self, sql: str) -> dict[str, Any]: ...
    def bind_secret(self, name: str, role: str, principal_id: str,
                    values: dict[str, str]) -> dict[str, Any]: ...


def _body(response: BootstrapResponse, *statuses: int) -> dict[str, Any]:
    if response.status not in statuses or not isinstance(response.json, dict):
        location = f" for {response.method} {response.path}" if response.method and response.path else ""
        raise ValueError(f"identity bootstrap HTTP status was {response.status}{location}")
    return response.json


def _bearer(value: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + value}


def _erpnext_authorization_check(
    environment: IdentityEnvironment, authorizations: list[str], *, attempts: int = 11,
) -> tuple[BootstrapResponse, str]:
    if not authorizations or attempts < 1:
        raise ValueError("ERPNext authorization check requires bounded candidates")
    response = None
    authorization = authorizations[0]
    for attempt in range(attempts):
        authorization = authorizations[attempt % len(authorizations)]
        response = environment.request(
            "GET", "/api/resource/ToDo", headers={"Authorization": authorization},
            query={"limit_page_length": 1},
        )
        if response.status not in {401, 502, 503, 504} or attempt == attempts - 1:
            break
        time.sleep(3)
    assert response is not None
    return response, authorization


def _erpnext_authorization_stability(
    environment: IdentityEnvironment, authorization: str, *,
    required_successes: int = 12, attempts: int = 60,
) -> int:
    if required_successes < 1 or attempts < required_successes:
        raise ValueError("ERPNext authorization stability requires bounded checks")
    consecutive = 0
    for attempt in range(attempts):
        response, _ = _erpnext_authorization_check(
            environment, [authorization], attempts=1,
        )
        if response.status == 200:
            consecutive += 1
            if consecutive == required_successes:
                return consecutive
        elif response.status in {401, 502, 503, 504}:
            consecutive = 0
        else:
            raise ValueError(
                f"ERPNext authorization stability HTTP status was {response.status}"
            )
        if attempt < attempts - 1:
            time.sleep(1)
    raise ValueError("ERPNext authorization did not reach the bounded stability gate")


def bootstrap_immich(environment: IdentityEnvironment) -> tuple[dict[str, Any], dict[str, Any]]:
    admin_email, user_email = "chaosatlas-admin@invalid", "chaosatlas-oracle@invalid"
    admin_password = environment.read_secret("immich-bootstrap-identity", "admin-password")
    user_password = environment.read_secret("immich-bootstrap-identity", "user-password")
    config = _body(environment.request("GET", "/api/server/config"), 200)
    if config.get("isInitialized") is not True:
        _body(environment.request("POST", "/api/auth/admin-sign-up", body={
            "email": admin_email, "password": admin_password, "name": "ChaosAtlas Bootstrap",
        }), 201)
    admin_login = _body(environment.request("POST", "/api/auth/login", body={
        "email": admin_email, "password": admin_password,
    }), 201)
    admin_token = str(admin_login.get("accessToken") or "")
    created = environment.request("POST", "/api/admin/users", headers=_bearer(admin_token), body={
        "email": user_email, "password": user_password, "name": "ChaosAtlas Oracle",
    })
    if created.status not in {201, 400}:
        _body(created, 201)
    user_login = _body(environment.request("POST", "/api/auth/login", body={
        "email": user_email, "password": user_password,
    }), 201)
    principal_id = str(user_login.get("userId") or "")
    user_token = str(user_login.get("accessToken") or "")
    key = _body(environment.request("POST", "/api/api-keys", headers=_bearer(user_token), body={
        "name": "ChaosAtlas transaction",
        "permissions": ["asset.upload", "asset.read", "asset.download"],
    }), 201)
    secret = str(key.get("secret") or "")
    if not principal_id or not secret:
        raise ValueError("Immich did not return a bounded principal and API key")
    binding = environment.bind_secret(
        "immich-transaction-auth", "transaction-test-user", principal_id, {"x-api-key": secret},
    )
    return {
        "project_id": "immich", "status": "initialized", "principal_id": principal_id,
        "principal_role": "transaction-test-user", "notifications_enabled": False,
        "credential_binding": binding,
    }, {}


def bootstrap_rocketchat(environment: IdentityEnvironment) -> tuple[dict[str, Any], dict[str, Any]]:
    user_password = environment.read_secret("rocketchat-bootstrap-identity", "user-password")
    created = _body(environment.request("POST", "/api/v1/users.register", body={
        "name": "ChaosAtlas Oracle", "email": "chaosatlas-oracle@example.com",
        "username": "chaosatlas-oracle", "pass": user_password,
    }), 200)
    registered_id = str((created.get("user") or {}).get("_id") or "")
    user = _body(environment.request("POST", "/api/v1/login", body={
        "user": "chaosatlas-oracle", "password": user_password,
    }), 200).get("data") or {}
    principal_id = str(user.get("userId") or "")
    token = str(user.get("authToken") or "")
    if not principal_id or principal_id != registered_id or not token:
        raise ValueError("Rocket.Chat did not return a bounded user token")
    binding = environment.bind_secret(
        "rocketchat-transaction-auth", "transaction-test-user", principal_id,
        {"x-auth-token": token, "x-user-id": principal_id},
    )
    return {
        "project_id": "rocketchat", "status": "initialized", "principal_id": principal_id,
        "principal_role": "transaction-test-user", "notifications_enabled": False,
        "credential_binding": binding,
    }, {}


def bootstrap_erpnext(environment: IdentityEnvironment) -> tuple[dict[str, Any], dict[str, Any]]:
    principal_id = "chaosatlas-oracle@example.com"
    token_authorization = environment.read_secret(
        "erpnext-bootstrap-identity", "authorization",
    )
    if not token_authorization.startswith("token "):
        raise ValueError("ERPNext bootstrap token scheme is invalid")
    authorization_check, authorization = _erpnext_authorization_check(
        environment, [token_authorization],
    )
    if authorization_check.status != 200:
        raise ValueError(
            f"ERPNext pre-web API credential verification failed with HTTP {authorization_check.status}"
        )
    binding = environment.bind_secret(
        "erpnext-transaction-auth", "transaction-todo-user", principal_id,
        {"authorization": authorization},
    )
    persisted_authorization = environment.read_secret("erpnext-transaction-auth", "authorization")
    if not hmac.compare_digest(persisted_authorization, authorization):
        raise ValueError("ERPNext transaction credential changed during Secret binding")
    stability_checks = _erpnext_authorization_stability(
        environment, persisted_authorization,
    )
    return {
        "project_id": "erpnext", "status": "initialized", "principal_id": principal_id,
        "principal_role": "transaction-todo-user", "notifications_enabled": False,
        "credential_binding": binding,
        "authorization_stability_checks": stability_checks,
    }, {}


def bootstrap_medusa(environment: IdentityEnvironment) -> tuple[dict[str, Any], dict[str, Any]]:
    key = environment.postgres_json(MEDUSA_KEY_QUERY)
    token = str(key.get("token") or "")
    principal_id = str(key.get("sales_channel_id") or "")
    headers = {"X-Publishable-Api-Key": token}
    regions = _body(environment.request("GET", "/store/regions", headers=headers,
                                        query={"limit": 1}), 200).get("regions") or []
    if len(regions) != 1:
        raise ValueError("Medusa seed did not expose exactly one selected region")
    region = regions[0]
    products = _body(environment.request("GET", "/store/products", headers=headers, query={
        "limit": 1, "region_id": region.get("id"),
        "fields": "+variants.calculated_price",
    }), 200).get("products") or []
    variants = products[0].get("variants") if len(products) == 1 else []
    variant = variants[0] if isinstance(variants, list) and variants else {}
    price = variant.get("calculated_price") or {}
    fixtures = {
        "synthetic_region_id": str(region.get("id") or ""),
        "synthetic_variant_id": str(variant.get("id") or ""),
        "fixture_currency": str(region.get("currency_code") or ""),
        "fixture_unit_price": price.get("calculated_amount"),
    }
    if not token or not principal_id or any(value in {None, ""} for value in fixtures.values()):
        raise ValueError("Medusa seed facts are incomplete")
    binding = environment.bind_secret(
        "medusa-transaction-auth", "transaction-sales-channel", principal_id,
        {"x-publishable-api-key": token},
    )
    return {
        "project_id": "medusa", "status": "initialized", "principal_id": principal_id,
        "principal_role": "transaction-sales-channel", "notifications_enabled": False,
        "credential_binding": binding,
    }, fixtures


BOOTSTRAPPERS = {
    "immich": bootstrap_immich,
    "medusa": bootstrap_medusa,
    "rocketchat": bootstrap_rocketchat,
    "erpnext": bootstrap_erpnext,
}


MEDUSA_KEY_QUERY = (
    "select json_build_object('token',a.token,'api_key_id',a.id,'sales_channel_id',l.sales_channel_id)::text "
    "from api_key a join publishable_api_key_sales_channel l on l.publishable_key_id=a.id "
    "where a.type='publishable' and a.revoked_at is null and a.deleted_at is null order by a.created_at limit 1"
)


class KubernetesIdentityEnvironment:
    """Exact-lease implementation. Credentials stay in memory and kubectl stdin."""

    def __init__(self, manager: IsolationManager, lease_id: str, *, service: str, port: int):
        self.manager, self.lease_id, self.service, self.port = manager, lease_id, service, port
        self.lease = manager.store.load(lease_id)
        if self.lease.get("state") != "ready" or self.lease["plan"].get("mode") == "adopted-test-replica":
            raise ValueError("identity bootstrap requires a ready disposable lease")
        self.namespace = str(self.lease.get("target_name") or "")
        self.provider = manager.providers.get(self.lease["provider"])
        self._process: subprocess.Popen | None = None
        self._origin = ""
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _registered(self, kind: str, name: str) -> dict[str, Any]:
        matches = [item for item in self.lease.get("resources") or []
                   if item.get("kind") == kind and item.get("namespace") == self.namespace and item.get("name") == name]
        if len(matches) != 1 or not matches[0].get("actual_uid"):
            raise ValueError("bootstrap resource is outside the lease")
        return matches[0]

    def open(self) -> None:
        self._registered("Service", self.service)
        ready, ports = threading.Event(), []
        context = str(self.lease.get("runtime_locator", {}).get("kube_context") or "")
        self._process = subprocess.Popen(
            ["kubectl", "--context", context, "-n", self.namespace, "port-forward",
             f"svc/{self.service}", f":{self.port}", "--address", "127.0.0.1"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        def consume():
            assert self._process and self._process.stdout
            for line in self._process.stdout:
                match = re.search(r"Forwarding from 127\.0\.0\.1:(\d+)", line)
                if match:
                    ports.append(int(match.group(1)))
                    ready.set()
            ready.set()
        threading.Thread(target=consume, daemon=True).start()
        if not ready.wait(30) or not ports:
            self.close()
            raise ValueError("bootstrap service tunnel unavailable")
        self._origin = f"http://127.0.0.1:{ports[0]}"

    def close(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
            if self._process.stdout:
                self._process.stdout.close()
            self._process = None

    def _secret(self, name: str) -> dict[str, Any]:
        registered = self._registered("Secret", name)
        value, error = self.provider._json(
            self.lease["plan"], ["-n", self.namespace, "get", "secret", name], lease=self.lease,
        )
        metadata = (value or {}).get("metadata") or {}
        if error or metadata.get("uid") != registered["actual_uid"] or metadata.get("namespace") != self.namespace:
            raise ValueError("bootstrap Secret identity changed")
        if any((metadata.get("labels") or {}).get(key) != str(expected)
               for key, expected in (self.lease.get("owner_labels") or {}).items()):
            raise ValueError("bootstrap Secret lost lease ownership")
        return value or {}

    def read_secret(self, name: str, key: str) -> str:
        try:
            value = base64.b64decode(self._secret(name)["data"][key], validate=True).decode("utf-8")
        except (KeyError, ValueError, UnicodeError, TypeError):
            raise ValueError("bootstrap Secret key unavailable") from None
        if not value or len(value) > 8192 or any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("bootstrap Secret value is invalid")
        return value

    def request(self, method: str, path: str, *, body: dict[str, Any] | None = None,
                headers: dict[str, str] | None = None,
                query: dict[str, Any] | None = None) -> BootstrapResponse:
        if not self._origin or not re.fullmatch(r"/[A-Za-z0-9_./%=-]+", path) or ".." in path:
            raise ValueError("unsafe bootstrap request path")
        url = self._origin + path + (("?" + urlencode(query)) if query else "")
        data = json.dumps(body, separators=(",", ":")).encode() if body is not None else None
        request_headers = dict(headers or {})
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request = Request(url, data=data, headers=request_headers, method=method)
        try:
            response = self._opener.open(request, timeout=60)
        except HTTPError as exc:
            response = exc
        except (TimeoutError, socket.timeout) as exc:
            raise ValueError(f"bootstrap request timed out: {method} {path}") from exc
        with response:
            payload = response.read(1048577)
            cookie_values = response.headers.get_all("Set-Cookie") or []
            response_headers = dict(response.headers.items())
            status = int(response.status)
        if len(payload) > 1048576:
            raise ValueError("bootstrap response exceeded bound")
        try:
            parsed = json.loads(payload.decode("utf-8")) if payload else {}
        except (UnicodeError, json.JSONDecodeError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        for cookie in cookie_values:
            match = re.search(r"(?:^|[,;]\s*)sid=([^;,\s]+)", cookie)
            if match:
                parsed["__cookie"] = "sid=" + match.group(1)
                break
        return BootstrapResponse(status, parsed, response_headers, method, path)

    def postgres_json(self, sql: str) -> dict[str, Any]:
        if self.lease.get("project_id") != "medusa" or sql != MEDUSA_KEY_QUERY:
            raise ValueError("only the reviewed Medusa metadata query is allowed")
        command = (
            'PGPASSWORD="$POSTGRES_PASSWORD" psql -U medusa -d medusa -Atc "'
            + sql.replace('"', '\\"')
            + '"'
        )
        code, stdout, _ = self.provider._run(
            self.lease["plan"], ["-n", self.namespace, "exec", "statefulset/medusa-postgres", "--",
                                 "sh", "-lc", command,
                                 ], lease=self.lease,
        )
        if code != 0 or not stdout:
            raise ValueError("Medusa bootstrap metadata query failed")
        try:
            value = json.loads(stdout.strip())
        except json.JSONDecodeError:
            raise ValueError("Medusa bootstrap metadata response invalid") from None
        return value if isinstance(value, dict) else {}

    def bind_secret(self, name: str, role: str, principal_id: str,
                    values: dict[str, str]) -> dict[str, Any]:
        current = self._secret(name)
        registered = self._registered("Secret", name)
        if not principal_id or len(principal_id) > 256 or not values:
            raise ValueError("invalid transaction principal binding")
        if any(not isinstance(value, str) or not value or len(value) > 8192 for value in values.values()):
            raise ValueError("invalid transaction credential value")
        metadata = current.get("metadata") or {}
        annotations = metadata.get("annotations") or {}
        if annotations.get("chaosatlas.dev/principal-role") != role:
            raise ValueError("transaction credential Secret role mismatch")
        if set(current.get("data") or {}) != set(values):
            raise ValueError("transaction credential Secret keys mismatch")
        manifest = {
            "apiVersion": "v1", "kind": "Secret", "type": "Opaque",
            "metadata": {
                "name": name, "namespace": self.namespace,
                "labels": deepcopy(metadata.get("labels") or {}),
                "annotations": {
                    **deepcopy(annotations),
                    "chaosatlas.dev/principal-role": role,
                    "chaosatlas.dev/principal-id": principal_id,
                },
            },
            "stringData": deepcopy(values),
        }
        code, _, _ = self.provider._run(
            self.lease["plan"], ["apply", "-f", "-"], lease=self.lease,
            input_text=json.dumps(manifest),
        )
        if code != 0:
            raise ValueError("transaction credential Secret update failed")
        verified = self._secret(name)
        if (verified.get("metadata") or {}).get("uid") != registered["actual_uid"] or set(verified.get("data") or {}) != set(values):
            raise ValueError("transaction credential Secret verification failed")
        return {
            "secret_name": name, "secret_uid": registered["actual_uid"],
            "key_names": sorted(values), "binding_source": "lease_owned_secret_ref",
        }
