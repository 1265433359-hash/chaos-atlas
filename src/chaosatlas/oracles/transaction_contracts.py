"""Versioned, non-executable transaction Oracle contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any

from chaosatlas.isolation.contracts import SAFE_ID, canonical_hash, sensitive_paths, verify_hash, with_hash


SCHEMA = "chaosatlas-transaction-oracle-v1"
STATES = {"draft", "validated", "approved", "frozen"}
METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
ASSERTIONS = {"status_equals", "json_path_equals", "json_path_exists", "sha256_equals", "count_equals", "eventually", "body_contains"}


def approval_subject_sha256(contract: dict[str, Any]) -> str:
    subject = deepcopy(contract)
    for key in ("status", "approval", "contract_sha256"):
        subject.pop(key, None)
    return canonical_hash(subject)


def validate_transaction_contract(contract: dict[str, Any]) -> list[str]:
    required = ("schema_version", "oracle_id", "project_id", "project_revision", "status", "evidence_sources", "credential_refs", "allowed_requests", "steps", "assertions", "ownership", "cleanup", "approval", "contract_sha256")
    errors = [f"missing {key}" for key in required if key not in contract]
    if contract.get("schema_version") != SCHEMA:
        errors.append("unknown transaction Oracle schema")
    if not SAFE_ID.fullmatch(str(contract.get("oracle_id") or "")):
        errors.append("unsafe oracle_id")
    if contract.get("status") not in STATES:
        errors.append("invalid Oracle status")
    if sensitive_paths(contract):
        errors.append("credential material is forbidden; use credential_refs")
    requests = contract.get("allowed_requests") if isinstance(contract.get("allowed_requests"), list) else []
    request_ids: set[str] = set()
    for item in requests:
        if isinstance(item, dict) and (str(item.get("path") or "").startswith("//") or "://" in str(item.get("path") or "")):
            errors.append("absolute or host-changing request path is forbidden")
        if not isinstance(item, dict) or item.get("method") not in METHODS or not str(item.get("path") or "").startswith("/") or not SAFE_ID.fullmatch(str(item.get("id") or "")):
            errors.append("invalid allowed request")
            continue
        request_ids.add(str(item["id"]))
    steps = contract.get("steps") if isinstance(contract.get("steps"), list) else []
    if not steps or any(not isinstance(step, dict) or step.get("request_id") not in request_ids for step in steps):
        errors.append("every step must reference an allowed request")
    step_ids = {str(step.get("id")) for step in steps if isinstance(step, dict) and step.get("id")}
    assertions = contract.get("assertions") if isinstance(contract.get("assertions"), list) else []
    if not assertions or any(not isinstance(item, dict) or item.get("operator") not in ASSERTIONS or item.get("step_id") not in step_ids for item in assertions):
        errors.append("invalid or missing assertions")
    cleanup = contract.get("cleanup") if isinstance(contract.get("cleanup"), dict) else {}
    if cleanup.get("strategy") not in {"exact_owned_ids", "disposable_environment"} or not cleanup.get("on_every_exit"):
        errors.append("cleanup must be exact_owned_ids or disposable_environment on every exit")
    approval = contract.get("approval") if isinstance(contract.get("approval"), dict) else {}
    if approval.get("required") is not True:
        errors.append("human approval must be required")
    if contract.get("status") in {"approved", "frozen"}:
        record = approval.get("record") if isinstance(approval.get("record"), dict) else {}
        if record.get("decision") != "approved" or not record.get("reviewer") or not record.get("reviewed_at") or record.get("approved_subject_sha256") != approval_subject_sha256(contract):
            errors.append("approved/frozen Oracle requires a matching human approval record")
    if not verify_hash(contract, "contract_sha256"):
        errors.append("contract hash mismatch")
    return sorted(set(errors))


def validate_draft(contract: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(contract)
    if result.get("status") != "draft":
        raise ValueError("only a draft can enter validation")
    result["status"] = "validated"
    result = with_hash(result, "contract_sha256")
    errors = validate_transaction_contract(result)
    if errors:
        raise ValueError("invalid transaction Oracle: " + "; ".join(errors))
    return result


def record_human_approval(contract: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Record an external human decision; callers must not synthesize this record."""
    if contract.get("status") != "validated":
        raise ValueError("only a validated Oracle can be approved")
    if record.get("decision") != "approved" or not record.get("reviewer") or not record.get("reviewed_at"):
        raise ValueError("a concrete human approval record is required")
    datetime.fromisoformat(str(record["reviewed_at"]))
    result = deepcopy(contract)
    result["approval"]["record"] = {**deepcopy(record), "approved_subject_sha256": approval_subject_sha256(contract)}
    result["status"] = "approved"
    return with_hash(result, "contract_sha256")


def freeze_approved_contract(contract: dict[str, Any]) -> dict[str, Any]:
    """Freeze an already approved contract without changing its approved semantics."""
    if contract.get("status") != "approved":
        raise ValueError("only an approved Oracle can be frozen")
    errors = validate_transaction_contract(contract)
    if errors:
        raise ValueError("invalid approved transaction Oracle: " + "; ".join(errors))
    result = deepcopy(contract)
    result["status"] = "frozen"
    result = with_hash(result, "contract_sha256")
    errors = validate_transaction_contract(result)
    if errors:
        raise ValueError("invalid frozen transaction Oracle: " + "; ".join(errors))
    return result


def make_draft(payload: dict[str, Any]) -> dict[str, Any]:
    value = {"schema_version": SCHEMA, **deepcopy(payload), "status": "draft"}
    value.setdefault("approval", {"required": True, "record": None})
    return with_hash(value, "contract_sha256")


def _json_path(value: Any, path: str) -> Any:
    current = value
    for key, index in re.findall(r"\.([A-Za-z0-9_-]+)|\[([0-9]+)\]", path.removeprefix("$")):
        current = current[int(index)] if index else current[key]
    return current


def evaluate_assertions(contract: dict[str, Any], observations: dict[str, dict[str, Any]], variables: dict[str, Any]) -> dict[str, Any]:
    """Evaluate the bounded assertion DSL without issuing requests or running code."""
    results: dict[str, bool] = {}
    errors: list[str] = []
    for assertion in contract.get("assertions") or []:
        identifier = str(assertion.get("id") or "")
        observation = observations.get(str(assertion.get("step_id") or ""), {})
        operator = assertion.get("operator")
        expected = assertion.get("expected") if "expected" in assertion else variables.get(str(assertion.get("expected_from") or ""))
        try:
            if operator == "status_equals":
                passed = observation.get("status") == expected
            elif operator in {"json_path_equals", "json_path_exists"}:
                actual = _json_path(observation.get("json"), str(assertion.get("path") or ""))
                passed = actual == expected if operator == "json_path_equals" else actual is not None
            elif operator == "sha256_equals":
                passed = observation.get("body_sha256") == expected
            elif operator == "body_contains":
                passed = str(expected) in str(observation.get("body") or "")
            elif operator == "count_equals":
                passed = len(_json_path(observation.get("json"), str(assertion.get("path") or ""))) == int(expected)
            elif operator == "eventually":
                passed = results.get(str(assertion.get("assertion_ref") or ""), False)
            else:
                passed = False
        except (KeyError, IndexError, TypeError, ValueError):
            passed = False
        results[identifier] = passed
        if not passed:
            errors.append(identifier)
    return {"status": "pass" if results and all(results.values()) else "fail", "assertions": results, "failed_assertions": errors}
