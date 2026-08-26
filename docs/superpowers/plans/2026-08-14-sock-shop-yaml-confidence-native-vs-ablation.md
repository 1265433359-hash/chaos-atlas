# Sock Shop YAML Confidence Native vs Ablation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Sock Shop experiment pipeline that compares `native-full` and `ChaosAtlas-ablation` under the same real-YAML five-category confidence-stopped hypothesis generation protocol.

**Architecture:** Add pure offline modules for YAML classification/statistics and Beta confidence stopping, then add a Sock Shop discovery/gating/runtime orchestration layer with explicit adapter functions for mutation compilation and runtime invocation. Runtime remains separate from hypothesis generation so the experiment can freeze generated candidates before touching Kubernetes.

**Tech Stack:** Python 3.12, PyYAML, pytest, existing ChaosAtlas `tools/` runners, existing Sock Shop runtime profiles and business oracle.

---

## File Structure

| File | Responsibility |
|---|---|
| `tools/yaml_confidence_categories.py` | Pure YAML inventory, five-category mapping, feature extraction, bucketization, support/entropy/lift/motif statistics. |
| `tools/yaml_confidence_stopping.py` | Pure Beta posterior, upper confidence bound, novelty tracking, class stop decision. |
| `tools/build_sock_shop_confidence_inputs.py` | Build frozen experiment inputs for both methods from YAML stats, Sock Shop facts, and method boundaries. |
| `tools/run_sock_shop_confidence_discovery.py` | Invoke the two discovery arms, record hypotheses, novelty decisions, confidence traces, and method timing. |
| `tools/run_sock_shop_confidence_runtime.py` | Compile/gate generated hypotheses and run completed candidates on Sock Shop, recording per-method timing. |
| `tools/review_sock_shop_confidence_experiment.py` | Summarize stable weaknesses, invalid candidates, elapsed time, and category contribution tables. |
| `tools/tests/test_yaml_confidence_categories.py` | Tests for category mapping and feature extraction. |
| `tools/tests/test_yaml_confidence_stopping.py` | Tests for Beta upper bound and stopping semantics. |
| `tools/tests/test_build_sock_shop_confidence_inputs.py` | Tests for frozen input manifests and method-boundary separation. |
| `tools/tests/test_run_sock_shop_confidence_discovery.py` | Tests for discovery trace/timing contracts using fake model outputs. |
| `tools/tests/test_run_sock_shop_confidence_runtime.py` | Tests for compile/gate/runtime plan contracts without touching Kubernetes. |
| `tools/tests/test_review_sock_shop_confidence_experiment.py` | Tests for result classification and timing tables. |
| `artifacts/experiments/sock_shop_yaml_confidence_2026-08-14-r1/` | New immutable experiment directory; create `-r2` if non-empty. |

## Task 1: YAML Five-Category Classifier

**Files:**
- Create: `tools/yaml_confidence_categories.py`
- Test: `tools/tests/test_yaml_confidence_categories.py`

- [ ] **Step 1: Write the failing category tests**

Create `tools/tests/test_yaml_confidence_categories.py`:

