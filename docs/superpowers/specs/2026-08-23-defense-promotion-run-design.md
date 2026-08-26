# Defense Promotion In `chaosatlas run`

## Goal

Make the existing runtime defense promotion step part of the auditable `chaosatlas run` lifecycle without scanning unrelated artifacts or allowing an unverified defense claim to influence future runs.

## Scope

This change closes the Phase 4 defense-feedback gap. It covers:

- explicit history input for repeated defensive runs;
- deterministic promotion and artifact publication;
- counterexample and validation-failure handling;
- regression/guard intent safety;
- offline and live-run integration tests.

It does not add automatic deployment patches, scan the whole artifacts tree, or make LLM output authoritative.

## Design

`chaosatlas run` receives an optional `--defense-history-root` pointing to a directory whose immediate child directories are immutable run roots. The orchestrator selects only children containing the required run artifacts (`run_manifest.json`, `classify.json`, `observe.json`, and `cleanup_report.json`). Selection is explicit and deterministic; malformed or non-defense children are reported as rejected inputs rather than silently treated as evidence.

When at least two independent runs satisfy the existing defense contract, the orchestrator calls `promote_repeated_defense` and writes a `promote_defense` stage plus `knowledge_promotion.json` under the current output directory. The promoted card and regression intents are copied into the configured `knowledge-root` only when that destination is explicitly supplied and the promotion result is `local_reusable`.

If a prior reusable card has a matching target/project identity but a new run fails the defense contract, the old card remains unchanged. The run writes `knowledge_conflict.json` containing the old card snapshot hash, the new run fingerprint, the failed gate, and a `contested` or `provisional` status. No executable guard is emitted for the conflicting evidence.

The promotion stage is checkpointed like other stages and is never run implicitly when `--defense-history-root` is absent. Dry-run mode can validate selection and promotion inputs but cannot produce runtime weakness or defense claims from synthetic evidence.

## CLI and Artifacts

New optional arguments:

```text
--defense-history-root PATH
--knowledge-write-root PATH
```

`--knowledge-root` remains read-only retrieval input. `--knowledge-write-root` is the explicit publication destination. The current run always writes:

- `promote_defense.json` (stage envelope);
- `knowledge_promotion.json` on success or a structured `not_run` result;
- `knowledge_conflict.json` only when contradictory evidence is found.

The stage payload includes selected run IDs, fingerprints, project/commit identity, claim type, promotion status, and all rejected input reasons.

## State Rules

- `local_reusable`: may generate `reproduce` and `guard` intents and affect next-run ranking.
- `provisional`: may generate only evidence-discrimination or reproduction intents.
- `contested`: remains historical and searchable but produces no executable intent.
- Any failed lifecycle, oracle, cleanup, identity, or mechanism-evidence check blocks promotion.

## Testing

Tests must cover: explicit child selection, duplicate fingerprint rejection, successful in-run promotion, read-only retrieval versus explicit publication, conflict artifact creation, preservation of the old card snapshot, and absence of executable guard for contested evidence. Existing defense and closed-loop suites must remain green.

## Non-Goals

- source-level RCA inference;
- automatic CVE scanning;
- automatic production changes;
- implicit artifact discovery outside the supplied history root;
- treating LLM confidence as evidence or promotion authority.
