import hashlib
from typing import Any

import pytest

from chaosatlas.oracles.builder import OracleBuilder
from chaosatlas.oracles.replay import HttpObservation, ResponseLost, TransactionReplayer
from chaosatlas.oracles.transaction_contracts import freeze_approved_contract, record_human_approval


def frozen(app: str) -> dict[str, Any]:
    contract = OracleBuilder().build(project_id=app, project_revision="revision")
    approved = record_human_approval(
        contract,
        {"decision": "approved", "reviewer": "reviewer", "reviewed_at": "2026-09-06T00:00:00+00:00"},
    )
    return freeze_approved_contract(approved)


class QueueTransport:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    def send(self, **request: Any) -> HttpObservation:
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def response(status: int, payload: Any = None, *, body: bytes | None = None) -> HttpObservation:
    if body is None:
        import json

        body = json.dumps(payload).encode() if payload is not None else b""
    return HttpObservation(status, body)


def test_immich_replay_runs_frozen_requests_and_exact_cleanup_without_leaking_headers():
    png = b"synthetic-png"
    transport = QueueTransport(
        [response(201, {"id": "asset-1"}), response(200, {"id": "asset-1"}), response(200, body=png), response(204), response(404)]
    )
    journal: list[dict[str, Any]] = []
    replayer = TransactionReplayer(
        frozen("immich"),
        transport,
        credential_headers=lambda _ref: {"x-api-key": "canary-runtime-secret"},
        fixtures={
            "synthetic_png": png,
            "fixture_sha256": hashlib.sha256(png).hexdigest(),
            "fixture_timestamp": "2026-09-06T00:00:00.000Z",
        },
        journal=journal.append,
    )
    prepared = replayer.prepare(run_id="ca-immich-1")
    assert prepared["status"] == "prepared"
    cleaned = replayer.cleanup()
    assert cleaned["cleanup_confirmed"] is True
    assert transport.requests[-2]["json_body"] == {"ids": ["asset-1"], "force": True}
    assert transport.requests[-1]["path"] == "/api/assets/asset-1"
    assert "canary-runtime-secret" not in repr(journal)


def test_idempotent_response_loss_retry_recovers_owned_immich_asset():
    png = b"synthetic-png"
    transport = QueueTransport(
        [ResponseLost("lost"), response(200, {"id": "asset-1"}), response(200, {"id": "asset-1"}), response(200, body=png), response(204), response(404)]
    )
    replayer = TransactionReplayer(
        frozen("immich"),
        transport,
        credential_headers=lambda _ref: {"x-api-key": "secret"},
        fixtures={"synthetic_png": png, "fixture_sha256": hashlib.sha256(png).hexdigest(), "fixture_timestamp": "2026-09-06T00:00:00.000Z"},
    )
    assert replayer.prepare(run_id="ca-immich-lost") ["status"] == "prepared"
    assert len([item for item in transport.requests if item["path"] == "/api/assets"]) == 2
    assert replayer.cleanup()["cleanup_confirmed"] is True


def test_rocketchat_exact_lookup_recovers_both_lost_write_responses():
    message = "ChaosAtlas synthetic ca-chat-1"
    transport = QueueTransport(
        [
            ResponseLost("room response lost"),
            response(200, {"room": {"_id": "room-1"}}),
            ResponseLost("message response lost"),
            response(200, {"messages": [{"_id": "message-1", "rid": "room-1", "msg": message}]}),
            response(200, {"messages": [{"_id": "message-1", "rid": "room-1", "msg": message}]}),
            response(200, {"success": True}),
        ]
    )
    replayer = TransactionReplayer(
        frozen("rocketchat"),
        transport,
        credential_headers=lambda _ref: {"X-Auth-Token": "secret", "X-User-Id": "user-1"},
        fixtures={},
    )
    assert replayer.prepare(run_id="ca-chat-1")["status"] == "prepared"
    assert replayer.variables["room_id"] == "room-1"
    assert replayer.variables["message_id"] == "message-1"
    assert replayer.cleanup()["cleanup_confirmed"] is True


def test_eventual_message_visibility_is_bounded_and_retried():
    message = "ChaosAtlas synthetic ca-chat-poll"
    transport = QueueTransport(
        [
            response(200, {"channel": {"_id": "room-1"}}),
            response(200, {"message": {"_id": "message-1"}}),
            response(200, {"messages": []}),
            response(200, {"messages": [{"_id": "message-1", "rid": "room-1", "msg": message}]}),
            response(200, {"success": True}),
        ]
    )
    now = [0.0]

    def advance(seconds: float) -> None:
        now[0] += seconds

    replayer = TransactionReplayer(
        frozen("rocketchat"),
        transport,
        credential_headers=lambda _ref: {"X-Auth-Token": "secret", "X-User-Id": "user-1"},
        fixtures={},
        sleep=advance,
        monotonic=lambda: now[0],
    )
    assert replayer.prepare(run_id="ca-chat-poll")["status"] == "prepared"
    assert len([item for item in transport.requests if item["path"] == "/api/v1/channels.messages"]) == 2
    assert replayer.cleanup()["cleanup_confirmed"] is True


def test_wrong_business_value_is_detected_and_cleanup_runs_immediately():
    transport = QueueTransport(
        [
            response(200, {"data": {"name": "TODO-1"}}),
            response(200, {"data": {"description": "wrong"}}),
            response(200, {"data": {"status": "Closed"}}),
            response(200, {"data": {"status": "Closed"}}),
            response(200),
            response(404),
        ]
    )
    replayer = TransactionReplayer(
        frozen("erpnext"),
        transport,
        credential_headers=lambda _ref: {"Authorization": "token secret"},
        fixtures={},
    )
    result = replayer.prepare(run_id="ca-erp-1")
    assert result["status"] == "oracle_failed"
    assert result["cleanup"]["cleanup_confirmed"] is True
    assert transport.requests[-2]["path"] == "/api/resource/ToDo/TODO-1"


def test_disposable_cleanup_is_not_confirmed_without_environment_release():
    transport = QueueTransport([])
    replayer = TransactionReplayer(
        frozen("medusa"),
        transport,
        credential_headers=lambda _ref: {"x-publishable-api-key": "secret"},
        fixtures={},
    )
    result = replayer.cleanup()
    assert result["status"] == "cleanup_failed"
    assert "disposable environment release not confirmed" in result["errors"]


def test_replayer_rejects_unapproved_or_legacy_contract():
    with pytest.raises(ValueError, match="frozen v2"):
        TransactionReplayer(
            OracleBuilder().build(project_id="immich", project_revision="revision"),
            QueueTransport([]),
            credential_headers=lambda _ref: {"x-api-key": "secret"},
            fixtures={},
        )