```python
from tools.yaml_confidence_categories import (
    YAML_CATEGORY_CONFIG,
    bucket_duration,
    classify_kind,
    extract_yaml_features,
    selector_shape,
)


def test_five_category_counts_are_fixed():
    assert YAML_CATEGORY_CONFIG["Pod disruption"]["kinds"] == ["PodChaos"]
    assert "NetworkChaos" in YAML_CATEGORY_CONFIG["Network degradation"]["kinds"]
    assert set(YAML_CATEGORY_CONFIG) == {
        "Pod disruption",
        "Network degradation",
        "Resource pressure",
        "Protocol/HTTP fault",
        "Composite/scheduled fault",
    }


def test_kind_mapping_includes_only_first_runtime_scope():
    assert classify_kind("PodChaos") == "Pod disruption"
    assert classify_kind("NetworkChaos") == "Network degradation"
    assert classify_kind("StressChaos") == "Resource pressure"
    assert classify_kind("HTTPChaos") == "Protocol/HTTP fault"
    assert classify_kind("DNSChaos") == "Protocol/HTTP fault"
    assert classify_kind("Workflow") == "Composite/scheduled fault"
    assert classify_kind("Schedule") == "Composite/scheduled fault"
    assert classify_kind("IOChaos") is None


def test_selector_shape_detects_app_label():
    spec = {"selector": {"labelSelectors": {"app": "catalogue"}}}
    assert selector_shape(spec) == "app-label"


def test_bucket_duration():
    assert bucket_duration("10s") == "short"
    assert bucket_duration("5m") == "medium"
    assert bucket_duration("1h") == "long"
    assert bucket_duration(None) == "unknown"


def test_extract_network_delay_features():
    doc = {
        "kind": "NetworkChaos",
        "spec": {
            "action": "delay",
            "mode": "one",
            "duration": "5m",
            "selector": {"labelSelectors": {"app": "catalogue"}},
            "delay": {"latency": "100ms"},
        },
    }
    features = extract_yaml_features("raw_yaml/NetworkChaos/example.yaml", doc)
    assert features["category"] == "Network degradation"
    assert features["kind"] == "NetworkChaos"
    assert features["action_or_target"] == "delay"
    assert features["mode"] == "one"
    assert features["selector_shape"] == "app-label"
    assert features["duration_bucket"] == "medium"
    assert features["intensity_bucket"] == "low"
```

- [ ] **Step 2: Run the tests and confirm RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_categories.py --basetemp .tmp-yaml-confidence-categories-red
```

Expected: fail with `ModuleNotFoundError: No module named 'tools.yaml_confidence_categories'`.

- [ ] **Step 3: Implement the classifier**

Create `tools/yaml_confidence_categories.py` with:

```python
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

YAML_CATEGORY_CONFIG = {
    "Pod disruption": {"kinds": ["PodChaos"], "min": 3, "max": 6, "tau": 0.08, "coverage_target": 0.75},
    "Network degradation": {"kinds": ["NetworkChaos"], "min": 4, "max": 8, "tau": 0.05, "coverage_target": 0.80},
    "Resource pressure": {"kinds": ["StressChaos"], "min": 2, "max": 5, "tau": 0.08, "coverage_target": 0.70},
    "Protocol/HTTP fault": {"kinds": ["HTTPChaos", "DNSChaos"], "min": 1, "max": 4, "tau": 0.10, "coverage_target": 0.60},
    "Composite/scheduled fault": {"kinds": ["Workflow", "Schedule"], "min": 0, "max": 2, "tau": 0.15, "coverage_target": 0.50},
}

_KIND_TO_CATEGORY = {
    kind: category
    for category, config in YAML_CATEGORY_CONFIG.items()
    for kind in config["kinds"]
}


def classify_kind(kind: str | None) -> str | None:
    return _KIND_TO_CATEGORY.get(kind or "")


def _parse_seconds(value: str | None) -> float | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(ms|s|m|h)", str(value).strip())
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    return amount * {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}[unit]


def bucket_duration(value: str | None) -> str:
    seconds = _parse_seconds(value)
    if seconds is None:
        return "unknown"
    if seconds <= 60:
        return "short"
    if seconds <= 600:
        return "medium"
    return "long"


def _bucket_numeric(value: float | None, low: float, high: float) -> str:
    if value is None:
        return "unknown"
    if value <= low:
        return "low"
    if value <= high:
        return "medium"
    return "high"


def selector_shape(spec: dict[str, Any]) -> str:
    selector = spec.get("selector") or {}
    labels = selector.get("labelSelectors") or {}
    namespaces = selector.get("namespaces") or []
    if labels.get("app"):
        return "app-label"
    if len(labels) > 1:
        return "multi-label"
    if namespaces and not labels:
        return "namespace-only"
    if not selector:
        return "empty-or-high-risk"
    return "other-selector"


