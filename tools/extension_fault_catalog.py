"""Provisional extension fault catalog kept separate from the 32 core intents."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ExtensionSpec:
    extension_id: str
    category: str
    backend: str
    resource_scope: str
    risk_level: str
    required_parameters: tuple[str, ...]
    required_capabilities: tuple[str, ...]


_CATALOG: dict[str, ExtensionSpec] = {
    "extension.io_delay": ExtensionSpec(
        "extension.io_delay", "storage_io", "IOChaos", "volume", "high",
        ("path", "latency_ms", "percent", "duration_s"),
        ("iochaos", "writable_path", "disposable_target"),
    ),
    "extension.io_error": ExtensionSpec(
        "extension.io_error", "storage_io", "IOChaos", "volume", "high",
        ("path", "errno", "percent", "duration_s"),
        ("iochaos", "writable_path", "disposable_target"),
    ),
    "extension.time_offset": ExtensionSpec(
        "extension.time_offset", "time_clock", "TimeChaos", "pod", "high",
        ("offset_ms", "duration_s"),
        ("timechaos", "disposable_target"),
    ),
    "extension.dependency_delay": ExtensionSpec(
        "extension.dependency_delay", "dependency_network", "NetworkChaos", "dependency_edge", "medium",
        ("latency_ms", "jitter_ms", "correlation", "duration_s"),
        ("networkchaos", "dependency_edge"),
    ),
    "extension.dependency_unreachable": ExtensionSpec(
        "extension.dependency_unreachable", "dependency_network", "NetworkChaos", "dependency_edge", "high",
        ("loss_percent", "correlation", "duration_s"),
        ("networkchaos", "dependency_edge"),
    ),
    "extension.jvm_gc_pause": ExtensionSpec(
        "extension.jvm_gc_pause", "runtime_jvm", "ChaosAtlasJvmAgent", "jvm", "high",
        ("target_process", "pause_ms", "duration_s"),
        ("jvmchaos", "jvm_present", "disposable_target"),
    ),
    "extension.queue_backlog": ExtensionSpec(
        "extension.queue_backlog", "runtime_queue", "ChaosAtlasQueueAgent", "queue", "high",
        ("queue_name", "depth", "duration_s"),
        ("queue_agent", "disposable_target"),
    ),
    "extension.connection_pool_exhaustion": ExtensionSpec(
        "extension.connection_pool_exhaustion", "connection_pool", "ChaosAtlasConnectionPoolAgent", "connection_pool", "high",
        ("pool_name", "connections", "duration_s"),
        ("connection_pool_agent", "disposable_target"),
    ),
    "extension.runtime_pause": ExtensionSpec(
        "extension.runtime_pause", "runtime_generic", "ChaosAtlasRuntimeAgent", "process", "high",
        ("target_process", "pause_ms", "duration_s"),
        ("pause_agent", "disposable_target"),
    ),
}


def is_extension_fault(value: Any) -> bool:
    return str(value or "").strip().startswith("extension.")


def get_extension_spec(extension_id: str) -> ExtensionSpec:
    key = str(extension_id or "").strip()
    try:
        return _CATALOG[key]
    except KeyError as exc:
        raise KeyError(f"unknown extension fault: {key}") from exc


def extension_catalog() -> dict[str, dict[str, Any]]:
    """Return JSON-safe copies without changing the core fault catalog."""
    return {key: deepcopy(asdict(value)) for key, value in _CATALOG.items()}


def extension_categories() -> tuple[str, ...]:
    return tuple(sorted({item.category for item in _CATALOG.values()}))
