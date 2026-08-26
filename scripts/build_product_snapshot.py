from __future__ import annotations

import argparse
import shutil
from pathlib import Path

PRODUCT_DIRS = ("src", "cli", "projects", "docs", "scripts", "examples")
ROOT_FILES = ("README.md", "AGENTS.md", ".gitignore", "pyproject.toml", "pytest.ini")
COMPAT_WRAPPERS = ("chaosatlas.py", "run_closed_loop.py", "chaosatlas_batch.py")
PRODUCT_TESTS = ("test_repository_architecture.py",)
COPY_IGNORE = shutil.ignore_patterns("__pycache__", "*.py[cod]", "*.egg-info")
LEGACY_RUNTIME_FILES = (
    "build_deployment_capability_pool.py",
    "causal_identity.py",
    "chaos_eater_adapter/llm_backend.py",
    "chaosatlas.py",
    "chaosatlas_batch.py",
    "chaosatlas_adapters.py",
    "chaosatlas_contracts.py",
    "chaosatlas_hypothesis.py",
    "chaosatlas_runtime_preflight.py",
    "classify_runtime_result.py",
    "compile_rca_regression.py",
    "compile_scenario_node.py",
    "decision_engine.py",
    "deepseek_advisory.py",
    "defense_knowledge.py",
    "defense_promotion_stage.py",
    "deployment_capability.py",
    "deployment_improvement.py",
    "discovery_to_rca.py",
    "environment_fingerprint.py",
    "evidence_action_planner.py",
    "evidence_collectors.py",
    "experiment_policy.py",
    "experiment_policy_feedback.py",
    "experiment_policy_schema.py",
    "feedback_protocol.py",
    "fresh_deploy.py",
    "hypothesis_registry.py",
    "knowledge_migration_audit.py",
    "kubernetes_evidence.py",
    "kubernetes_lifecycle_executor.py",
    "kubernetes_project_adapter.py",
    "phase6_audit.py",
    "planned_evidence.py",
    "policy_calibration.py",
    "policy_controller.py",
    "policy_selection_gate.py",
    "project_onboarding.py",
    "rca_loop.py",
    "rca_runtime_loop.py",
    "recovery_contract.py",
    "registry_policy_signal.py",
    "registry_shadow.py",
    "run_chaos_experiment.py",
    "run_deployment_scenario.py",
    "run_live_improvement.py",
    "runtime_applicability_gate.py",
    "sock_shop_rca.py",
    "stop_policy.py",
    "validate_knowledge_base.py",
    "validate_rca_loop.py",
    "weakness_promotion_stage.py",
)


def build_snapshot(root: str | Path, destination: str | Path) -> Path:
    root_path = Path(root).resolve()
    destination_path = Path(destination).resolve()
    destination_path.mkdir(parents=True, exist_ok=True)
    if any(destination_path.iterdir()):
        raise ValueError(f"snapshot destination must be empty: {destination_path}")

    for directory in PRODUCT_DIRS:
        source = root_path / directory
        if source.exists():
            shutil.copytree(source, destination_path / directory, dirs_exist_ok=True, ignore=COPY_IGNORE)

    product_tests = root_path / "tests"
    legacy_tests = root_path / "tools" / "tests"
    tests_source = product_tests if (product_tests / PRODUCT_TESTS[0]).exists() else legacy_tests
    if tests_source.exists():
        tests_destination = destination_path / "tests"
        tests_destination.mkdir(parents=True, exist_ok=True)
        for test_name in PRODUCT_TESTS:
            source = tests_source / test_name
            if source.exists():
                shutil.copy2(source, tests_destination / test_name)
    fixtures_source = root_path / "tests" / "fixtures"
    if fixtures_source.exists():
        shutil.copytree(
            fixtures_source,
            destination_path / "tests" / "fixtures",
            dirs_exist_ok=True,
            ignore=COPY_IGNORE,
        )

    for name in ROOT_FILES:
        source = root_path / name
        if source.exists():
            shutil.copy2(source, destination_path / name)

    tools_destination = destination_path / "tools"
    tools_destination.mkdir(parents=True, exist_ok=True)
    wrapper = (
        "from pathlib import Path\n"
        "import sys\n\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))\n"
        "from chaosatlas.cli import main\n\n"
        "if __name__ == '__main__':\n"
        "    raise SystemExit(main())\n"
    )
    for name in COMPAT_WRAPPERS:
        (tools_destination / name).write_text(wrapper, encoding="utf-8")
    legacy_source = root_path / "tools"
    for relative in LEGACY_RUNTIME_FILES:
        source_relative = relative
        if relative == "chaosatlas.py" and (legacy_source / "_legacy_chaosatlas.py").exists():
            source_relative = "_legacy_chaosatlas.py"
        elif relative == "chaosatlas_batch.py" and (legacy_source / "_legacy_chaosatlas_batch.py").exists():
            source_relative = "_legacy_chaosatlas_batch.py"
        source = legacy_source / source_relative
        if not source.exists():
            continue
        destination_name = "_legacy_" + relative if relative in {"chaosatlas.py", "chaosatlas_batch.py"} else relative
        target = tools_destination / destination_name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a clean ChaosAtlas product snapshot.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--destination", required=True)
    args = parser.parse_args(argv)
    print(build_snapshot(args.root, args.destination))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