def intensity_bucket(kind: str, spec: dict[str, Any]) -> str:
    if kind == "NetworkChaos":
        latency = ((spec.get("delay") or {}).get("latency"))
        return _bucket_numeric(_parse_seconds(latency), 0.2, 2.0)
    if kind == "StressChaos":
        stressors = spec.get("stressors") or {}
        cpu = (stressors.get("cpu") or {}).get("load")
        memory = (stressors.get("memory") or {}).get("size")
        if cpu is not None:
            return _bucket_numeric(float(cpu), 50, 90)
        if memory is not None:
            return "memory-present"
    return "unknown"


def action_or_target(kind: str, spec: dict[str, Any]) -> str:
    if kind == "StressChaos":
        stressors = spec.get("stressors") or {}
        if "cpu" in stressors:
            return "cpu"
        if "memory" in stressors:
            return "memory"
    if kind == "HTTPChaos":
        return str(spec.get("target") or spec.get("method") or "http")
    if kind == "PodChaos":
        return str(spec.get("action") or "pod-kill")
    if kind == "DNSChaos":
        return str(spec.get("action") or "dns")
    return str(spec.get("action") or spec.get("target") or "unknown")


def extract_yaml_features(path: str, doc: dict[str, Any]) -> dict[str, Any]:
    kind = doc.get("kind")
    spec = doc.get("spec") or {}
    category = classify_kind(kind)
    return {
        "path": path,
        "kind": kind,
        "category": category,
        "included_in_runtime_scope": category is not None,
        "action_or_target": action_or_target(kind or "", spec),
        "mode": str(spec.get("mode") or "unknown"),
        "selector_shape": selector_shape(spec),
        "duration_bucket": bucket_duration(spec.get("duration")),
        "intensity_bucket": intensity_bucket(kind or "", spec),
        "scheduler_present": bool(spec.get("scheduler") or kind in {"Workflow", "Schedule"}),
    }


def load_yaml_feature_rows(raw_yaml_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_path in sorted(raw_yaml_root.glob("*/*.yaml")):
        try:
            doc = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"path": str(file_path), "parse_error": str(exc), "included_in_runtime_scope": False})
            continue
        if isinstance(doc, dict):
            rows.append(extract_yaml_features(str(file_path), doc))
    return rows
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_categories.py --basetemp .tmp-yaml-confidence-categories-green
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/yaml_confidence_categories.py tools/tests/test_yaml_confidence_categories.py
git commit -m "feat: classify YAML confidence categories"
```

## Task 2: YAML Category Statistics and Motifs

**Files:**
- Modify: `tools/yaml_confidence_categories.py`
- Modify: `tools/tests/test_yaml_confidence_categories.py`

- [ ] **Step 1: Add failing statistics tests**

Append:

```python
from tools.yaml_confidence_categories import summarize_feature_rows


def test_summarize_feature_rows_counts_and_motifs():
    rows = [
        {"category": "Network degradation", "kind": "NetworkChaos", "action_or_target": "delay", "mode": "one", "selector_shape": "app-label", "duration_bucket": "medium", "intensity_bucket": "low", "included_in_runtime_scope": True},
        {"category": "Network degradation", "kind": "NetworkChaos", "action_or_target": "delay", "mode": "one", "selector_shape": "app-label", "duration_bucket": "medium", "intensity_bucket": "medium", "included_in_runtime_scope": True},
        {"category": "Pod disruption", "kind": "PodChaos", "action_or_target": "pod-kill", "mode": "one", "selector_shape": "app-label", "duration_bucket": "medium", "intensity_bucket": "unknown", "included_in_runtime_scope": True},
    ]
    summary = summarize_feature_rows(rows)
    assert summary["total_yaml"] == 3
    assert summary["categories"]["Network degradation"]["count"] == 2
    assert summary["categories"]["Network degradation"]["coverage_target"] == 0.80
    motifs = summary["categories"]["Network degradation"]["top_motifs"]
    assert any("action_or_target=delay" in motif["motif"] for motif in motifs)
