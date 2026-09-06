"""Reviewed four-project inputs for the shared v3 transaction DSL.

This module contains data, not project-specific execution code.  Every payload
is still processed by OracleBuilder and the strict v3 validator.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from chaosatlas.oracles.replay_validation import INTERPRETER


IMAGE_DIGESTS = {
    "immich": "sha256:f71a3a1f325972f620101773d4e23ad6d6eecb81cc53c464431080d5a1cf9a28",
    "medusa": "sha256:1bf4cc153e58a99cf34d92ee970d5494bf0d599899ee2481d691a849cba53464",
    "rocketchat": "sha256:c8ee1044c2c0503eddc1abc212240012ec9ba73e2cfa80d001cd23d582ec7c51",
    "erpnext": "sha256:eee240a179ff494cb82ad067d853c8db3f87171d86324f4b326892654e342144",
}


def _request(identifier: str, method: str, path: str, effect: str) -> dict[str, str]:
    return {"id": identifier, "method": method, "path": path, "effect": effect}


def _success(*statuses: int) -> dict[str, Any]:
    return {"statuses": list(statuses)}


def _capture(path: str, maximum: int = 128) -> dict[str, Any]:
    return {"path": path, "type": "string", "max_length": maximum}


def _lease_ownership(object_type: str) -> dict[str, Any]:
    return {"mode": "lease_exclusive", "object_type": object_type, "preflight_absent": True}


def _cleanup(reason: str) -> dict[str, Any]:
    return {
        "strategy": "disposable_environment",
        "on_every_exit": True,
        "environment_release_required": True,
        "steps": [],
        "reason": reason,
    }


COMMON = {
    "interpreter_version": INTERPRETER,
    "timeouts": {"request_s": 10, "eventual_s": 60, "poll_interval_s": 2},
    "ownership": {
        "synthetic_only": True,
        "boundary": "lease_exclusive_disposable_environment",
        "delete_scope": "verified_whole_lease_release",
    },
}


PAYLOADS: dict[str, dict[str, Any]] = {
    "immich": {
        "oracle_id": "immich-asset-roundtrip-v3",
        "evidence_sources": [
            "image:ghcr.io/immich-app/immich-server:v2.6.3@" + IMAGE_DIGESTS["immich"],
            "source:https://github.com/immich-app/immich/blob/v2.6.3/server/src/controllers/asset-media.controller.ts",
            "source:https://github.com/immich-app/immich/blob/v2.6.3/server/src/controllers/asset.controller.ts",
        ],
        "inputs": {
            "synthetic_png": {"type": "bytes", "max_length": 1048576},
            "fixture_timestamp": {"type": "string", "max_length": 64},
            "fixture_sha256": {"type": "string", "max_length": 64},
        },
        "runtime_scope": {
            "mode": "disposable", "service": "immich-server",
            "source_revision": "v2.6.3", "image_digest": IMAGE_DIGESTS["immich"],
        },
        "credential_refs": [{
            "id": "immich-transaction-auth", "source": "lease_owned_secret_ref",
            "secret_name": "immich-transaction-auth", "principal_role": "transaction-test-user",
            "header_keys": {"X-Api-Key": "x-api-key"},
        }],
        "allowed_requests": [
            _request("upload", "POST", "/api/assets", "write"),
            _request("read", "GET", "/api/assets/{asset_id}", "read"),
            _request("download", "GET", "/api/assets/{asset_id}/original", "read"),
        ],
        "steps": [
            {
                "id": "upload-synthetic-image", "request_id": "upload",
                "multipart": {
                    "assetData": "{synthetic_png}", "deviceAssetId": "ca-{run_id}",
                    "deviceId": "chaosatlas", "fileCreatedAt": "{fixture_timestamp}",
                    "fileModifiedAt": "{fixture_timestamp}", "isFavorite": "false",
                },
                "capture": {"asset_id": _capture("$.id", 64)}, "success": _success(201),
                "on_response_loss": {"strategy": "disposable_environment"},
                "ownership": _lease_ownership("immich-asset"),
            },
            {"id": "read-metadata", "request_id": "read", "success": _success(200)},
            {"id": "download-original", "request_id": "download", "success": _success(200)},
        ],
        "probe_steps": ["read-metadata", "download-original"],
        "assertions": [
            {"id": "asset-id", "operator": "json_path_equals", "step_id": "read-metadata", "path": "$.id", "expected_from": "asset_id"},
            {"id": "original-byte-hash", "operator": "sha256_equals", "step_id": "download-original", "expected_from": "fixture_sha256"},
        ],
        "probe_assertions": [
            {"id": "fresh-asset-id", "operator": "json_path_equals", "step_id": "read-metadata", "path": "$.id", "expected_from": "asset_id"},
            {"id": "fresh-original-byte-hash", "operator": "sha256_equals", "step_id": "download-original", "expected_from": "fixture_sha256"},
        ],
        "cleanup": _cleanup("The synthetic asset and its storage live only inside the fresh disposable lease."),
    },
    "medusa": {
        "oracle_id": "medusa-cart-lineitem-v3",
        "evidence_sources": [
            "image:docker.io/chaosatlas/medusa-backend:2.20.1@" + IMAGE_DIGESTS["medusa"],
            "source:projects/chaosatlas-apps/medusa/medusa/apps/backend/src/migration-scripts/initial-data-seed.ts",
            "api:https://docs.medusajs.com/api/store#carts",
        ],
        "inputs": {
            "synthetic_region_id": {"type": "string", "max_length": 128},
            "synthetic_variant_id": {"type": "string", "max_length": 128},
            "fixture_currency": {"type": "string", "max_length": 8},
            "fixture_unit_price": {"type": "number", "minimum": 0, "maximum": 1000000},
        },
        "runtime_scope": {
            "mode": "disposable", "service": "medusa-backend",
            "source_revision": "2.20.1", "image_digest": IMAGE_DIGESTS["medusa"],
        },
        "credential_refs": [{
            "id": "medusa-transaction-auth", "source": "lease_owned_secret_ref",
            "secret_name": "medusa-transaction-auth", "principal_role": "transaction-sales-channel",
            "header_keys": {"X-Publishable-Api-Key": "x-publishable-api-key"},
        }],
        "allowed_requests": [
            _request("create-cart", "POST", "/store/carts", "write"),
            _request("add-line", "POST", "/store/carts/{cart_id}/line-items", "write"),
            _request("read-cart", "GET", "/store/carts/{cart_id}", "read"),
        ],
        "steps": [
            {
                "id": "create-cart", "request_id": "create-cart",
                "json_body": {"region_id": "{synthetic_region_id}"},
                "capture": {"cart_id": _capture("$.cart.id")}, "success": _success(200),
                "on_response_loss": {"strategy": "disposable_environment"},
                "ownership": _lease_ownership("medusa-cart"),
            },
            {
                "id": "add-synthetic-variant", "request_id": "add-line",
                "json_body": {"variant_id": "{synthetic_variant_id}", "quantity": 1},
                "success": _success(200), "on_response_loss": {"strategy": "disposable_environment"},
                "owned_operation": "create-cart",
            },
            {"id": "read-cart", "request_id": "read-cart", "success": _success(200)},
        ],
        "probe_steps": ["read-cart"],
        "assertions": [
            {"id": "cart-id", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.id", "expected_from": "cart_id"},
            {"id": "one-line", "operator": "count_equals", "step_id": "read-cart", "path": "$.cart.items", "expected": 1},
            {"id": "variant", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.items[0].variant_id", "expected_from": "synthetic_variant_id"},
            {"id": "quantity", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.items[0].quantity", "expected": 1},
            {"id": "currency", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.currency_code", "expected_from": "fixture_currency"},
            {"id": "unit-price", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.items[0].unit_price", "expected_from": "fixture_unit_price"},
        ],
        "probe_assertions": [
            {"id": "fresh-one-line", "operator": "count_equals", "step_id": "read-cart", "path": "$.cart.items", "expected": 1},
            {"id": "fresh-variant", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.items[0].variant_id", "expected_from": "synthetic_variant_id"},
            {"id": "fresh-quantity", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.items[0].quantity", "expected": 1},
            {"id": "fresh-currency", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.currency_code", "expected_from": "fixture_currency"},
            {"id": "fresh-unit-price", "operator": "json_path_equals", "step_id": "read-cart", "path": "$.cart.items[0].unit_price", "expected_from": "fixture_unit_price"},
        ],
        "cleanup": _cleanup("The Store API has no approved cart deletion; the fresh database is destroyed with its lease."),
    },
    "rocketchat": {
        "oracle_id": "rocketchat-message-roundtrip-v3",
        "evidence_sources": [
            "image:registry.rocket.chat/rocketchat/rocket.chat:8.6.1@" + IMAGE_DIGESTS["rocketchat"],
            "api:https://developer.rocket.chat/apidocs/create-channel",
            "api:https://developer.rocket.chat/apidocs/post-message",
            "api:https://developer.rocket.chat/apidocs/get-channel-messages",
        ],
        "inputs": {},
        "runtime_scope": {
            "mode": "disposable", "service": "rocketchat-rocketchat",
            "source_revision": "8.6.1", "image_digest": IMAGE_DIGESTS["rocketchat"],
        },
        "credential_refs": [{
            "id": "rocketchat-transaction-auth", "source": "lease_owned_secret_ref",
            "secret_name": "rocketchat-transaction-auth", "principal_role": "transaction-test-user",
            "header_keys": {"X-Auth-Token": "x-auth-token", "X-User-Id": "x-user-id"},
        }],
        "allowed_requests": [
            _request("create-room", "POST", "/api/v1/channels.create", "write"),
            _request("post-message", "POST", "/api/v1/chat.postMessage", "write"),
            _request("read-messages", "GET", "/api/v1/channels.messages", "read"),
        ],
        "steps": [
            {
                "id": "create-owned-room", "request_id": "create-room",
                "json_body": {"name": "ca-{run_id}"},
                "capture": {"room_id": _capture("$.channel._id")},
                "success": {"statuses": [200], "checks": [
                    {"id": "room-success", "operator": "json_path_equals", "path": "$.success", "expected": True},
                ]},
                "on_response_loss": {"strategy": "disposable_environment"},
                "ownership": _lease_ownership("rocketchat-room"),
            },
            {
                "id": "post-owned-message", "request_id": "post-message",
                "json_body": {"roomId": "{room_id}", "text": "ChaosAtlas synthetic {run_id}", "parseUrls": False},
                "success": {"statuses": [200], "checks": [
                    {"id": "message-success", "operator": "json_path_equals", "path": "$.success", "expected": True},
                ]},
                "on_response_loss": {"strategy": "disposable_environment"},
                "owned_operation": "create-owned-room",
            },
            {
                "id": "poll-messages", "request_id": "read-messages",
                "query": {"roomId": "{room_id}", "count": 20}, "success": _success(200),
            },
        ],
        "probe_steps": ["poll-messages"],
        "assertions": [
            {
                "id": "one-owned-message", "operator": "array_exactly_one_matches",
                "step_id": "poll-messages", "path": "$.messages",
                "expected": {
                    "$.rid": "{room_id}", "$.u._id": "{principal_id}",
                    "$.msg": "ChaosAtlas synthetic {run_id}",
                },
            },
            {"id": "message-visible", "operator": "eventually", "step_id": "poll-messages", "assertion_ref": "one-owned-message"},
        ],
        "probe_assertions": [
            {
                "id": "fresh-one-owned-message", "operator": "array_exactly_one_matches",
                "step_id": "poll-messages", "path": "$.messages",
                "expected": {
                    "$.rid": "{room_id}", "$.u._id": "{principal_id}",
                    "$.msg": "ChaosAtlas synthetic {run_id}",
                },
            },
            {"id": "fresh-message-visible", "operator": "eventually", "step_id": "poll-messages", "assertion_ref": "fresh-one-owned-message"},
        ],
        "cleanup": _cleanup("The channel, message and synthetic account are destroyed with the fresh Rocket.Chat lease."),
    },
    "erpnext": {
        "oracle_id": "erpnext-todo-crud-v3",
        "evidence_sources": [
            "image:docker.io/frappe/erpnext:v16.34.1@" + IMAGE_DIGESTS["erpnext"],
            "runtime:frappe-16.33.0",
            "api:https://docs.frappe.io/framework/user/en/api/rest",
        ],
        "inputs": {},
        "runtime_scope": {
            "mode": "disposable", "service": "erpnext",
            "source_revision": "erpnext-v16.34.1+frappe-v16.33.0", "image_digest": IMAGE_DIGESTS["erpnext"],
        },
        "credential_refs": [{
            "id": "erpnext-transaction-auth", "source": "lease_owned_secret_ref",
            "secret_name": "erpnext-transaction-auth", "principal_role": "transaction-todo-user",
            "header_keys": {"Authorization": "authorization"},
        }],
        "allowed_requests": [
            _request("create", "POST", "/api/resource/ToDo", "write"),
            _request("read", "GET", "/api/resource/ToDo/{todo_name}", "read"),
            _request("update", "PUT", "/api/resource/ToDo/{todo_name}", "write"),
        ],
        "steps": [
            {
                "id": "create-owned-todo", "request_id": "create",
                "json_body": {"description": "ChaosAtlas synthetic {run_id}", "status": "Open", "priority": "Low"},
                "capture": {"todo_name": _capture("$.data.name")}, "success": _success(200),
                "on_response_loss": {"strategy": "disposable_environment"},
                "ownership": _lease_ownership("erpnext-todo"),
            },
            {"id": "read-todo", "request_id": "read", "success": _success(200)},
            {
                "id": "update-status", "request_id": "update", "json_body": {"status": "Closed"},
                "success": _success(200), "on_response_loss": {"strategy": "disposable_environment"},
                "owned_operation": "create-owned-todo",
            },
            {"id": "read-updated-todo", "request_id": "read", "success": _success(200)},
        ],
        "probe_steps": ["read-updated-todo"],
        "assertions": [
            {"id": "description-before", "operator": "json_path_equals", "step_id": "read-todo", "path": "$.data.description", "expected": "ChaosAtlas synthetic {run_id}"},
            {"id": "status-before", "operator": "json_path_equals", "step_id": "read-todo", "path": "$.data.status", "expected": "Open"},
            {"id": "description-after", "operator": "json_path_equals", "step_id": "read-updated-todo", "path": "$.data.description", "expected": "ChaosAtlas synthetic {run_id}"},
            {"id": "status-after", "operator": "json_path_equals", "step_id": "read-updated-todo", "path": "$.data.status", "expected": "Closed"},
        ],
        "probe_assertions": [
            {"id": "fresh-description", "operator": "json_path_equals", "step_id": "read-updated-todo", "path": "$.data.description", "expected": "ChaosAtlas synthetic {run_id}"},
            {"id": "fresh-status", "operator": "json_path_equals", "step_id": "read-updated-todo", "path": "$.data.status", "expected": "Closed"},
        ],
        "cleanup": _cleanup("The ToDo, site, database and synthetic user are destroyed with the fresh ERPNext lease."),
    },
}


def project_v3_payload(project_id: str) -> dict[str, Any]:
    try:
        payload = deepcopy(PAYLOADS[project_id])
    except KeyError as exc:
        raise ValueError(f"no reviewed v3 transaction template for {project_id}") from exc
    return {**deepcopy(COMMON), **payload}
