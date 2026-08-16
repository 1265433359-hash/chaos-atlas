"""Generate the Full discovery arm with category-specific confidence stops.

This module uses the frozen YAML category summary to control novelty,
feature-coverage, and the Beta-style upper-bound stopping rule.  It may include
the Full knowledge projection, but it only emits discovery evidence; runtime
injection remains the responsibility of the gated runners.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.yaml_confidence_stopping import ConfidenceState, judge_novelty


ModelCall = Callable[[dict[str, Any]], dict[str, Any]]
DEEPSEEK_REQUEST_TIMEOUT_SECONDS = 120


def parse_model_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("model response JSON must be an object")
    return value


def _model_payload(method_input: dict[str, Any], category: str, config: dict[str, Any], seen: list[dict[str, Any]]) -> dict[str, Any]:
    payload = {
        "method": method_input["method"],
        "knowledge_allowed": bool(method_input["knowledge_allowed"]),
        "category": category,
        "category_config": config,
        "seen_hypotheses": seen,
        "sock_shop_profile": method_input.get("sock_shop_profile", {}),
    }
    if method_input.get("knowledge_allowed"):
        for key in ("knowledge_projection", "knowledge_base_view", "historical_experience", "call_chain_projection"):
            if key in method_input:
                payload[key] = method_input[key]
    return payload


def _write_discovery_checkpoint(
    path: Path,
    method_input: dict[str, Any],
    hypotheses: list[dict[str, Any]],
    stopping: dict[str, dict[str, Any]],
    confidence_trace: dict[str, list[dict[str, Any]]],
    category_states: dict[str, dict[str, Any]],
    status: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": "sock-shop-confidence-discovery-checkpoint-v1",
                "status": status,
                "method": method_input["method"],
                "knowledge_allowed": bool(method_input["knowledge_allowed"]),
                "hypotheses": hypotheses,
                "stopping": stopping,
                "confidence_trace": confidence_trace,
                "category_states": category_states,
                "human_review": "pending",
                "knowledge_base_updated": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def run_confidence_discovery(
    method_input: dict[str, Any],
    model_call: ModelCall,
    *,
    checkpoint_path: Path | None = None,
    resume: bool = False,
) -> dict[str, Any]:
    start = time.monotonic()
    hypotheses: list[dict[str, Any]] = []
    stopping: dict[str, dict[str, Any]] = {}
    confidence_trace: dict[str, list[dict[str, Any]]] = {}
    category_states: dict[str, dict[str, Any]] = {}

    if resume and checkpoint_path and checkpoint_path.is_file():
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint.get("method") != method_input["method"]:
            raise ValueError("checkpoint method does not match method input")
        hypotheses = list(checkpoint.get("hypotheses", []))
        stopping = dict(checkpoint.get("stopping", {}))
        confidence_trace = dict(checkpoint.get("confidence_trace", {}))
        category_states = dict(checkpoint.get("category_states", {}))

    categories = method_input["yaml_category_summary"]["categories"]
    for category, config in categories.items():
        if category in stopping:
            continue
        state = ConfidenceState(
            category=category,
            min_hypotheses=int(config["min_hypotheses"]),
            max_hypotheses=int(config["max_hypotheses"]),
            tau=float(config["tau"]),
            coverage_target=float(config["coverage_target"]),
        )
        restored = category_states.get(category) or {}
        state.novel_count = int(restored.get("novel_count", 0))
        state.duplicate_count = int(restored.get("duplicate_count", 0))
        state.covered_motifs = set(restored.get("covered_motifs", []))
        state.trace = list(restored.get("trace", []))
        required_motifs = {item["motif"] for item in config.get("top_motifs", [])}
        seen_for_category = [item for item in hypotheses if item.get("category") == category]

        if state.max_hypotheses <= 0:
            stopping[category] = {
                "stop": True,
                "reason": "empty_category",
                "generated": 0,
                "novel_count": 0,
                "duplicate_count": 0,
                "upper95": None,
                "feature_coverage": 1.0 if not required_motifs else 0.0,
            }
            confidence_trace[category] = []
            category_states[category] = {
                "novel_count": 0,
                "duplicate_count": 0,
                "covered_motifs": [],
                "trace": [],
            }
            if checkpoint_path:
                _write_discovery_checkpoint(
                    checkpoint_path,
                    method_input,
                    hypotheses,
                    stopping,
                    confidence_trace,
                    category_states,
                    "running",
                )
            continue

        while True:
            response = model_call(_model_payload(method_input, category, config, seen_for_category))
            hypothesis = dict(response["hypothesis"])
            motifs = set(hypothesis.get("motifs", []))
            novelty = judge_novelty(hypothesis, seen_for_category, required_motifs)
            decision = state.observe(novelty.novel, motifs, required_motifs)

            hypothesis.update(
                {
                    "method": method_input["method"],
                    "category": category,
                    "novel": novelty.novel,
                    "novelty_reasons": novelty.reasons,
                    "stop_snapshot": decision.to_dict(),
                }
            )
            hypotheses.append(hypothesis)
            seen_for_category.append(hypothesis)
            category_states[category] = {
                "novel_count": state.novel_count,
                "duplicate_count": state.duplicate_count,
                "covered_motifs": sorted(state.covered_motifs),
                "trace": list(state.trace),
            }
            if checkpoint_path:
                _write_discovery_checkpoint(
                    checkpoint_path,
                    method_input,
                    hypotheses,
                    stopping,
                    confidence_trace,
                    category_states,
                    "running",
                )
            if decision.stop:
                stopping[category] = decision.to_dict()
                confidence_trace[category] = list(state.trace)
                break

    result = {
        "method": method_input["method"],
        "status": "confidence_incomplete"
        if any(item.get("reason") == "max_hypotheses" for item in stopping.values())
        else "completed",
        "knowledge_allowed": bool(method_input["knowledge_allowed"]),
        "hypotheses": hypotheses,
        "stopping": stopping,
        "confidence_trace": confidence_trace,
        "timing": {"generation_seconds": round(time.monotonic() - start, 3)},
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
    if checkpoint_path:
        _write_discovery_checkpoint(
            checkpoint_path,
            method_input,
            hypotheses,
            stopping,
            confidence_trace,
            category_states,
            "completed",
        )
    return result


def fake_model_call(payload: dict[str, Any]) -> dict[str, Any]:
    seen_count = len(payload.get("seen_hypotheses", []))
    category = payload["category"]
    service_cycle = ["front-end", "catalogue", "carts", "orders", "user", "payment", "shipping", "queue-master"]
    action = {
        "Network degradation": "delay",
        "Resource pressure": "cpu",
        "Pod disruption": "pod-kill",
        "Protocol/HTTP fault": "abort",
        "Composite/scheduled fault": "scheduled-delay",
    }.get(category, "unknown")
    required_motifs = [item["motif"] for item in payload["category_config"].get("top_motifs", [])]
    motifs = [required_motifs[seen_count]] if seen_count < len(required_motifs) else required_motifs[-1:]
    action = next(
        (motif.split("=", 1)[1] for motif in motifs if motif.startswith("action_or_target=")),
        action,
    )
    return {
        "hypothesis": {
            "id": f"{payload['method']}-{category.lower().replace(' ', '-')}-{seen_count + 1}",
            "target_service": service_cycle[seen_count % len(service_cycle)],
            "action_or_target": action,
            "call_chain_position": "entry" if seen_count == 0 else "business-service",
            "motifs": motifs,
            "rationale": "fake deterministic offline discovery",
        }
    }


def build_deepseek_body(payload: dict[str, Any], model: str) -> dict[str, Any]:
    profile = payload.get("sock_shop_profile") or {}
    services = profile.get("services") or []
    if not services and isinstance(profile.get("topology"), dict):
        services = [
            str(node.get("name"))
            for node in profile["topology"].get("nodes", [])
            if node.get("role") == "workload" and node.get("name")
        ]
    required_motifs = [
        str(item["motif"])
        for item in payload.get("category_config", {}).get("top_motifs", [])
        if item.get("motif")
    ]
    seen_motifs = {
        str(motif)
        for hypothesis in payload.get("seen_hypotheses", [])
        for motif in hypothesis.get("motifs", [])
    }
    compact_payload = {
        "method": payload.get("method"),
        "knowledge_allowed": payload.get("knowledge_allowed"),
        "category": payload.get("category"),
        "category_config": payload.get("category_config"),
        "seen_hypotheses": payload.get("seen_hypotheses", []),
        "uncovered_required_motifs": [
            motif for motif in required_motifs if motif not in seen_motifs
        ],
        "allowed_target_services": sorted(set(services)),
        "business_oracle": profile.get("business_oracle"),
        "runtime_contract": profile.get("runtime_contract"),
    }
    if payload.get("knowledge_allowed"):
        for key in ("knowledge_projection", "knowledge_base_view", "historical_experience", "call_chain_projection"):
            if key in payload:
                compact_payload[key] = payload[key]
    schema = {
        "hypothesis": {
            "id": "short-stable-id",
            "target_service": "one allowed Sock Shop workload name",
            "action_or_target": "delay|loss|pod-kill|cpu|memory|abort|dns|scheduled-delay",
            "call_chain_position": "entry|business-service|data-dependency|supporting-service",
            "motifs": ["motif strings copied from category_config when relevant"],
            "rationale": "brief evidence-backed reason",
        }
    }
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object and no markdown. The top-level hypothesis must be a JSON object, "
                    "not a string. Use this schema exactly: "
                    + json.dumps(schema, ensure_ascii=False)
                    + " When uncovered_required_motifs is non-empty, prefer one of those motifs in the next hypothesis "
                    "when it is valid for the selected action and target; do not repeat a fully covered motif solely "
                    "to avoid exploration."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(compact_payload, ensure_ascii=False),
            },
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }


def _deepseek_model_call(api_key: str, model: str = "deepseek-chat") -> ModelCall:
    endpoint = "https://api.deepseek.com/v1/chat/completions"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        body = build_deepseek_body(payload, model)
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        for attempt in range(5):
            try:
                with opener.open(request, timeout=DEEPSEEK_REQUEST_TIMEOUT_SECONDS) as response:
                    content = json.loads(response.read().decode("utf-8"))
                text = content["choices"][0]["message"]["content"]
                return parse_model_json(text)
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {408, 425, 429} or exc.code >= 500
                if not retryable or attempt == 4:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 4:
                    raise
            time.sleep(2**attempt)
        raise RuntimeError("unreachable DeepSeek retry state")

    return call


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", choices=["fake", "deepseek"], default="fake")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--deepseek-model", default="deepseek-chat")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()

    method_input = json.loads(args.method_input.read_text(encoding="utf-8"))
    if args.model == "deepseek":
        if args.api_key_file is None:
            raise SystemExit("--api-key-file is required for --model deepseek")
        api_key = args.api_key_file.read_text(encoding="utf-8").strip()
        model_call = _deepseek_model_call(api_key, args.deepseek_model)
    else:
        model_call = fake_model_call

    result = run_confidence_discovery(
        method_input,
        model_call,
        checkpoint_path=args.checkpoint,
        resume=args.resume,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "hypotheses": len(result["hypotheses"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