```

- [ ] **Step 2: Run RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_categories.py::test_summarize_feature_rows_counts_and_motifs --basetemp .tmp-yaml-confidence-stats-red
```

Expected: fail because `summarize_feature_rows` is missing.

- [ ] **Step 3: Implement summary logic**

Add:

```python
def _entropy(values: list[str]) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _motifs(rows: list[dict[str, Any]], class_count: int) -> list[dict[str, Any]]:
    fields = ["action_or_target", "mode", "selector_shape", "duration_bucket", "intensity_bucket"]
    counts: Counter[str] = Counter()
    for row in rows:
        for field in fields:
            counts[f"{field}={row.get(field, 'unknown')}"] += 1
    min_support = max(1, math.ceil(class_count * 0.05))
    motifs = [
        {"motif": motif, "support": support, "support_ratio": round(support / class_count, 4)}
        for motif, support in counts.most_common()
        if support >= min_support
    ]
    return motifs[:12]


def summarize_feature_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    included = [row for row in rows if row.get("included_in_runtime_scope")]
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in included:
        by_category[str(row["category"])].append(row)
    categories = {}
    for category, config in YAML_CATEGORY_CONFIG.items():
        class_rows = by_category.get(category, [])
        count = len(class_rows)
        categories[category] = {
            "count": count,
            "min_hypotheses": config["min"],
            "max_hypotheses": config["max"],
            "tau": config["tau"],
            "coverage_target": config["coverage_target"],
            "feature_entropy": {
                field: round(_entropy([str(row.get(field, "unknown")) for row in class_rows]), 4)
                for field in ["action_or_target", "mode", "selector_shape", "duration_bucket", "intensity_bucket"]
            },
            "top_motifs": _motifs(class_rows, count) if count else [],
        }
    return {
        "total_yaml": len(rows),
        "included_runtime_scope": len(included),
        "categories": categories,
    }
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_categories.py --basetemp .tmp-yaml-confidence-stats-green
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/yaml_confidence_categories.py tools/tests/test_yaml_confidence_categories.py
git commit -m "feat: summarize YAML confidence motifs"
```

## Task 3: Beta Confidence Stop Engine

**Files:**
- Create: `tools/yaml_confidence_stopping.py`
- Test: `tools/tests/test_yaml_confidence_stopping.py`

- [ ] **Step 1: Write failing stop-rule tests**

Create:

```python
from tools.yaml_confidence_stopping import ConfidenceState, judge_novelty


def test_confidence_state_stops_when_upper_bound_below_tau_after_minimum():
    state = ConfidenceState(category="Protocol/HTTP fault", min_hypotheses=1, max_hypotheses=4, tau=0.95, coverage_target=0.50)
    decision = state.observe(novel=False, covered_motifs={"mode=one"}, required_motifs={"mode=one"})
    assert decision.stop is True
    assert decision.reason == "confidence_saturated"


def test_confidence_state_forces_stop_at_max():
    state = ConfidenceState(category="Network degradation", min_hypotheses=4, max_hypotheses=4, tau=0.05, coverage_target=0.80)
    for _ in range(4):
        decision = state.observe(novel=True, covered_motifs={"action_or_target=delay"}, required_motifs={"action_or_target=delay"})
    assert decision.stop is True
    assert decision.reason == "max_hypotheses"


def test_judge_novelty_detects_new_service_and_motif():
    seen = [{"target_service": "catalogue", "motifs": ["action_or_target=delay"]}]
    hypothesis = {"target_service": "user", "motifs": ["mode=one"]}
    novelty = judge_novelty(hypothesis, seen, required_motifs={"mode=one"})
    assert novelty.novel is True
    assert "new_target_service" in novelty.reasons
    assert "new_required_motif" in novelty.reasons
```

- [ ] **Step 2: Run RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_stopping.py --basetemp .tmp-yaml-confidence-stopping-red
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement stop engine**

Create:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Any


@dataclass
class StopDecision:
    stop: bool
    reason: str
    generated: int
    novel_count: int
    duplicate_count: int
    upper95: float
    feature_coverage: float


