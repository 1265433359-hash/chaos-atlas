"""Regression tests for the LLM knowledge-ablation Gate 0-2 remediation v2.

Covers the human-review fixes:
- Fix 1: LLM-generic uses generic-rules-only knowledge (no project names, service
  names, candidate IDs, evidence fields, file paths, or project results).
- Fix 4: the leakage audit scans historical project terms across all arms.
- Fix 6: formal pools are recorded as non-conforming to the pre-registered 48
  (40/30) and require a protocol amendment.
- Fix 7: the candidate_id -> mutation_path mapping exists and every mutation YAML
  is mode=one with a matching hash; the frozen pool mutation_path stays null.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import build_knowledge_ablation_gates0to2 as builder  # noqa: E402


GENERIC_RULES = ROOT / "artifacts" / "experiments" / "knowledge_ablation_generic_rules_v1.json"


def _json_text(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False)


@pytest.fixture(scope="module")
def generic_rules() -> dict:
    return json.loads(GENERIC_RULES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def leakage_audits() -> dict[str, dict]:
    audits = {}
    for proj in ("ESHOP", "SOCIALNET"):
        audits[proj] = json.loads(
            (ROOT / f"artifacts/experiments/knowledge_ablation_snapshots/{proj}/leakage_audit.json")
            .read_text(encoding="utf-8")
        )
    return audits


@pytest.fixture(scope="module")
def top_manifest() -> dict:
    return json.loads(
        (ROOT / "artifacts/experiments/knowledge_ablation_manifest_gate0to2.json").read_text(encoding="utf-8")
    )


class TestGenericRulesOnly:
    def test_generic_rules_sha_pinned(self):
        expected = builder.GENERIC_RULES_SHA
        actual = hashlib.sha256(GENERIC_RULES.read_bytes()).hexdigest()
        assert actual == expected, "generic rules file drifted from the pinned SHA"

    def test_llm_facing_sections_have_no_evidence_fields(self, generic_rules):
        for sec in ("selection_experience", "defense_pattern_library", "judgment_experience"):
            for item in generic_rules[sec]:
                keys = set(item.keys())
                forbidden = {"experiment_evidence", "corpus_evidence", "evidence_cases",
                             "evidence_files", "evidence_count", "source", "source_note"}
                assert not (keys & forbidden), f"{sec} entry {item.get('id')} leaks evidence fields: {keys & forbidden}"

    def test_llm_facing_sections_clean_of_historical_terms(self, generic_rules):
        text = _json_text({k: generic_rules[k] for k in
                           ("selection_experience", "defense_pattern_library", "judgment_experience")}).lower()
        for term in builder.HISTORICAL_TERMS:
            assert term.lower() not in text, f"generic rule text contains historical term {term!r}"


class TestLeakageAudit:
    def test_all_arm_scans_pass(self, leakage_audits):
        for proj, audit in leakage_audits.items():
            for scan in audit["arm_scans"]:
                assert scan["pass"], f"{proj} {scan['phase']} {scan['arm']} failed: {scan['prompt_file']}"

    def test_generic_rules_sections_pass(self, leakage_audits):
        for proj, audit in leakage_audits.items():
            gr = audit["generic_rules_file_scan"]["llm_facing_sections"]
            assert gr["pass"], f"{proj} generic-rules LLM sections failed: {gr}"

    def test_pools_have_no_historical_terms(self, leakage_audits):
        for proj, audit in leakage_audits.items():
            for phase in ("pilot", "formal"):
                pc = audit[f"pool_checks_{phase}"]
                assert not pc["historical_term_hits"], f"{proj} {phase} pool contains historical terms"
                assert pc["mutation_paths_all_null"], f"{proj} {phase} pool must keep mutation_path null"


class TestFormalConformance:
    def test_formal_48_not_met(self, top_manifest):
        fc = top_manifest["formal_pool_conformance"]
        assert fc["ESHOP/formal"]["pool_size_actual"] == 40
        assert fc["SOCIALNET/formal"]["pool_size_actual"] == 30
        assert fc["ESHOP/formal"]["requires_protocol_amendment"] is True
        assert fc["SOCIALNET/formal"]["requires_protocol_amendment"] is True
        # pilot matches the pre-registered 24 in both projects
        assert fc["ESHOP/pilot"]["pool_size_actual"] == 24
        assert fc["SOCIALNET/pilot"]["pool_size_actual"] == 24

    def test_manifest_notes_amendment_requirement(self, top_manifest):
        notes = " ".join(top_manifest["remediation_v2_notes"]).lower()
        assert "amendment" in notes


class TestMutationMapping:
    def test_mutation_map_hashes_match(self):
        for proj in ("ESHOP", "SOCIALNET"):
            mm = json.loads(
                (ROOT / f"artifacts/experiments/knowledge_ablation_mutations/{proj}/mutation_map.json")
                .read_text(encoding="utf-8")
            )
            assert mm["entries"], f"{proj} mutation map is empty"
            for cid, entry in mm["entries"].items():
                yaml_bytes = (ROOT / entry["mutation_path"]).read_bytes()
                assert hashlib.sha256(yaml_bytes).hexdigest() == entry["yaml_sha256"], f"{proj} {cid} yaml hash mismatch"

    def test_every_mutation_yaml_is_mode_one(self):
        for proj in ("ESHOP", "SOCIALNET"):
            mm = json.loads(
                (ROOT / f"artifacts/experiments/knowledge_ablation_mutations/{proj}/mutation_map.json")
                .read_text(encoding="utf-8")
            )
            for entry in mm["entries"].values():
                text = (ROOT / entry["mutation_path"]).read_text(encoding="utf-8")
                assert "mode: one" in text
                assert entry["mode"] == "one"
