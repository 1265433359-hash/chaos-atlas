# ChaosAtlas Three-Arm Protocol v1

Status: offline preregistration. No DeepSeek request is authorized by this file.

## Arms

- `ChaosAtlas-KB`: full ChaosAtlas input with frozen general and project knowledge views.
- `ChaosAtlas-noKB`: identical common input and prompt skeleton, with all knowledge views removed.
- `ChaosEater-adapter`: frozen ChaosEater FaultScenarioAgent selection logic mapped to the same candidate IDs. It receives no ChaosAtlas knowledge.

Official end-to-end ChaosEater remains a supplementary track and is not pooled into the primary paired statistic.

## Frozen comparison unit

`project family x frozen commit x candidate pool x arm x seed`

The 10 registered projects are P01-P10. A project that fails the deployment gate remains in the registry as `environment_blocked` or `out_of_domain`; it is not silently replaced after seeing model output.

## Selection parameters

- Candidate pool: 16 candidates per project, generated from four target roles and four fault families.
- Candidate budget: `K=8`.
- Registered seeds: `1001`, `1002`, `1003`.
- Candidate order: lexicographic by `candidate_id`, then deterministic Fisher-Yates permutation seeded by the registered seed. The same order is supplied to all three arms for a project/seed.
- Selection output: strict JSON; malformed or out-of-pool selections are `method_invalid`.

## Model parameters (pre-registered, not yet approved for use)

- Endpoint: `https://api.deepseek.com/v1`.
- Model: `deepseek-v4-flash`.
- Temperature: `0.2`.
- Maximum output tokens: `2048`.
- Timeout: `180 s`.
- At most one transport retry for timeout, connection reset, HTTP 429, or transient 5xx.

## Execution protocol

`clean -> health gate -> baseline workload -> one bounded fault -> verify injection -> observe fixed window -> remove fault -> recovery health -> cleanup check`.

All arms use the same runner, observation window, recovery window, workload, oracle version, namespace policy, and cleanup policy. A shared execution is allowed only when evidence attribution and cost accounting remain separate.

## Validity and stopping rules

- A confirmed weakness requires two valid reproductions and complete evidence.
- `environment_blocked`, `method_invalid`, and `out_of_domain` are separate from method quality metrics.
- Three consecutive transport failures stop the run for human review.
- Any change to model, prompt, seed, K, candidate pool, oracle, runner, or retry policy creates a new protocol version.
- No model request is made until the user explicitly approves the consent checklist and monetary ceiling.
