"""Deterministic first-draft builder for bounded transaction Oracles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from chaosatlas.oracles.transaction_contracts import make_draft, make_v3_draft, validate_draft


def _request(identifier: str, method: str, path: str) -> dict[str, str]:
    return {"id": identifier, "method": method, "path": path}


TEMPLATES: dict[str, dict[str, Any]] = {
    "immich": {
        "oracle_id": "immich-asset-roundtrip-v2",
        "evidence_sources": ["image:immich-server:v2.6.3", "source:asset-media.controller.ts"],
        "credential_refs": [{"id": "immich-test-api-key", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("upload", "POST", "/api/assets"), _request("read", "GET", "/api/assets/{asset_id}"), _request("download", "GET", "/api/assets/{asset_id}/original"), _request("delete", "DELETE", "/api/assets")],
        "steps": [{"id": "upload-synthetic-image", "request_id": "upload", "multipart": {"assetData": "fixture:synthetic_png", "deviceAssetId": "{run_id}-asset", "deviceId": "chaosatlas", "fileCreatedAt": "{fixture_timestamp}", "fileModifiedAt": "{fixture_timestamp}", "isFavorite": "false"}, "capture": {"asset_id": "$.id"}, "idempotency_key": "{run_id}-asset", "on_response_loss": {"strategy": "retry_same_request", "max_attempts": 1, "acceptable_statuses": [200, 201]}}, {"id": "read-metadata", "request_id": "read", "path_variables": {"asset_id": "{asset_id}"}}, {"id": "download-original", "request_id": "download", "path_variables": {"asset_id": "{asset_id}"}}],
        "probe_steps": ["read-metadata", "download-original"],
        "assertions": [{"id": "upload-ok", "step_id": "upload-synthetic-image", "operator": "status_in", "expected": [200, 201]}, {"id": "id-returned", "step_id": "upload-synthetic-image", "operator": "json_path_exists", "path": "$.id"}, {"id": "original-byte-hash", "step_id": "download-original", "operator": "sha256_equals", "expected_from": "fixture_sha256"}],
        "cleanup": {"strategy": "exact_owned_ids", "on_every_exit": True, "steps": [{"id": "delete-owned-asset", "request_id": "delete", "json_body": {"ids": ["{asset_id}"], "force": True}, "required_variables": ["asset_id"], "acceptable_statuses": [204]}, {"id": "confirm-asset-absent", "request_id": "read", "path_variables": {"asset_id": "{asset_id}"}, "required_variables": ["asset_id"], "acceptable_statuses": [404]}]},
    },
    "medusa": {
        "oracle_id": "medusa-cart-lineitem-v2",
        "evidence_sources": ["image:medusa-backend:2.20.1", "source:apps/backend/src"],
        "credential_refs": [{"id": "medusa-publishable-api-key", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("create-cart", "POST", "/store/carts"), _request("add-line", "POST", "/store/carts/{cart_id}/line-items"), _request("read-cart", "GET", "/store/carts/{cart_id}"), _request("delete-line", "DELETE", "/store/carts/{cart_id}/line-items/{line_id}")],
        "steps": [{"id": "create-cart", "request_id": "create-cart", "json_body": {"region_id": "{synthetic_region_id}"}, "capture": {"cart_id": "$.cart.id"}, "on_response_loss": {"strategy": "disposable_environment"}}, {"id": "add-synthetic-variant", "request_id": "add-line", "path_variables": {"cart_id": "{cart_id}"}, "json_body": {"variant_id": "{synthetic_variant_id}", "quantity": 1}, "fixture_refs": ["synthetic_region_id", "synthetic_variant_id"], "capture": {"line_id": "$.cart.items[0].id"}, "on_response_loss": {"strategy": "exact_lookup", "request_id": "read-cart", "path_variables": {"cart_id": "{cart_id}"}, "capture": {"line_id": "$.cart.items[0].id"}}}, {"id": "read-cart", "request_id": "read-cart", "path_variables": {"cart_id": "{cart_id}"}}],
        "probe_steps": ["read-cart"],
        "assertions": [{"id": "quantity", "step_id": "read-cart", "operator": "json_path_equals", "path": "$.cart.items[0].quantity", "expected": 1}, {"id": "currency", "step_id": "read-cart", "operator": "json_path_equals", "path": "$.cart.currency_code", "expected_from": "fixture_currency"}, {"id": "unit-price", "step_id": "read-cart", "operator": "json_path_equals", "path": "$.cart.items[0].unit_price", "expected_from": "fixture_unit_price"}],
        "cleanup": {"strategy": "disposable_environment", "on_every_exit": True, "environment_release_required": True, "steps": [{"id": "delete-owned-line", "request_id": "delete-line", "path_variables": {"cart_id": "{cart_id}", "line_id": "{line_id}"}, "required_variables": ["cart_id", "line_id"], "acceptable_statuses": [200]}], "reason": "No approved Store API cart-delete operation; delete the exact line item, then destroy the disposable database environment."},
    },
    "rocketchat": {
        "oracle_id": "rocketchat-message-roundtrip-v2",
        "evidence_sources": ["image:rocket.chat:8.6.1", "api:channels.create,chat.postMessage,channels.messages,channels.delete"],
        "credential_refs": [{"id": "rocketchat-test-user", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("create-room", "POST", "/api/v1/channels.create"), _request("room-info", "GET", "/api/v1/rooms.info"), _request("post-message", "POST", "/api/v1/chat.postMessage"), _request("read-messages", "GET", "/api/v1/channels.messages"), _request("delete-room", "POST", "/api/v1/channels.delete")],
        "steps": [{"id": "create-owned-room", "request_id": "create-room", "json_body": {"name": "ca-{run_id}"}, "capture": {"room_id": "$.channel._id"}, "on_response_loss": {"strategy": "exact_lookup", "request_id": "room-info", "query": {"roomName": "ca-{run_id}"}, "capture": {"room_id": "$.room._id"}}}, {"id": "post-owned-message", "request_id": "post-message", "json_body": {"roomId": "{room_id}", "text": "ChaosAtlas synthetic {run_id}"}, "capture": {"message_id": "$.message._id"}, "on_response_loss": {"strategy": "exact_lookup", "request_id": "read-messages", "query": {"roomId": "{room_id}", "count": 1}, "capture": {"message_id": "$.messages[0]._id"}}}, {"id": "poll-messages", "request_id": "read-messages", "query": {"roomId": "{room_id}", "count": 20}}],
        "probe_steps": ["poll-messages"],
        "assertions": [{"id": "room-owner", "step_id": "poll-messages", "operator": "json_path_equals", "path": "$.messages[0].rid", "expected_from": "room_id"}, {"id": "message-body", "step_id": "poll-messages", "operator": "json_path_equals", "path": "$.messages[0].msg", "expected": "ChaosAtlas synthetic {run_id}"}, {"id": "async-visible", "step_id": "poll-messages", "operator": "eventually", "assertion_ref": "message-body"}],
        "cleanup": {"strategy": "exact_owned_ids", "on_every_exit": True, "steps": [{"id": "delete-owned-room", "request_id": "delete-room", "json_body": {"roomId": "{room_id}"}, "required_variables": ["room_id"], "acceptable_statuses": [200]}]},
    },
    "erpnext": {
        "oracle_id": "erpnext-todo-crud-v2",
        "evidence_sources": ["image:erpnext:v16.34.1", "api:/api/resource/ToDo"],
        "credential_refs": [{"id": "erpnext-test-api-token", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("create", "POST", "/api/resource/ToDo"), _request("list", "GET", "/api/resource/ToDo"), _request("read", "GET", "/api/resource/ToDo/{todo_name}"), _request("update", "PUT", "/api/resource/ToDo/{todo_name}"), _request("delete", "DELETE", "/api/resource/ToDo/{todo_name}")],
        "steps": [{"id": "create-owned-todo", "request_id": "create", "json_body": {"description": "ChaosAtlas synthetic {run_id}", "status": "Open", "priority": "Low"}, "capture": {"todo_name": "$.data.name"}, "on_response_loss": {"strategy": "exact_lookup", "request_id": "list", "query": {"filters": "[[\"description\",\"=\",\"ChaosAtlas synthetic {run_id}\"]]", "fields": "[\"name\"]", "limit_page_length": 2}, "capture": {"todo_name": "$.data[0].name"}}}, {"id": "read-todo", "request_id": "read", "path_variables": {"todo_name": "{todo_name}"}}, {"id": "update-status", "request_id": "update", "path_variables": {"todo_name": "{todo_name}"}, "json_body": {"status": "Closed"}, "on_response_loss": {"strategy": "retry_same_request", "max_attempts": 1, "acceptable_statuses": [200]}}, {"id": "read-updated-todo", "request_id": "read", "path_variables": {"todo_name": "{todo_name}"}}],
        "probe_steps": ["read-updated-todo"],
        "assertions": [{"id": "description", "step_id": "read-todo", "operator": "json_path_equals", "path": "$.data.description", "expected": "ChaosAtlas synthetic {run_id}"}, {"id": "status-updated", "step_id": "read-updated-todo", "operator": "json_path_equals", "path": "$.data.status", "expected": "Closed"}],
        "cleanup": {"strategy": "exact_owned_ids", "on_every_exit": True, "steps": [{"id": "delete-owned-todo", "request_id": "delete", "path_variables": {"todo_name": "{todo_name}"}, "required_variables": ["todo_name"], "acceptable_statuses": [200, 202]}, {"id": "confirm-todo-absent", "request_id": "read", "path_variables": {"todo_name": "{todo_name}"}, "required_variables": ["todo_name"], "acceptable_statuses": [404]}]},
    },
}


class OracleBuilder:
    def build(self, *, project_id: str, project_revision: str) -> dict[str, Any]:
        if project_id not in TEMPLATES:
            raise ValueError(f"no bounded transaction Oracle template for {project_id}")
        payload = {
            **deepcopy(TEMPLATES[project_id]),
            "project_id": project_id,
            "project_revision": project_revision,
            "timeouts": {"request_s": 10, "eventual_s": 30, "poll_interval_s": 2},
            "ownership": {"marker_field": "chaosatlas_run_id", "synthetic_only": True, "delete_scope": "returned_or_exactly_queried_ids"},
            "approval": {"required": True, "record": None},
        }
        return validate_draft(make_draft(payload))

    def build_v3(self, *, project_id: str, project_revision: str,
                 structured_payload: dict[str, Any]) -> dict[str, Any]:
        """Validate a generated v3 proposal without silently filling semantics.

        Project IDs and source revisions are owned by the builder caller; all
        executable request/ownership/cleanup fields must be supplied explicitly
        and pass the strict v3 validator.
        """
        if not isinstance(structured_payload, dict):
            raise ValueError('structured v3 payload must be an object')
        payload = deepcopy(structured_payload)
        payload['project_id'] = project_id
        payload['project_revision'] = project_revision
        payload.setdefault('approval', {'required': True, 'record': None})
        return validate_draft(make_v3_draft(payload))
