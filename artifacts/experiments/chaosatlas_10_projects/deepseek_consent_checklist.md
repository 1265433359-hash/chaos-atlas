# DeepSeek API Consent Checklist

Status: PREPARED BUT NOT APPROVED. No key has been read and no request has been sent.

## Required local gates before any request

Current checkpoint: structural input preparation, exact checkouts, and read-only cluster preflight are complete. The runtime gate matrix records `execution_ready=0/10` (nine environment-blocked projects and P04 out-of-domain under the current bounded budget); namespace-local deployment, baseline, recovery, cleanup, and independent oracle evidence remain incomplete. Therefore the key is still unread and no request is authorized.

- [x] All project commits and source-tree hashes are frozen.
- [ ] Each project that remains in scope passes a namespace-local deployment and health gate.
- [ ] A deterministic workload and recovery check are recorded for every in-scope project.
- [x] The method-neutral candidate pool is frozen and hashed before arm selection.
- [x] `ChaosAtlas-KB`, `ChaosAtlas-noKB`, and `ChaosEater-adapter` input bundles are generated from the same project evidence, with a leakage scan showing that oracle labels, prior results, and RCA are absent.
- [x] Seed list, candidate budget `K`, candidate ordering permutations, output schema, runner, oracle, timeout, retry policy, and cleanup procedure are frozen.
- [x] Local mock backend and schema validation pass without any external API.
- [x] P09 is checked out at the exact `cd0e...` commit; the earlier drift checkout is not used.
- [x] A human-readable cost/token ledger is ready and writes no secret material; the monetary ceiling remains pending explicit user confirmation.
- [x] Read-only cluster preflight is recorded: kind node Ready, Chaos Mesh PodChaos/NetworkChaos/StressChaos CRDs present, and no mutation performed.
- [x] `runtime_gate_matrix.json` records a per-project status and prevents blocked or out-of-domain projects from entering method-result statistics.

## Proposed call plan

Primary comparison arm: `ChaosAtlas-KB`, `ChaosAtlas-noKB`, and `ChaosEater-adapter`. Official end-to-end ChaosEater is supplementary and is not mixed into the primary paired statistic.

- Pilot: 2 projects x 3 arms x 3 registered seeds = 18 selection calls.
- Formal run: 10 projects x 3 arms x 3 registered seeds = 90 selection calls.
- Planned maximum: 108 successful selection calls.
- Transport retry allowance: at most one retry per call, so at most 216 HTTP attempts. Retries do not create new seeds or new results.
- No automatic LLM calls for oracle labeling; oracle is prepared independently and runs locally.

## Frozen model settings (proposal)

- Endpoint: `https://api.deepseek.com/v1` (OpenAI-compatible).
- Model: `deepseek-v4-flash`.
- Temperature: `0.2`.
- Max output tokens: `2048`.
- Request timeout: `180 s`.
- Output mode: strict JSON schema validation; malformed output is `method_invalid` and is not silently repaired.

## Token and cost ceiling (proposal)

- Per-call accounting limit: 8,192 input tokens and 2,048 output tokens.
- Hard aggregate ceiling: 1,200,000 billed tokens across all arms, including retries.
- Stop before the next request if the ledger reaches 1,200,000 tokens or the user-approved monetary ceiling, whichever comes first.
- The exact monetary ceiling must be confirmed against the account pricing visible to the user; this file intentionally does not assume a price that may change.

## Failure policy

- Retry once only for timeout, connection reset, HTTP 429, or transient 5xx, with bounded backoff.
- Do not retry 4xx authentication, quota, permission, or schema errors automatically.
- Preserve raw response metadata without the API key; redact authorization headers and secret-like strings before writing artifacts.
- A failed call is marked `transport_failed`; it is not converted into a selected candidate and does not change `K`, seed, prompt, or candidate order.
- Three consecutive transport failures stop the run and require human review.
- Any prompt/model/temperature/max-token/budget change creates a new protocol version and requires renewed consent.

## Explicit approval required

The checklist is not yet approval-ready because runtime gates and independent oracle evidence are incomplete. Before the first request, the user must explicitly approve this checklist (or an amended version), including the 108-call plan, model settings, 1.2M-token ceiling, retry policy, and the monetary ceiling. Until then, the only permitted actions are offline validation, local mock calls, deployment smoke tests, and schema/leakage audits. A real key must not be read as part of preparation.