@dataclass
class NoveltyDecision:
    novel: bool
    reasons: list[str]


def beta_upper95(alpha: float, beta: float) -> float:
    mean = alpha / (alpha + beta)
    variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
    upper = mean + NormalDist().inv_cdf(0.95) * (variance ** 0.5)
    return max(0.0, min(1.0, upper))


@dataclass
class ConfidenceState:
    category: str
    min_hypotheses: int
    max_hypotheses: int
    tau: float
    coverage_target: float
    novel_count: int = 0
    duplicate_count: int = 0
    covered_motifs: set[str] = field(default_factory=set)

    @property
    def generated(self) -> int:
        return self.novel_count + self.duplicate_count

    def observe(self, novel: bool, covered_motifs: set[str], required_motifs: set[str]) -> StopDecision:
        if novel:
            self.novel_count += 1
        else:
            self.duplicate_count += 1
        self.covered_motifs.update(covered_motifs)
        alpha = 1 + self.novel_count
        beta = 1 + self.duplicate_count
        upper95 = beta_upper95(alpha, beta)
        coverage = len(self.covered_motifs & required_motifs) / len(required_motifs) if required_motifs else 1.0
        if self.generated >= self.max_hypotheses:
            return StopDecision(True, "max_hypotheses", self.generated, self.novel_count, self.duplicate_count, upper95, coverage)
        if self.generated >= self.min_hypotheses and coverage >= self.coverage_target and upper95 < self.tau:
            return StopDecision(True, "confidence_saturated", self.generated, self.novel_count, self.duplicate_count, upper95, coverage)
        return StopDecision(False, "continue", self.generated, self.novel_count, self.duplicate_count, upper95, coverage)


def judge_novelty(hypothesis: dict[str, Any], seen: list[dict[str, Any]], required_motifs: set[str]) -> NoveltyDecision:
    reasons: list[str] = []
    seen_services = {item.get("target_service") for item in seen}
    seen_actions = {item.get("action_or_target") for item in seen}
    seen_positions = {item.get("call_chain_position") for item in seen}
    seen_motifs = {motif for item in seen for motif in item.get("motifs", [])}
    motifs = set(hypothesis.get("motifs", []))
    if hypothesis.get("target_service") not in seen_services:
        reasons.append("new_target_service")
    if hypothesis.get("action_or_target") not in seen_actions:
        reasons.append("new_action_or_target")
    if hypothesis.get("call_chain_position") not in seen_positions:
        reasons.append("new_call_chain_position")
    if motifs & required_motifs - seen_motifs:
        reasons.append("new_required_motif")
    return NoveltyDecision(bool(reasons), reasons)
```

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_stopping.py --basetemp .tmp-yaml-confidence-stopping-green
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/yaml_confidence_stopping.py tools/tests/test_yaml_confidence_stopping.py
git commit -m "feat: add YAML confidence stop engine"
```

## Task 4: Build Frozen Sock Shop Confidence Inputs

**Files:**
- Create: `tools/build_sock_shop_confidence_inputs.py`
- Test: `tools/tests/test_build_sock_shop_confidence_inputs.py`

- [ ] **Step 1: Write failing manifest tests**

Create tests asserting:

```python
from pathlib import Path
from tools.build_sock_shop_confidence_inputs import build_confidence_input_manifest


def test_manifest_separates_native_and_ablation_boundaries(tmp_path):
    out = tmp_path / "exp"
    manifest = build_confidence_input_manifest(
        raw_yaml_root=Path("raw_yaml"),
        output_dir=out,
        sock_shop_profile={"services": ["front-end", "catalogue", "user"]},
        dry_run=True,
    )
    assert manifest["human_review"] == "pending"
    assert manifest["knowledge_base_updated"] is False
    assert manifest["methods"]["native-full"]["knowledge_allowed"] is True
    assert manifest["methods"]["chaosatlas-ablation"]["knowledge_allowed"] is False
    assert (out / "yaml-category-summary.json").exists()
    assert (out / "method-inputs" / "native-full.json").exists()
    assert (out / "method-inputs" / "chaosatlas-ablation.json").exists()
```

