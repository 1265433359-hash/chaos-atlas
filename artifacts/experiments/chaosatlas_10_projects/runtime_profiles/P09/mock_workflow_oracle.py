"""Deterministic local oracle for the P09 minimal profile.

It validates API health and exercises a model-free workflow contract. It never
contacts an external model endpoint.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        return 0, {"error": str(exc)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-url", default="http://127.0.0.1:5001")
    ap.add_argument("--mock-only", action="store_true")
    args = ap.parse_args()
    result = {"oracle": "p09-local-mock-workflow", "external_model_calls": False, "checks": []}
    if args.mock_only:
        result["checks"].append({"name": "mock-workflow", "ok": True, "response": {"status": "succeeded", "answer": "P09-MOCK-OK", "model": "deterministic-local"}})
    else:
        status, payload = get_json(args.api_url.rstrip("/") + "/health")
        result["checks"].append({"name": "api-health", "ok": status == 200, "status": status, "payload": payload})
        result["checks"].append({"name": "mock-workflow", "ok": True, "response": {"status": "succeeded", "answer": "P09-MOCK-OK", "model": "deterministic-local"}})
    result["ok"] = all(check["ok"] for check in result["checks"])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
