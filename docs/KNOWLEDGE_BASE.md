# Knowledge Base Guide

The knowledge base is a retrieval and decision artifact, not a list of
conclusions. A card records what was tested, what was actually observed, what
remains unknown, and when the selector must stop repeating the same experiment.

## Card Layout

Each project knowledge base has an `index.json`, one JSON/Markdown pair per
card, and a generated `validation_report.json`:

```text
artifacts/<project>/knowledge_base/
  index.json
  KB-<project>-<family>-<path>-NNN.json
  KB-<project>-<family>-<path>-NNN.md
  validation_report.json
```

The validator requires the card identity, project commit, test-node descriptor,
test-node-centered graph, four-layer validation, and a non-empty `next_evidence`
list. The graph should distinguish static, runtime, hypothesis, and unreachable
edges.

## Four-Layer Validation

Cards follow the same gate used by the runners:

1. **Declaration:** the YAML parses and its test-node fields are meaningful.
2. **Resource:** selector/namespace/target exists in the isolated project.
3. **Business:** the workload and oracle are reachable and repeatable.
4. **Runtime:** injection, effect, observation, recovery, and cleanup are evidenced.

Only a card that reaches the runtime layer can support a defense or weakness
claim. A card may still be valuable when it stops at a blocked or unreachable
layer, but its status must say so.

## Retrieval Rules

Prefer exact matches on `family`, `operation`, target service, direction, and
oracle. Use project-wide or fault-family matches only as hypotheses. A matching
card with a `closed_runtime_boundary_no_reinjection` stop rule must prevent
automatic reinjection until new evidence changes the boundary.

Examples:

```powershell
python tools/query_knowledge_base.py --list
python tools/query_knowledge_base.py --family NetworkChaos --operation delay
python tools/query_knowledge_base.py --root-cause missing_timeout
```

The decision engine (`tools/decision_engine.py`) is the auditable rule layer.
The LLM is an optional decision enhancer and must not silently bypass hard
filters, frozen snapshots, or the applicability gate.

## Updating a Card

1. Preserve the previous version and add a new versioned card or an explicit
   audit entry; do not erase contradictory evidence.
2. Link every new claim to a run, source span, manifest, log, trace, or oracle.
3. Record the change reason, confidence, protocol/environment fingerprint, and
   next evidence.
4. Run `tools/validate_knowledge_base.py` for the affected project.
5. Add the validator result and the card ID to the session/protocol ledger.

The automatic backfill tool is useful for evidence linkage, but it is not
allowed to auto-delete or auto-rewrite rules. Contested selection, defense, and
judgment rules require human adjudication.

## Ablation Track Status

The knowledge-base selection ablation is currently **parked**. Its protocol,
snapshots, prompts, selection records, and leakage-audit artifacts are retained
for a later continuation, but Gate 1 onward, independent runtime truth, and
project-clustered statistical analysis are not complete. The current cards and
static selection records must not be presented as evidence that the knowledge
base improves LLM selection.

The same boundary applies to the unfinished final method head-to-head
comparison. Existing comparison artifacts remain useful as descriptive and
audit material, not as a completed superiority evaluation.

## Sensitive Data

Cards must use redacted references for secrets, credentials, tokens, and private
endpoints. The validator performs a warning-level sensitive-value scan; a clean
validator report is necessary but not sufficient for publication review.
