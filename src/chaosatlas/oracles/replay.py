"""Deterministic, bounded replay for frozen transaction Oracle contracts."""

from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import hashlib
import json
import math
import re
import time
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from chaosatlas.oracles.transaction_contracts import SCHEMA, evaluate_assertions, validate_transaction_contract


_VARIABLE = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*)\}")


@dataclass(frozen=True)
class HttpObservation:
    status: int
    body: bytes = b""
    headers: dict[str, str] | None = None

    def as_assertion_value(self) -> dict[str, Any]:
        parsed = None
        try:
            parsed = json.loads(self.body.decode("utf-8")) if self.body else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
        return {
            "status": self.status,
            "json": parsed,
            "body": self.body.decode("utf-8", errors="replace") if len(self.body) <= 65536 else "",
            "body_sha256": hashlib.sha256(self.body).hexdigest(),
        }


class HttpTransport(Protocol):
    def send(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any],
        json_body: Any,
        multipart: dict[str, Any],
        headers: dict[str, str],
        timeout_s: float,
    ) -> HttpObservation: ...


class ResponseLost(RuntimeError):
    """The request may have committed, but no complete response was received."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


class UrllibHttpTransport:
    """Origin-pinned HTTP transport with proxies and redirects disabled."""

    def __init__(self, base_url: str, *, max_response_bytes: int = 4 * 1024 * 1024) -> None:
        if any(ord(c) < 33 or c == '\\' for c in base_url):
            raise ValueError('unsafe HTTP origin')
        parsed = urlsplit(str(base_url))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.path not in {"", "/"} or parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment or '?' in base_url or '#' in base_url:
            raise ValueError("base_url must be an HTTP(S) origin without a path")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError('invalid origin port')
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 4194304:
            raise ValueError('invalid response bound')
        self.base_url = f"{parsed.scheme}://{parsed.netloc}"
        self.max_response_bytes = int(max_response_bytes)
        self._opener = build_opener(ProxyHandler({}), _NoRedirect())

    @staticmethod
    def _multipart(fields: dict[str, Any]) -> tuple[bytes, str]:
        boundary = "----chaosatlas-oracle-boundary"
        chunks: list[bytes] = []
        for name, value in fields.items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', name):
                raise ValueError('unsafe multipart field name')
            chunks.append(f"--{boundary}\r\n".encode())
            if isinstance(value, bytes):
                chunks.append(f'Content-Disposition: form-data; name="{name}"; filename="synthetic.png"\r\n'.encode())
                chunks.append(b"Content-Type: image/png\r\n\r\n")
                chunks.append(value)
            else:
                chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n{value}'.encode())
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        return b"".join(chunks), f"multipart/form-data; boundary={boundary}"

    def send(
        self,
        *,
        method: str,
        path: str,
        query: dict[str, Any],
        json_body: Any,
        multipart: dict[str, Any],
        headers: dict[str, str],
        timeout_s: float,
    ) -> HttpObservation:
        if not path.startswith("/") or any(x in path for x in ('//', '://', '\\', '?', '#', '{', '}')) or any(ord(x) < 33 for x in path) or any(x in {'.', '..'} for x in path.split('/')):
            raise ValueError("request path escaped the frozen origin")
        if type(timeout_s) not in {float, int} or not math.isfinite(timeout_s) or not 0 < timeout_s <= 30:
            raise ValueError('invalid HTTP timeout')
        validate_auth_headers(headers)
        suffix = "?" + urlencode(query, doseq=True) if query else ""
        body: bytes | None = None
        request_headers = dict(headers)
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        elif multipart:
            body, content_type = self._multipart(multipart)
            request_headers["Content-Type"] = content_type
        if body is not None and len(body) > 4194304:
            raise ValueError('request exceeded bounded Oracle limit')
        request = Request(self.base_url + path + suffix, data=body, headers=request_headers, method=method)
        try:
            response = self._opener.open(request, timeout=float(timeout_s))
            with response:
                response_body = response.read(self.max_response_bytes + 1)
            if len(response_body) > self.max_response_bytes:
                raise ValueError("response exceeded bounded Oracle limit")
            return HttpObservation(int(response.status), response_body, dict(response.headers.items()))
        except HTTPError as exc:
            with exc:
                response_body = exc.read(self.max_response_bytes + 1)
            if len(response_body) > self.max_response_bytes:
                raise ValueError('error response exceeded bounded Oracle limit')
            return HttpObservation(int(exc.code), response_body, dict(exc.headers.items()))
        except (OSError, TimeoutError) as exc:
            raise ResponseLost("request outcome is unknown") from exc


def validate_auth_headers(headers: dict[str, str]) -> None:
    allowed = {'authorization', 'x-api-key', 'x-auth-token', 'x-user-id', 'x-publishable-api-key'}
    if len({k.lower() for k in headers}) != len(headers):
        raise ValueError('duplicate authentication header')
    for name, value in headers.items():
        if name.lower() not in allowed or not isinstance(value, str) or not value or len(value) > 8192 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ValueError('invalid or reserved authentication header')


def render_path(path: str, variables: dict[str, Any]) -> str:
    def segment(match: re.Match[str]) -> str:
        value = variables.get(match.group(1))
        if not isinstance(value, str) or not value or len(value) > 256 or value in {'.', '..'} or any(c in value for c in '/\\%?#') or any(ord(c) < 33 for c in value):
            raise ValueError('invalid single path-segment identity')
        return quote(value, safe='')
    rendered = _VARIABLE.sub(segment, path)
    if '{' in rendered or '}' in rendered:
        raise ValueError('unresolved path placeholder')
    return rendered


def _render(value: Any, variables: dict[str, Any], fixtures: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _render(item, variables, fixtures) for key, item in value.items()}
    if isinstance(value, list):
        return [_render(item, variables, fixtures) for item in value]
    if not isinstance(value, str):
        return value
    if value.startswith("fixture:"):
        key = value.split(":", 1)[1]
        if key not in fixtures:
            raise ValueError(f"missing fixture: {key}")
        return fixtures[key]

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in variables:
            raise ValueError(f"missing Oracle variable: {key}")
        return str(variables[key])

    return _VARIABLE.sub(replace, value)


class TransactionReplayer:
    """Execute only requests encoded in one frozen v2 contract."""

    def __init__(
        self,
        contract: dict[str, Any],
        transport: HttpTransport,
        *,
        credential_headers: Callable[[str], dict[str, str]],
        fixtures: dict[str, Any],
        journal: Callable[[dict[str, Any]], None] | None = None,
        environment_releaser: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        errors = validate_transaction_contract(contract)
        if errors:
            raise ValueError("invalid transaction Oracle: " + "; ".join(errors))
        if contract.get("schema_version") != SCHEMA or contract.get("status") != "frozen":
            raise ValueError("deterministic replay requires a frozen v2 Oracle")
        if isinstance(transport, UrllibHttpTransport):
            raise ValueError('v2 live replay disabled: v3 ownership ledger and runtime binding required')
        contract = deepcopy(contract)
        self.contract = contract
        self.transport = transport
        captured = {key for step in contract['steps'] for key in (step.get('capture') or {})}
        reserved = captured | {'run_id', 'lease_id', 'principal_id', 'attempt_id'}
        if reserved.intersection(fixtures):
            raise ValueError('fixture cannot supply reserved identity or capture variables')
        self.fixtures = deepcopy(fixtures)
        self.journal = journal or (lambda _event: None)
        self.environment_releaser = environment_releaser
        self._sleep = sleep
        self._monotonic = monotonic
        self.variables: dict[str, Any] = {}
        self.observations: dict[str, dict[str, Any]] = {}
        self._write_states: dict[str, str] = {}
        self._requests = {str(item["id"]): item for item in contract["allowed_requests"]}
        self._steps = {str(item["id"]): item for item in contract["steps"]}
        headers: dict[str, str] = {}
        for reference in contract.get("credential_refs") or []:
            resolved = credential_headers(str(reference["id"]))
            if not isinstance(resolved, dict) or not resolved:
                raise ValueError(f"credential ref did not resolve to headers: {reference['id']}")
            headers.update({str(key): str(value) for key, value in resolved.items()})
        validate_auth_headers(headers)
        self._headers = headers

    def _emit(self, event: str, step: dict[str, Any], **fields: Any) -> None:
        request = self._requests[str(step["request_id"])]
        payload = {
            "schema_version": "chaosatlas-transaction-journal-v1",
            "event": event,
            "step_id": str(step.get("id") or ""),
            "request_id": str(step["request_id"]),
            "method": str(request["method"]),
            **fields,
        }
        self.journal(payload)

    def _capture(self, step: dict[str, Any], observation: dict[str, Any]) -> None:
        from chaosatlas.oracles.transaction_contracts import _json_path

        for name, path in (step.get("capture") or {}).items():
            self.variables[str(name)] = _json_path(observation.get("json"), str(path))

    def _send(self, step: dict[str, Any]) -> dict[str, Any]:
        request = self._requests.get(str(step.get("request_id") or ""))
        if request is None:
            raise ValueError("step references a request outside the frozen allow-list")
        path = render_path(request["path"], self.variables)
        query = _render(step.get("query") or {}, self.variables, self.fixtures)
        json_body = _render(step.get("json_body"), self.variables, self.fixtures)
        multipart = _render(step.get("multipart") or {}, self.variables, self.fixtures)
        self._emit("request_intent", step, path_sha256=hashlib.sha256(path.encode()).hexdigest())
        if request['method'] != 'GET':
            self._write_states[str(step['id'])] = 'outcome_unknown'
        response = self.transport.send(
            method=str(request["method"]),
            path=str(path),
            query=query,
            json_body=json_body,
            multipart=multipart,
            headers=dict(self._headers),
            timeout_s=float((self.contract.get("timeouts") or {}).get("request_s") or 10),
        )
        observation = response.as_assertion_value()
        self._emit("response", step, status=response.status, body_sha256=observation["body_sha256"])
        return observation

    def _recover_response_loss(self, step: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        recovery = step.get("on_response_loss") or {}
        strategy = recovery.get("strategy")
        self._emit("response_lost", step, recovery_strategy=strategy)
        if strategy == "retry_same_request":
            observation = self._send(step)
            acceptable = recovery.get("acceptable_statuses") or list(range(200, 300))
            if observation["status"] not in acceptable:
                raise ResponseLost("bounded idempotent retry did not recover the response")
            return observation, False
        if strategy == "exact_lookup":
            lookup = {"id": f"{step['id']}-response-loss-lookup", **recovery}
            lookup.pop("strategy", None)
            lookup.pop("max_attempts", None)
            observation = self._send(lookup)
            if not 200 <= int(observation["status"]) < 300:
                raise ResponseLost("exact ownership lookup did not recover the response")
            self._capture(lookup, observation)
            return observation, True
        raise ResponseLost("write outcome requires disposable environment cleanup")

    def _execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        captured_by_recovery = False
        try:
            observation = self._send(step)
        except ResponseLost:
            observation, captured_by_recovery = self._recover_response_loss(step)
        if not captured_by_recovery:
            self._capture(step, observation)
        if 200 <= int(observation['status']) < 300 and str(step['id']) in self._write_states:
            self._write_states[str(step['id'])] = 'cleanup_pending'
        self.observations[str(step["id"])] = observation
        return observation

    def _execute_with_polling(self, step: dict[str, Any]) -> dict[str, Any]:
        step_id = str(step["id"])
        assertions = [item for item in self.contract["assertions"] if item.get("step_id") == step_id]
        if not any(item.get("operator") == "eventually" for item in assertions):
            return self._execute_step(step)
        deadline = self._monotonic() + float((self.contract.get("timeouts") or {}).get("eventual_s") or 0)
        while True:
            observation = self._execute_step(step)
            direct = [item for item in assertions if item.get("operator") != "eventually"]
            scoped = {**self.contract, "assertions": direct}
            if direct and evaluate_assertions(scoped, self.observations, self.variables)["status"] == "pass":
                return observation
            if self._monotonic() >= deadline:
                return observation
            self._sleep(float((self.contract.get("timeouts") or {}).get("poll_interval_s") or 1))

    def prepare(self, *, run_id: str) -> dict[str, Any]:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", run_id):
            raise ValueError("unsafe transaction run_id")
        if self._write_states:
            raise ValueError('existing write operations require recovery before a new prepare')
        self.variables = {"run_id": run_id, **{key: value for key, value in self.fixtures.items() if not isinstance(value, bytes)}}
        self.observations = {}
        try:
            for step in self.contract["steps"]:
                self._execute_with_polling(step)
            evaluated = evaluate_assertions(self.contract, self.observations, self.variables)
            if evaluated["status"] != "pass":
                cleanup = self.cleanup()
                return {"status": "oracle_failed", "assertion_result": evaluated["status"], "assertions": evaluated["assertions"], "failed_assertions": evaluated["failed_assertions"], "cleanup": cleanup}
            return {"status": "prepared", "assertion_result": evaluated["status"], "assertions": evaluated["assertions"], "failed_assertions": evaluated["failed_assertions"]}
        except BaseException as exc:
            cleanup = self.cleanup()
            if not isinstance(exc, Exception):
                raise
            return {"status": "prepare_failed", "error_type": type(exc).__name__, "cleanup": cleanup}

    def probe(self, phase: str) -> dict[str, Any]:
        for step_id in self.contract["probe_steps"]:
            self._execute_with_polling(self._steps[str(step_id)])
        evaluated = evaluate_assertions(self.contract, self.observations, self.variables)
        return {"status": evaluated["status"], "phase": phase, **evaluated}

    def cleanup(self) -> dict[str, Any]:
        errors: list[str] = [f'unresolved write: {key}' for key, state in self._write_states.items() if state == 'outcome_unknown']
        executed: list[str] = []
        for step in (self.contract.get("cleanup") or {}).get("steps") or []:
            required = {str(item) for item in step.get("required_variables") or []}
            if not required.issubset(self.variables):
                if any(state == 'outcome_unknown' for state in self._write_states.values()):
                    errors.append(f"missing ownership variables for {step['id']}")
                continue
            try:
                observation = self._send(step)
                executed.append(str(step["id"]))
                if observation["status"] not in step["acceptable_statuses"]:
                    errors.append(f"unexpected cleanup status for {step['id']}: {observation['status']}")
            except Exception as exc:
                errors.append(f"{step['id']}: {type(exc).__name__}")
        environment_released = None
        if (self.contract.get("cleanup") or {}).get("environment_release_required"):
            environment_released = bool(self.environment_releaser and self.environment_releaser())
            if not environment_released:
                errors.append("disposable environment release not confirmed")
        return {
            "status": "cleaned" if not errors else "cleanup_failed",
            "cleanup_confirmed": not errors,
            "executed_steps": executed,
            "environment_released": environment_released,
            "errors": errors,
        }


class TransactionWorkflowOracle:
    """Expose one replayer through the shared WorkflowOracle lifecycle."""

    def __init__(self, replayer: TransactionReplayer) -> None:
        self.replayer = replayer
        self._journal_events = 0

    def prepare_fixture(self, run_context: dict[str, Any]) -> dict[str, Any]:
        return self.replayer.prepare(run_id=str(run_context["run_id"]))

    def probe(self, phase: str, _run_context: dict[str, Any]) -> dict[str, Any]:
        return self.replayer.probe(phase)

    def collect_evidence(self, _run_context: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "collected",
            "oracle_kind": "transaction_http",
            "contract_sha256": self.replayer.contract["contract_sha256"],
            "captured_variables": sorted(self.replayer.variables),
        }

    def cleanup_fixture(self, _run_context: dict[str, Any]) -> dict[str, Any]:
        return self.replayer.cleanup()
