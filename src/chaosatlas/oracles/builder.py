"""Deterministic first-draft builder for bounded transaction Oracles."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from chaosatlas.oracles.transaction_contracts import make_draft, validate_draft


def _request(identifier: str, method: str, path: str) -> dict[str, str]:
    return {"id": identifier, "method": method, "path": path}


TEMPLATES: dict[str, dict[str, Any]] = {
    "immich": {
        "oracle_id": "immich-asset-roundtrip-v1",
        "evidence_sources": ["image:immich-server:v2.6.3", "source:asset-media.controller.ts"],
        "credential_refs": [{"id": "immich-test-api-key", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("upload", "POST", "/api/assets"), _request("read", "GET", "/api/assets/{asset_id}"), _request("download", "GET", "/api/assets/{asset_id}/original"), _request("delete", "DELETE", "/api/assets")],
        "steps": [{"id": "upload-synthetic-image", "request_id": "upload", "multipart": {"assetData": "fixture:synthetic_png", "deviceAssetId": "{run_id}-asset", "deviceId": "chaosatlas", "fileCreatedAt": "fixture_timestamp", "fileModifiedAt": "fixture_timestamp", "isFavorite": "false"}, "capture": {"asset_id": "$.id"}, "idempotency_key": "{run_id}-asset"}, {"id": "read-metadata", "request_id": "read", "path_variables": {"asset_id": "{asset_id}"}}, {"id": "download-original", "request_id": "download", "path_variables": {"asset_id": "{asset_id}"}}],
        "assertions": [{"id": "upload-ok", "step_id": "upload-synthetic-image", "operator": "status_equals", "expected": 201}, {"id": "id-returned", "step_id": "upload-synthetic-image", "operator": "json_path_exists", "path": "$.id"}, {"id": "original-byte-hash", "step_id": "download-original", "operator": "sha256_equals", "expected_from": "fixture_sha256"}],
        "cleanup": {"strategy": "exact_owned_ids", "request_id": "delete", "on_every_exit": True, "lookup_after_lost_response": {"field": "deviceAssetId", "value": "{run_id}-asset"}},
    },
    "medusa": {
        "oracle_id": "medusa-cart-lineitem-v1",
        "evidence_sources": ["image:medusa-backend:2.20.1", "source:apps/backend/src"],
        "credential_refs": [{"id": "medusa-publishable-api-key", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("create-cart", "POST", "/store/carts"), _request("add-line", "POST", "/store/carts/{cart_id}/line-items"), _request("read-cart", "GET", "/store/carts/{cart_id}"), _request("delete-line", "DELETE", "/store/carts/{cart_id}/line-items/{line_id}")],
        "steps": [{"id": "create-cart", "request_id": "create-cart", "json_body": {"region_id": "{synthetic_region_id}"}, "capture": {"cart_id": "$.cart.id"}}, {"id": "add-synthetic-variant", "request_id": "add-line", "path_variables": {"cart_id": "{cart_id}"}, "json_body": {"variant_id": "{synthetic_variant_id}", "quantity": 1}, "fixture_refs": ["synthetic_region_id", "synthetic_variant_id"], "capture": {"line_id": "$.cart.items[0].id"}}, {"id": "read-cart", "request_id": "read-cart", "path_variables": {"cart_id": "{cart_id}"}}],
        "assertions": [{"id": "quantity", "step_id": "read-cart", "operator": "json_path_equals", "path": "$.cart.items[0].quantity", "expected": 1}, {"id": "currency", "step_id": "read-cart", "operator": "json_path_equals", "path": "$.cart.currency_code", "expected_from": "fixture_currency"}, {"id": "unit-price", "step_id": "read-cart", "operator": "json_path_equals", "path": "$.cart.items[0].unit_price", "expected_from": "fixture_unit_price"}],
        "cleanup": {"strategy": "disposable_environment", "on_every_exit": True, "reason": "No approved Store API cart-delete operation; delete the exact line item, then destroy the disposable database environment."},
    },
    "rocketchat": {
        "oracle_id": "rocketchat-message-roundtrip-v1",
        "evidence_sources": ["image:rocket.chat:8.6.1", "api:channels.create,chat.postMessage,channels.messages,channels.delete"],
        "credential_refs": [{"id": "rocketchat-test-user", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("create-room", "POST", "/api/v1/channels.create"), _request("post-message", "POST", "/api/v1/chat.postMessage"), _request("read-messages", "GET", "/api/v1/channels.messages"), _request("delete-room", "POST", "/api/v1/channels.delete")],
        "steps": [{"id": "create-owned-room", "request_id": "create-room", "json_body": {"name": "ca-{run_id}"}, "capture": {"room_id": "$.channel._id"}}, {"id": "post-owned-message", "request_id": "post-message", "json_body": {"roomId": "{room_id}", "text": "ChaosAtlas synthetic {run_id}"}, "capture": {"message_id": "$.message._id"}}, {"id": "poll-messages", "request_id": "read-messages", "query": {"roomId": "{room_id}", "count": 20}}],
        "assertions": [{"id": "room-owner", "step_id": "poll-messages", "operator": "json_path_equals", "path": "$.messages[0].rid", "expected_from": "room_id"}, {"id": "message-body", "step_id": "poll-messages", "operator": "json_path_equals", "path": "$.messages[0].msg", "expected_from": "synthetic_message"}, {"id": "async-visible", "step_id": "poll-messages", "operator": "eventually", "assertion_ref": "message-body"}],
        "cleanup": {"strategy": "exact_owned_ids", "request_id": "delete-room", "on_every_exit": True, "lookup_after_lost_response": {"field": "name", "value": "ca-{run_id}"}},
    },
    "erpnext": {
        "oracle_id": "erpnext-todo-crud-v1",
        "evidence_sources": ["image:erpnext:v16.34.1", "api:/api/resource/ToDo"],
        "credential_refs": [{"id": "erpnext-test-api-token", "source": "runtime_secret_ref"}],
        "allowed_requests": [_request("create", "POST", "/api/resource/ToDo"), _request("read", "GET", "/api/resource/ToDo/{todo_name}"), _request("update", "PUT", "/api/resource/ToDo/{todo_name}"), _request("delete", "DELETE", "/api/resource/ToDo/{todo_name}")],
        "steps": [{"id": "create-owned-todo", "request_id": "create", "json_body": {"description": "ChaosAtlas synthetic {run_id}", "status": "Open", "priority": "Low"}, "capture": {"todo_name": "$.data.name"}}, {"id": "read-todo", "request_id": "read", "path_variables": {"todo_name": "{todo_name}"}}, {"id": "update-status", "request_id": "update", "path_variables": {"todo_name": "{todo_name}"}, "json_body": {"status": "Closed"}}, {"id": "read-updated-todo", "request_id": "read", "path_variables": {"todo_name": "{todo_name}"}}],
        "assertions": [{"id": "description", "step_id": "read-todo", "operator": "json_path_equals", "path": "$.data.description", "expected": "ChaosAtlas synthetic {run_id}"}, {"id": "status-updated", "step_id": "read-updated-todo", "operator": "json_path_equals", "path": "$.data.status", "expected": "Closed"}],
        "cleanup": {"strategy": "exact_owned_ids", "request_id": "delete", "on_every_exit": True, "lookup_after_lost_response": {"field": "description", "value": "ChaosAtlas synthetic {run_id}"}},
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