- [ ] **Step 2: Run RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_build_sock_shop_confidence_inputs.py --basetemp .tmp-build-confidence-inputs-red
```

Expected: fail because module is missing.

- [ ] **Step 3: Implement manifest builder**

Implement:

```python
def build_confidence_input_manifest(
    raw_yaml_root: Path,
    output_dir: Path,
    sock_shop_profile: dict,
    dry_run: bool = False,
) -> dict:
    rows = load_yaml_feature_rows(raw_yaml_root)
    summary = summarize_feature_rows(rows)
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "yaml-category-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    methods = {
        "native-full": {"knowledge_allowed": True},
        "chaosatlas-ablation": {"knowledge_allowed": False},
    }
    for method, method_config in methods.items():
        payload = {
            "method": method,
            "knowledge_allowed": method_config["knowledge_allowed"],
            "yaml_category_summary": summary,
            "sock_shop_profile": sock_shop_profile,
            "human_review": "pending",
            "knowledge_base_updated": False,
        }
        path = output_dir / "method-inputs" / f"{method}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    manifest = {
        "experiment": "sock_shop_yaml_confidence",
        "human_review": "pending",
        "knowledge_base_updated": False,
        "methods": methods,
        "dry_run": dry_run,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest
```

The implementation must:

1. call `load_yaml_feature_rows`;
2. call `summarize_feature_rows`;
3. write `yaml-category-summary.json`;
4. write method input JSONs with identical category/stopping config;
5. set `knowledge_allowed=true` only for native-full;
6. record timing fields initialized to null.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_build_sock_shop_confidence_inputs.py --basetemp .tmp-build-confidence-inputs-green
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/build_sock_shop_confidence_inputs.py tools/tests/test_build_sock_shop_confidence_inputs.py
git commit -m "feat: build Sock Shop confidence inputs"
```

## Task 5: Confidence Discovery Runner

**Files:**
- Create: `tools/run_sock_shop_confidence_discovery.py`
- Test: `tools/tests/test_run_sock_shop_confidence_discovery.py`

- [ ] **Step 1: Write fake-model tests**

The test must not call DeepSeek. It should pass a fake model function that returns deterministic hypotheses per category and assert:

```python
assert result["method"] == "native-full"
assert result["stopping"]["Network degradation"]["reason"] in {"confidence_saturated", "max_hypotheses"}
assert result["timing"]["generation_seconds"] >= 0
assert result["knowledge_allowed"] is True
```

Add a second test asserting ablation receives `knowledge_allowed=false` and no knowledge projection fields.

- [ ] **Step 2: Run RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_run_sock_shop_confidence_discovery.py --basetemp .tmp-confidence-discovery-red
```

Expected: fail because runner is missing.

- [ ] **Step 3: Implement offline discovery contract**

Implement a pure function:

```python
def run_confidence_discovery(method_input: dict, model_call: Callable[[dict], dict]) -> dict:
    start = time.monotonic()
    hypotheses: list[dict] = []
    stopping: dict[str, dict] = {}
    for category, config in method_input["yaml_category_summary"]["categories"].items():
        state = ConfidenceState(
            category=category,
            min_hypotheses=config["min_hypotheses"],
            max_hypotheses=config["max_hypotheses"],
            tau=config["tau"],
            coverage_target=config["coverage_target"],
        )
        required_motifs = {item["motif"] for item in config["top_motifs"]}
        seen_for_category: list[dict] = []
        while True:
            response = model_call({
                "method": method_input["method"],
                "knowledge_allowed": method_input["knowledge_allowed"],
                "category": category,
                "category_config": config,
                "seen_hypotheses": seen_for_category,
            })
            hypothesis = response["hypothesis"]
            novelty = judge_novelty(hypothesis, seen_for_category, required_motifs)
            motifs = set(hypothesis.get("motifs", []))
            decision = state.observe(novelty.novel, motifs, required_motifs)
            hypothesis["category"] = category
            hypothesis["novel"] = novelty.novel
            hypothesis["novelty_reasons"] = novelty.reasons
            hypothesis["stop_snapshot"] = decision.__dict__
            hypotheses.append(hypothesis)
            seen_for_category.append(hypothesis)
            if decision.stop:
                stopping[category] = decision.__dict__
                break
    return {
        "method": method_input["method"],
        "knowledge_allowed": method_input["knowledge_allowed"],
        "hypotheses": hypotheses,
        "stopping": stopping,
        "timing": {"generation_seconds": round(time.monotonic() - start, 3)},
        "human_review": "pending",
        "knowledge_base_updated": False,
    }
