"""Run the independent Sock Shop Ablation discovery arm.

The default arm exposes no classification, confidence, knowledge projection,
or Full stopping trace.  The YAML15 variant adds only five category labels and
three real YAML examples per category; it keeps the LLM self-stop policy and
uses the Full discovery wall-clock as a hard cap.  This module records model
and token accounting but never applies a mutation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ModelCall = Callable[[dict[str, Any]], dict[str, Any]]
DEEPSEEK_REQUEST_TIMEOUT_SECONDS = 120
PROMPT_PROTOCOL = {
    "schema_version": "sock-shop-ablation-prompt-v1",
    "classification_allowed": False,
    "confidence_allowed": False,
    "full_stop_trace_allowed": False,
    "knowledge_projection_allowed": False,
    "stop_control": "llm_self_stop_with_wall_clock_cap",
}
YAML15_CATEGORIES = (
    "Pod disruption",
    "Network degradation",
    "Resource pressure",
    "Protocol/HTTP fault",
    "Composite/scheduled fault",
)
YAML15_PROMPT_PROTOCOL = {
    "schema_version": "sock-shop-ablation-yaml15-prompt-v1",
    "classification_examples_allowed": True,
    "examples_per_category": 3,
    "confidence_allowed": False,
    "full_stop_trace_allowed": False,
    "knowledge_projection_allowed": False,
    "project_call_chain_allowed": False,
    "stop_control": "llm_self_stop_with_full_wall_clock_cap",
}


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _public_profile(method_input: dict[str, Any]) -> dict[str, Any]:
    source = method_input.get("sock_shop_profile") or {}
    allowed = {"namespace", "services", "oracles", "business_oracle", "runtime_contract"}
    return {key: source[key] for key in allowed if key in source}


def load_yaml15_bundle(manifest_path: Path) -> dict[str, Any]:
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    if manifest.get("schema_version") != "sock-shop-ablation-yaml15-manifest-v1":
        raise ValueError("unsupported YAML15 manifest schema")
    if manifest.get("total_examples") != 15:
        raise ValueError("YAML15 manifest must contain exactly 15 examples")
    if tuple(manifest.get("category_order") or ()) != YAML15_CATEGORIES:
        raise ValueError("YAML15 category order mismatch")
    categories = manifest.get("categories") or {}
    if set(categories) != set(YAML15_CATEGORIES) or any(len(categories[name]) != 3 for name in YAML15_CATEGORIES):
        raise ValueError("YAML15 manifest must contain three examples in each category")

    prompt_path = manifest_path.parent / str(manifest.get("prompt_path") or "")
    prompt_bytes = prompt_path.read_bytes()
    prompt_sha256 = hashlib.sha256(prompt_bytes).hexdigest()
    if prompt_sha256 != manifest.get("prompt_sha256"):
        raise ValueError("YAML15 prompt SHA-256 mismatch")
    prompt = json.loads(prompt_bytes.decode("utf-8"))
    if prompt.get("schema_version") != "sock-shop-ablation-yaml15-prompt-v1":
        raise ValueError("unsupported YAML15 prompt schema")
    examples = prompt.get("labeled_yaml_examples") or []
    counts = {category: 0 for category in YAML15_CATEGORIES}
    for example in examples:
        if not isinstance(example, dict) or set(example) != {"category", "yaml"}:
            raise ValueError("YAML15 prompt examples must contain only category and yaml")
        category = example.get("category")
        if category not in counts or not str(example.get("yaml") or "").strip():
            raise ValueError("YAML15 prompt contains an invalid labeled example")
        counts[category] += 1
    if len(examples) != 15 or any(count != 3 for count in counts.values()):
        raise ValueError("YAML15 prompt must contain three examples in each category")
    return {
        "prompt": prompt,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "prompt_sha256": prompt_sha256,
        "selection_fingerprint_sha256": manifest.get("selection_fingerprint_sha256"),
    }


def _public_hypothesis(hypothesis: dict[str, Any], *, yaml15_enabled: bool = False) -> dict[str, Any]:
    allowed = {"id", "target_service", "action_or_target", "call_chain_position", "motifs", "rationale"}
    result = {key: hypothesis[key] for key in allowed if key in hypothesis}
    if yaml15_enabled:
        source = hypothesis.get("call_chain_position_source")
        if source is None:
            source = "model_inference" if result.get("call_chain_position") else "unknown"
        if source not in {"model_inference", "unknown"}:
            raise ValueError("YAML15 call_chain_position_source must be model_inference or unknown")
        result["call_chain_position_source"] = source
    return result


def build_ablation_payload(
    method_input: dict[str, Any],
    seen_hypotheses: list[dict[str, Any]],
    *,
    seed: int,
    deadline_remaining_seconds: float | None = None,
    yaml15_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    yaml15_enabled = yaml15_bundle is not None
    payload = {
        "method": "chaosatlas-ablation-yaml15" if yaml15_enabled else "chaosatlas-ablation",
        "seed": seed,
        "sock_shop_profile": _public_profile(method_input),
        "seen_hypotheses": [
            _public_hypothesis(item, yaml15_enabled=yaml15_enabled)
            for item in seen_hypotheses
        ],
        "instruction": (
            "Generate one new Sock Shop chaos hypothesis at a time. You have no knowledge base, no confidence score, "
            "no project call-chain evidence, and no Full-arm hypotheses or stopping trace. The labeled YAML15 primer "
            "only demonstrates five fault categories and valid YAML structures; it contains no Sock Shop outcome. "
            if yaml15_enabled
            else "Generate one new Sock Shop chaos hypothesis at a time. You have no knowledge base, no category labels, "
            "no confidence score, and no Full-arm stopping trace. Decide yourself whether another hypothesis is useful. "
        ) + (
            "Return stop=true and stop_reason=self_stop when you decide to stop; otherwise return one hypothesis and "
            "continue_generation=true."
        ),
    }
    if yaml15_enabled:
        payload["yaml15_primer"] = yaml15_bundle["prompt"]
    if deadline_remaining_seconds is not None:
        payload["deadline_remaining_seconds"] = max(0.0, deadline_remaining_seconds)
    return payload


def _usage_totals(result: dict[str, Any]) -> tuple[int, int, int]:
    usage = result.get("_usage") or result.get("usage") or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or prompt + completion)
    return prompt, completion, total


def run_ablation_discovery(
    method_input: dict[str, Any],
    model_call: ModelCall,
    *,
    time_cap_seconds: float,
    seed: int,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    yaml15_bundle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    yaml15_enabled = yaml15_bundle is not None
    method = "chaosatlas-ablation-yaml15" if yaml15_enabled else "chaosatlas-ablation"
    prompt_protocol = YAML15_PROMPT_PROTOCOL if yaml15_enabled else PROMPT_PROTOCOL
    yaml15_provenance = None
    if yaml15_enabled:
        yaml15_provenance = {
            key: yaml15_bundle.get(key)
            for key in ("manifest_sha256", "prompt_sha256", "selection_fingerprint_sha256")
        }
    input_boundary = {
        "method": method,
        "sock_shop_profile": _public_profile(method_input),
        "seed": seed,
        "time_cap_seconds": time_cap_seconds,
        "yaml15_provenance": yaml15_provenance,
    }
    input_sha256 = _canonical_hash(input_boundary)
    prompt_protocol_sha256 = _canonical_hash(prompt_protocol)
    hypotheses: list[dict[str, Any]] = []
    self_stop = False
    time_cap_hit = False
    stop_reason = "not_stopped"
    model_calls = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    prior_elapsed = 0.0

    if resume and checkpoint_path and checkpoint_path.is_file():
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if saved.get("input_sha256") != input_sha256:
            raise ValueError("Ablation checkpoint input hash does not match")
        if saved.get("status") in {"completed", "time_cap_hit"}:
            return saved
        hypotheses = list(saved.get("hypotheses") or [])
        timing = saved.get("timing") or {}
        model_calls = int(timing.get("model_calls") or 0)
        prompt_tokens = int(timing.get("prompt_tokens") or 0)
        completion_tokens = int(timing.get("completion_tokens") or 0)
        total_tokens = int(timing.get("total_tokens") or 0)
        prior_elapsed = float(timing.get("discovery_wall_clock_seconds") or 0.0)

    remaining_budget = max(0.0, float(time_cap_seconds) - prior_elapsed)
    deadline = started + remaining_budget

    def result_payload(status: str) -> dict[str, Any]:
        elapsed = round(prior_elapsed + (time.monotonic() - started), 3)
        return {
            "schema_version": (
                "sock-shop-ablation-yaml15-discovery-v1"
                if yaml15_enabled
                else "sock-shop-ablation-discovery-v1"
            ),
            "method": method,
            "status": status,
            "self_stop": self_stop,
            "time_cap_hit": time_cap_hit,
            "stop_reason": stop_reason,
            "time_cap_seconds": time_cap_seconds,
            "seed": seed,
            "input_sha256": input_sha256,
            "prompt_protocol_sha256": prompt_protocol_sha256,
            "prompt_protocol": prompt_protocol,
            "yaml15_provenance": yaml15_provenance,
            "hypotheses": hypotheses,
            "timing": {
                "discovery_wall_clock_seconds": elapsed,
                "model_calls": model_calls,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
            "human_review": "pending",
            "knowledge_base_updated": False,
        }

    def write_checkpoint(status: str) -> None:
        if checkpoint_path is None:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(result_payload(status), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            time_cap_hit = True
            stop_reason = "time_cap_hit"
            write_checkpoint("time_cap_hit")
            break
        response = dict(
            model_call(
                build_ablation_payload(
                    method_input,
                    hypotheses,
                    seed=seed,
                    deadline_remaining_seconds=remaining,
                    yaml15_bundle=yaml15_bundle,
                )
            )
        )
        model_calls += 1
        prompt, completion, total = _usage_totals(response)
        prompt_tokens += prompt
        completion_tokens += completion
        total_tokens += total

        if time.monotonic() >= deadline:
            time_cap_hit = True
            stop_reason = "time_cap_hit"
            write_checkpoint("time_cap_hit")
            break

        if bool(response.get("stop")) or response.get("continue_generation") is False:
            self_stop = True
            stop_reason = str(response.get("stop_reason") or "self_stop")
            if response.get("hypothesis"):
                hypotheses.append(
                    _public_hypothesis(dict(response["hypothesis"]), yaml15_enabled=yaml15_enabled)
                )
            write_checkpoint("completed")
            break

        if not isinstance(response.get("hypothesis"), dict):
            raise ValueError("Ablation model response must contain a hypothesis or explicit stop=true")
        hypotheses.append(_public_hypothesis(dict(response["hypothesis"]), yaml15_enabled=yaml15_enabled))
        write_checkpoint("running")
        if time.monotonic() >= deadline:
            time_cap_hit = True
            stop_reason = "time_cap_hit"
            write_checkpoint("time_cap_hit")
            break

    return result_payload("completed" if self_stop else "time_cap_hit")


def fake_ablation_model_call(payload: dict[str, Any]) -> dict[str, Any]:
    count = len(payload.get("seen_hypotheses", []))
    if count >= 4:
        return {"stop": True, "stop_reason": "self_stop", "_usage": {"total_tokens": 1}}
    services = payload.get("sock_shop_profile", {}).get("services") or ["front-end"]
    return {
        "hypothesis": {
            "id": f"ablation-h-{count + 1}",
            "target_service": services[count % len(services)],
            "action_or_target": "pod-kill" if count % 2 == 0 else "delay",
            "call_chain_position": "entry" if count == 0 else "business-service",
            "rationale": "deterministic offline ablation discovery",
        },
        "continue_generation": True,
        "_usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
    }


def build_deepseek_ablation_body(payload: dict[str, Any], model: str) -> dict[str, Any]:
    yaml15_enabled = payload.get("method") == "chaosatlas-ablation-yaml15"
    schema = {
        "stop": "boolean; true only when no further useful hypothesis remains",
        "stop_reason": "self_stop when stop=true",
        "continue_generation": "boolean; false when choosing to stop",
        "hypothesis": {
            "id": "short stable id",
            "target_service": "one Sock Shop workload from the supplied profile",
            "action_or_target": "chaos action such as pod-kill, delay, loss, cpu, memory, abort, dns",
            "call_chain_position": "brief position if inferable from the profile",
            **(
                {"call_chain_position_source": "model_inference or unknown; never claim verified evidence"}
                if yaml15_enabled
                else {}
            ),
            "motifs": ["optional descriptive feature strings"],
            "rationale": "brief reason",
        },
    }
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object and no markdown. Do not invent or request a confidence score, "
                    "knowledge-base fact, project call-chain evidence, Full-arm result, or stopping trace. "
                    + (
                        "The five category labels apply only to the supplied YAML15 examples; do not claim they are "
                        "a confidence policy or a Full-arm generation quota. "
                        if yaml15_enabled
                        else "Do not invent or request a category label. "
                    )
                    + "Follow this schema: "
                    + json.dumps(schema, ensure_ascii=False)
                ),
            },
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        "temperature": 0.2,
        "seed": payload.get("seed"),
        "response_format": {"type": "json_object"},
    }


def _deepseek_model_call(
    api_key: str,
    model: str = "deepseek-chat",
    *,
    audit_dir: Path | None = None,
) -> ModelCall:
    endpoint = "https://api.deepseek.com/v1/chat/completions"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    call_number = 0
    if audit_dir is not None:
        audit_dir.mkdir(parents=True, exist_ok=True)
        call_number = len(list(audit_dir.glob("call-*.request.json")))

    def write_audit(path: Path, payload: dict[str, Any]) -> None:
        if path.exists():
            raise FileExistsError(f"refusing to overwrite model audit file: {path}")
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def call(payload: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_number
        call_number += 1
        body = build_deepseek_ablation_body(payload, model)
        if audit_dir is not None:
            write_audit(
                audit_dir / f"call-{call_number:03d}.request.json",
                {
                    "schema_version": "sock-shop-ablation-model-request-audit-v1",
                    "endpoint": endpoint,
                    "body_sha256": _canonical_hash(body),
                    "body": body,
                    "authorization_header_recorded": False,
                },
            )
        deadline_value = payload.get("deadline_remaining_seconds")
        remaining = (
            DEEPSEEK_REQUEST_TIMEOUT_SECONDS
            if deadline_value is None
            else float(deadline_value)
        )
        request_deadline = time.monotonic() + max(0.0, remaining)
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(5):
            request_remaining = request_deadline - time.monotonic()
            if request_remaining <= 0:
                raise TimeoutError("DeepSeek request deadline exceeded")
            timeout = min(DEEPSEEK_REQUEST_TIMEOUT_SECONDS, request_remaining)
            try:
                with opener.open(request, timeout=timeout) as response:
                    content = json.loads(response.read().decode("utf-8"))
                message = json.loads(content["choices"][0]["message"]["content"])
                message["_usage"] = content.get("usage") or {}
                if audit_dir is not None:
                    write_audit(
                        audit_dir / f"call-{call_number:03d}.response.json",
                        {
                            "schema_version": "sock-shop-ablation-model-response-audit-v1",
                            "model": content.get("model") or model,
                            "usage": content.get("usage") or {},
                            "message": {
                                key: value
                                for key, value in message.items()
                                if key != "_usage"
                            },
                        },
                    )
                return message
            except urllib.error.HTTPError as exc:
                retryable = exc.code in {408, 425, 429} or exc.code >= 500
                if not retryable or attempt == 4:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == 4:
                    raise
            request_remaining = request_deadline - time.monotonic()
            if request_remaining <= 0:
                raise TimeoutError("DeepSeek request deadline exceeded")
            time.sleep(min(2**attempt, request_remaining))
        raise RuntimeError("unreachable DeepSeek retry state")

    return call


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method-input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--time-cap-seconds", type=float, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--model", choices=["fake", "deepseek"], default="fake")
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--deepseek-model", default="deepseek-chat")
    parser.add_argument("--audit-dir", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--yaml15-manifest", type=Path)
    args = parser.parse_args()

    method_input = json.loads(args.method_input.read_text(encoding="utf-8"))
    if args.model == "deepseek":
        if args.api_key_file is None:
            raise SystemExit("--api-key-file is required for --model deepseek")
        api_key = args.api_key_file.read_text(encoding="utf-8").strip()
        if args.audit_dir and args.audit_dir.exists() and any(args.audit_dir.iterdir()) and not args.resume:
            raise SystemExit("--audit-dir is non-empty; use a new directory or --resume")
        model_call = _deepseek_model_call(api_key, args.deepseek_model, audit_dir=args.audit_dir)
    else:
        model_call = fake_ablation_model_call
    yaml15_bundle = load_yaml15_bundle(args.yaml15_manifest) if args.yaml15_manifest else None

    result = run_ablation_discovery(
        method_input,
        model_call,
        time_cap_seconds=args.time_cap_seconds,
        seed=args.seed,
        checkpoint_path=args.checkpoint,
        resume=args.resume,
        yaml15_bundle=yaml15_bundle,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "hypotheses": len(result["hypotheses"]), "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
