from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import classify_runtime_result
import project_onboarding
import validate_knowledge_base


def valid_profile() -> dict:
    return {
        "schema_version": "chaosatlas-project-profile-v1",
        "project_id": "sock-shop",
        "project_commit": "sock-shop-fixture-commit",
        "revision_kind": "fixture",
        "namespace_policy": {
            "allowed_namespaces": ["sock-shop-lab"],
            "isolation_required": True,
        },
        "source": {
            "manifest_roots": ["artifacts/sock-shop"],
            "source_roots": ["sources/sock-shop"],
        },
        "business_oracles": [
            {
                "id": "sock-shop-homepage",
                "kind": "http",
                "entrypoint": "/",
                "success_contract": "http_200",
            }
        ],
        "observability": {
            "logs": {"provider": "kubectl", "required": True},
            "traces": {"provider": "none", "required": False},
            "events": {"provider": "kubectl", "required": True},
        },
        "recovery": {
            "deadline_s": 180,
            "require_business_probe": True,
            "require_cleanup": True,
        },
        "cleanup": {"owner": "chaosatlas", "must_be_empty": True},
        "sensitive_data_policy": {
            "redact_fields": ["password", "secret", "token"],
            "allow_redacted_placeholders": True,
        },
    }


class ProjectOnboardingTest(unittest.TestCase):
    def test_valid_profile_passes_and_normalizes_relative_paths(self) -> None:
        profile = valid_profile()
        profile["source"]["manifest_roots"] = ["artifacts\\sock-shop"]

        result = project_onboarding.validate_project_profile(profile)

        self.assertTrue(result["valid"], result)
        self.assertEqual("artifacts/sock-shop", result["profile"]["source"]["manifest_roots"][0])

    def test_profile_rejects_default_namespace_and_absolute_paths(self) -> None:
        profile = valid_profile()
        profile["namespace_policy"]["allowed_namespaces"] = ["default"]
        profile["source"]["manifest_roots"] = ["C:/workspace/manifests"]

        result = project_onboarding.validate_project_profile(profile)

        self.assertFalse(result["valid"])
        self.assertIn("namespace_policy.allowed_namespaces cannot include default", result["errors"])
        self.assertTrue(any("manifest_roots" in error and "relative" in error for error in result["errors"]))

    def test_git_revision_requires_a_full_commit(self) -> None:
        profile = valid_profile()
        profile["revision_kind"] = "git"
        profile["project_commit"] = "short"

        result = project_onboarding.validate_project_profile(profile)

        self.assertFalse(result["valid"])
        self.assertIn("project_commit must be a 40-character hexadecimal commit", result["errors"])

    def test_response_preserved_never_becomes_defense(self) -> None:
        record = project_onboarding.result_contract_from_classification(
            "response_observed",
            claim_scope="front-end->catalogue",
            evidence_refs=["runtime/report.json"],
            injected=True,
            recovered=True,
        )

        self.assertTrue(record["valid"])
        self.assertEqual("response_preserved", record["result"])
        self.assertFalse(record["defense_claim_allowed"])

    def test_defended_requires_injection_and_evidence(self) -> None:
        record = project_onboarding.validate_result_contract(
            {
                "result": "defended",
                "claim_scope": "front-end->catalogue",
                "evidence_refs": [],
                "next_evidence": [],
                "injection_confirmed": False,
                "defense_claim_allowed": True,
            }
        )

        self.assertFalse(record["valid"])
        self.assertIn("defended requires confirmed injection", record["errors"])
        self.assertIn("defended requires evidence_refs", record["errors"])

    def test_gate_result_maps_environment_blocked_without_defense_claim(self) -> None:
        record = project_onboarding.result_contract_from_gate(
            {
                "decision": "blocked",
                "kind": "HTTPChaos",
                "namespace": "sock-shop-lab",
                "name": "catalogue-abort",
                "errors": ["http_tproxy_positive_evidence_missing"],
                "checks": {
                    "injector_prerequisite": {
                        "status": "blocked",
                        "blocker": "http_tproxy_positive_evidence_missing",
                    }
                },
            }
        )

        self.assertTrue(record["valid"])
        self.assertEqual("environment_blocked", record["result"])
        self.assertFalse(record["defense_claim_allowed"])

    def test_classifier_adds_contract_without_upgrading_response_observed(self) -> None:
        run = {
            "claim_scope": "front-end->catalogue",
            "preflight": {"decision": "ready_for_injection"},
            "lifecycle": {
                "injected": True,
                "injected_status": {"injected_count": 1},
                "recovered": True,
                "cleanup": {"resource_absent_after_delete": True},
            },
            "requests": [{"status_code": 200, "latency_ms": 20, "body": {"ok": True}}],
        }
        baseline = {"requests": [{"status_code": 200, "latency_ms": 20, "body": {"ok": True}}]}

        result = classify_runtime_result.classify(run, baseline)

        self.assertEqual("response_observed", result["classification"])
        self.assertEqual("response_preserved", result["result_contract"]["result"])
        self.assertFalse(result["result_contract"]["defense_claim_allowed"])

    def test_knowledge_validator_can_validate_profile_alongside_cards(self) -> None:
        report = validate_knowledge_base.validate(
            Path("artifacts/train-ticket/knowledge_base"),
            Path("artifacts/project_profiles/sock-shop/project_profile.json"),
        )

        self.assertTrue(report["project_profile"]["valid"], report["project_profile"])

    def test_input_inspection_reports_static_readiness_without_cluster_access(self) -> None:
        profile = valid_profile()
        profile["source"]["source_roots"] = ["artifacts/sock-shop"]

        report = project_onboarding.inspect_profile_inputs(profile, Path.cwd())

        self.assertEqual("ready_for_static_analysis", report["status"])
        self.assertEqual("not_checked", report["runtime"])

    def test_improvement_policy_requires_isolated_fresh_namespace(self) -> None:
        profile = valid_profile()
        profile["improvement_policy"] = {
            "fresh_namespace": "sock-shop-improvement-lab",
            "manifest_source": "artifacts/sock-shop/sock-shop-lab-manifest.yaml",
            "source_copy_required": True,
        }
        result = project_onboarding.validate_project_profile(profile)
        self.assertTrue(result["valid"], result)

        profile["improvement_policy"]["fresh_namespace"] = "sock-shop-lab"
        result = project_onboarding.validate_project_profile(profile)
        self.assertFalse(result["valid"])
        self.assertIn("improvement_policy.fresh_namespace must be isolated", result["errors"])


if __name__ == "__main__":
    unittest.main()