```

It must:

1. create `ConfidenceState` per category;
2. call the model once per category iteration;
3. classify novelty with `judge_novelty`;
4. append hypothesis with novelty reasons and stop snapshot;
5. stop category only by confidence or max;
6. write timing in seconds.

The CLI may read the DeepSeek key only when invoked with `--model deepseek`; tests must use fake model output and must not read environment variables or key files.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_run_sock_shop_confidence_discovery.py --basetemp .tmp-confidence-discovery-green
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/run_sock_shop_confidence_discovery.py tools/tests/test_run_sock_shop_confidence_discovery.py
git commit -m "feat: run confidence-stopped Sock Shop discovery"
```

## Task 6: Compile, Gate, and Runtime Plan

**Files:**
- Create: `tools/run_sock_shop_confidence_runtime.py`
- Test: `tools/tests/test_run_sock_shop_confidence_runtime.py`

- [ ] **Step 1: Write contract tests**

Use fake hypotheses and assert:

```python
assert plan["methods"]["native-full"]["runtime_candidates"] == 2
assert plan["methods"]["native-full"]["gate_failed"] == 1
assert plan["timing_fields"] == [
    "generation_seconds",
    "compile_seconds",
    "gate_seconds",
    "runtime_seconds",
    "washout_seconds",
    "total_wall_clock_seconds",
]
```

- [ ] **Step 2: Run RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_run_sock_shop_confidence_runtime.py --basetemp .tmp-confidence-runtime-red
```

Expected: fail because runtime planner is missing.

- [ ] **Step 3: Implement runtime planner**

The implementation must define two explicit adapters in `tools/run_sock_shop_confidence_runtime.py`:

```python
def compile_hypothesis_to_mutation(hypothesis: dict, output_dir: Path) -> dict:
    """Write one mutation YAML and return path, sha256, kind, target, and method metadata."""


def build_runtime_invocation(candidate: dict, report_path: Path, execute: bool) -> dict:
    """Return the exact command metadata for runtime execution; run it only when execute=True."""
```

It must:

1. convert hypotheses into mutation YAML;
2. write mutation SHA-256;
3. run static gate and server-side dry-run in CLI mode;
4. refuse to overwrite non-empty output directories;
5. execute runtime only when `--execute` is present;
6. record method timing and report paths.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_run_sock_shop_confidence_runtime.py --basetemp .tmp-confidence-runtime-green
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/run_sock_shop_confidence_runtime.py tools/tests/test_run_sock_shop_confidence_runtime.py
git commit -m "feat: plan Sock Shop confidence runtime"
```

## Task 7: Review and Final Report

**Files:**
- Create: `tools/review_sock_shop_confidence_experiment.py`
- Test: `tools/tests/test_review_sock_shop_confidence_experiment.py`

- [ ] **Step 1: Write review tests**

Use fixture reports to assert:

```python
assert summary["methods"]["native-full"]["stable_weaknesses"] == 2
assert summary["methods"]["chaosatlas-ablation"]["stable_weaknesses"] == 1
assert summary["methods"]["native-full"]["stable_weaknesses_per_hour"] == 1.5
assert summary["human_review"] == "pending"
assert summary["knowledge_base_updated"] is False
```

