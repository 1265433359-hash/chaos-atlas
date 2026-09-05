"""Redacted Dify Chatflow business oracle for live lifecycle runs."""

from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any

from tools.run_chaos_experiment import (
    http_request,
    observation_failure_sample,
    start_port_forward,
    stop_process,
    wait_for_port,
)


class DifyChatflowOracle:
    """Probe a published Dify Chatflow without persisting credentials or text."""

    def __init__(
        self,
        *,
        api_key_file: Path,
        namespace: str,
        service: str,
        remote_port: int = 80,
        local_port: int = 18081,
        kube_context: str | None = None,
        timeout_s: float = 60.0,
        observation_window_s: float = 60.0,
        probe_retry_interval_s: float = 2.0,
    ) -> None:
        self.api_key = Path(api_key_file).expanduser().resolve().read_text(encoding="utf-8-sig").strip()
        if not self.api_key:
            raise ValueError("Dify application key file is empty")
        self.namespace = str(namespace).strip()
        self.service = str(service).strip()
        self.remote_port = int(remote_port)
        self.local_port = int(local_port)
        self.kube_context = str(kube_context).strip() if kube_context else None
        self.timeout_s = float(timeout_s)
        self.observation_window_s = max(0.0, float(observation_window_s))
        self.probe_retry_interval_s = max(0.0, float(probe_retry_interval_s))

    @classmethod
    def from_oracle(cls, oracle: dict[str, Any], *, namespace: str, kube_context: str | None = None) -> "DifyChatflowOracle":
        key_file = str(oracle.get("api_key_file") or r"C:\APP\project\Dify_APIkey.txt")
        return cls(
            api_key_file=Path(key_file),
            namespace=namespace,
            service=str(oracle.get("service") or ""),
            remote_port=int(oracle.get("remote_port") or 80),
            local_port=int(oracle.get("local_port") or 18081),
            kube_context=kube_context,
            timeout_s=float(oracle.get("timeout_s") or 60),
            observation_window_s=float(oracle.get("observation_window_s") or 60),
            probe_retry_interval_s=float(oracle.get("probe_retry_interval_s") or 2),
        )

    @staticmethod
    def _success(response: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        parsed: dict[str, Any] = {}
        try:
            value = json.loads(response.get("body") or "{}")
            if isinstance(value, dict):
                parsed = value
        except json.JSONDecodeError:
            pass
        success = (
            response.get("status_code") == 200
            and bool(parsed.get("answer"))
            and bool(parsed.get("message_id"))
        )
        # Deliberately retain response shape only; answer text never enters evidence.
        sample = {
            "status_code": response.get("status_code"),
            "latency_ms": response.get("latency_ms"),
            "response_shape": bool(parsed.get("answer")) and bool(parsed.get("message_id")),
            "mode": parsed.get("mode") if success else None,
            "error_code": parsed.get("code") if not success else None,
            "transport_error": bool(response.get("error")),
        }
        return success, sample

    def __call__(self, phase: str, _manifest: dict[str, Any] | None = None) -> dict[str, Any]:
        deadline = time.monotonic() + (self.observation_window_s if phase == "observe" else 0.0)
        samples: list[dict[str, Any]] = []
        failures: list[str] = []
        sample_index = 0
        while True:
            process = None
            try:
                process = start_port_forward(
                    self.namespace,
                    self.service,
                    self.local_port,
                    self.remote_port,
                    kube_context=self.kube_context,
                )
                wait_for_port("127.0.0.1", self.local_port, process, 15.0)
                body = json.dumps(
                    {
                        "inputs": {},
                        "query": "Reply with exactly CHAOSATLAS_OK.",
                        "response_mode": "blocking",
                        "user": "chaosatlas-e2e",
                    },
                    ensure_ascii=True,
                )
                response = http_request(
                    self.local_port,
                    "/v1/chat-messages",
                    "POST",
                    self.timeout_s,
                    body,
                    65536,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                sample_index += 1
                success, sample = self._success(response)
                sample["sample"] = sample_index
                samples.append(sample)
                if success:
                    return {
                        "status": "degraded" if failures else "pass",
                        "phase": phase,
                        "samples": samples,
                        "reason": "chat recovered after transient failures" if failures else None,
                    }
                failures.append(str(sample.get("error_code") or "chat request did not satisfy success contract"))
            except (OSError, RuntimeError, TimeoutError) as exc:
                sample_index += 1
                samples.append({"sample": sample_index, **observation_failure_sample(sample_index, type(exc).__name__)})
                failures.append(type(exc).__name__)
            finally:
                stop_process(process)
            if time.monotonic() >= deadline:
                return {
                    "status": "business_unreachable",
                    "phase": phase,
                    "samples": samples,
                    "reason": failures[-1] if failures else "chat request did not pass",
                }
            time.sleep(min(self.probe_retry_interval_s, max(0.0, deadline - time.monotonic())))