- [ ] **Step 2: Run RED**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_review_sock_shop_confidence_experiment.py --basetemp .tmp-confidence-review-red
```

Expected: fail because reviewer is missing.

- [ ] **Step 3: Implement reviewer**

Reviewer must produce:

1. method comparison table;
2. category contribution table;
3. timing table;
4. stable weakness definition;
5. non-claim boundaries;
6. `human_review=pending`;
7. `knowledge_base_updated=false`.

- [ ] **Step 4: Run GREEN**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_review_sock_shop_confidence_experiment.py --basetemp .tmp-confidence-review-green
```

Expected: pass.

- [ ] **Step 5: Commit**

```powershell
git add tools/review_sock_shop_confidence_experiment.py tools/tests/test_review_sock_shop_confidence_experiment.py
git commit -m "feat: review Sock Shop confidence comparison"
```

## Task 8: End-to-End Offline Smoke

**Files:**
- Modify: `docs/ARCHIVE_MAP.md`
- Create after run: `artifacts/experiments/sock_shop_yaml_confidence_2026-08-14-r1/manifest.json`

- [ ] **Step 1: Build inputs**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' .\tools\build_sock_shop_confidence_inputs.py --raw-yaml raw_yaml --output artifacts\experiments\sock_shop_yaml_confidence_2026-08-14-r1
```

Expected: manifest and method input JSONs are written.

- [ ] **Step 2: Run fake discovery smoke**

Run the discovery runner with `--fake-model` first. Expected: both methods produce hypotheses, confidence traces, and timing without network calls.

- [ ] **Step 3: Run focused tests**

Run:

```powershell
& 'C:\Users\23741\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest tools/tests/test_yaml_confidence_categories.py tools/tests/test_yaml_confidence_stopping.py tools/tests/test_build_sock_shop_confidence_inputs.py tools/tests/test_run_sock_shop_confidence_discovery.py tools/tests/test_run_sock_shop_confidence_runtime.py tools/tests/test_review_sock_shop_confidence_experiment.py --basetemp .tmp-confidence-final
```

Expected: all tests pass.

- [ ] **Step 4: Scan staged files**

Run a staged sensitive scan before commit. Expected: zero strict high-risk hits.

- [ ] **Step 5: Commit**

```powershell
git add docs/ARCHIVE_MAP.md artifacts/experiments/sock_shop_yaml_confidence_2026-08-14-r1 tools/yaml_confidence_categories.py tools/yaml_confidence_stopping.py tools/build_sock_shop_confidence_inputs.py tools/run_sock_shop_confidence_discovery.py tools/run_sock_shop_confidence_runtime.py tools/review_sock_shop_confidence_experiment.py tools/tests/test_yaml_confidence_categories.py tools/tests/test_yaml_confidence_stopping.py tools/tests/test_build_sock_shop_confidence_inputs.py tools/tests/test_run_sock_shop_confidence_discovery.py tools/tests/test_run_sock_shop_confidence_runtime.py tools/tests/test_review_sock_shop_confidence_experiment.py
git commit -m "feat: prepare Sock Shop YAML confidence comparison"
```

## Acceptance Criteria

- [ ] Five-category YAML summary reports 1935 total YAML and 1506 included first-scope YAML.
- [ ] The five category counts match: 341 Pod, 428 Network, 352 Stress, 263 Protocol/DNS, 122 Workflow/Schedule.
- [ ] Both methods use identical category thresholds and stopping rules.
- [ ] `native-full` input includes knowledge permission; `ChaosAtlas-ablation` input explicitly excludes knowledge projection and historical evidence.
- [ ] Discovery traces include novelty decisions, Beta posterior inputs, upper95, coverage, stop reason, and timing.
- [ ] Runtime is not executed unless explicitly requested with an execution flag.
- [ ] Review output compares stable weaknesses, nonrepeatable candidates, no-impact candidates, total time, and stable weaknesses per hour.
- [ ] `human_review=pending` and `knowledge_base_updated=false` appear in every final manifest/report.
- [ ] No push is executed as part of implementation.
