# ChaosAtlas

**ChaosAtlas** (TestNode-Centered Chaos Analysis and Knowledge Base) is a
research workspace for evidence-bound chaos testing of real microservice
projects. The repository turns a real chaos YAML into a small, test-node-
centered impact slice, checks whether the slice is reachable and injectable,
runs a bounded experiment, classifies the result, and stores the result as a
versioned knowledge card.

本项目用于论文写作、跨项目对比实验和知识库消融实验。它不是一个生产
环境部署仓库，也不把“注入成功”自动解释成“系统有韧性”。所有结论都必须
绑定源码、固定版本、运行时证据、恢复证据和明确的适用边界。

## Research Scope

The current archive contains four case-study families:

| Case study | Pinned source | Role in the study | Knowledge cards |
|---|---|---|---:|
| Train Ticket | `FudanSELab/train-ticket` @ `313886e99befb94be6cd45f085c98e0019f59829` | First end-to-end test-node-centered workflow; CPU and network delay boundary cases | 7 |
| Online Boutique | `GoogleCloudPlatform/microservices-demo` @ `9a4616e77f0f9cbcbecaf27d711c38890dda1404` | Cross-project comparison of delay, loss, probe restart, and multi-fault semantics | 8 |
| OpenTelemetry Demo | `open-telemetry/opentelemetry-demo` @ `2e72d8bcdf754603e956406808630bc9663c992c` | Observability-aware comparison and repeated no-timeout behavior | 2 |
| Sock Shop | `markfink/sock-shop` (pinned artifacts and lab manifest) | Held-out cross-project validation and direct comparison with ChaosEater; combines call-contract and deployment-availability evidence | 0 formal cards; project evidence archived |

The held-out and knowledge-ablation tracks under `artifacts/experiments/` are
supplementary evaluation material. They are not merged into the case-study
claims unless their protocol gates and independent oracle checks pass.

### Sock Shop: the fourth project and the ChaosEater comparison

Sock Shop is the external-transfer project for the method, not just another
case study. It tests whether rules learned from the first three projects move
to a new service distribution and whether the same evidence chain can cover
both application call contracts and deployment availability.

The final HTTP-edge result is **6/8 weakness and 2/8 defended**. The two
defended edges are `orders -> payment` and `orders -> shipping`, where the
real order path enforces a 5-second `Future.get(timeout, SECONDS)` boundary.
The earlier `8/8 weakness` result came from direct service-level measurement
and is retained only as a corrected historical result.

Counting note: this paper-facing number counts the two defended service edges.
The machine ledger also contains delay/loss variants; its contract-layer
summary reports 4/8 + 4/8 because the two loss variants are inferred from the
shared timeout contract rather than independently re-run. These denominators
must not be mixed in a manuscript.

Against ChaosEater (`47c4e44`), the comparison is intentionally layered:
ChaosEater's Sock Shop run identified deployment availability risks such as
single-replica services and missing PDB/HPA/probe coverage, while this method
also verified request-level delay/loss behavior, source-level timeout
contracts, business responses, recovery, and cleanup. The contribution is
therefore complementary coverage and auditable attribution, not a claim of
overall superiority or statistical significance.

## Method In One Line

```text
real YAML -> TestNode -> local impact slice -> applicability gate
-> bounded single-factor run -> baseline/effect/recovery evidence
-> conservative classification -> knowledge card -> next selection
```

The applicability gate is deliberately ordered: YAML validity, target
existence, workload reachability, selector match, actual injection, observed
effect, recovery, and cleanup. A platform prerequisite failure or unreachable
workload is an experiment outcome, not a defense result.

## Repository Map

| Path | What belongs here |
|---|---|
| `raw_yaml/` | Source chaos YAML corpus; preserve original paths and hashes |
| `artifacts/<project>/` | Project-scoped inventories, slices, manifests, runtime reports, and knowledge cards |
| `artifacts/experiments/` | Comparison pilots, held-out pools, frozen snapshots, ablations, and execution ledgers |
| `reporting/` | Human-readable findings, issue drafts, submission tracking, and evidence packaging |
| `tools/` | Deterministic catalog builders, selectors, runners, classifiers, validators, and query tools |
| `tools/tests/` | Regression tests for gates, runners, classifiers, selectors, and artifact builders |
| `governance/` | Safety and review rules for isolated execution and external reporting |
| `task_plan.md`, `findings.md`, `progress.md` | Persistent research plan, discoveries, and session history |

The archive conventions and paper-facing evidence boundaries are documented
in [`docs/ARCHIVE_MAP.md`](docs/ARCHIVE_MAP.md). The comparison matrix is in
[`docs/EXPERIMENT_CATALOG.md`](docs/EXPERIMENT_CATALOG.md), and the knowledge
card lifecycle is in [`docs/KNOWLEDGE_BASE.md`](docs/KNOWLEDGE_BASE.md).
The retention and cleanup decisions for workspace clutter are recorded in
[`docs/ARCHIVE_CLEANUP.md`](docs/ARCHIVE_CLEANUP.md).

## Evidence Vocabulary

- `confirmed_static`: source or manifest evidence is present, but runtime reachability is not proven.
- `confirmed_runtime`: the request path and the intended mutation were observed in a bounded run.
- `validated_runtime`: the card passed the knowledge-base schema and has runtime evidence.
- `candidate` or `pending`: useful for planning, not a paper result.
- `blocked_by_platform_prerequisite`: the environment prevented a fair injection; never call this defended or unprotected.
- `not_reachable`: the candidate is retained as a counterexample or applicability result.
- `hypothesis`: an explicit, unverified edge or explanation.

Response preservation, latency degradation, client timeout, server-side
completion after client timeout, and defense observed are separate fields in
the reports. Do not collapse them into a single pass/fail score.

## Safe Local Checks

These commands only inspect or validate existing artifacts. They do not deploy
services or inject faults:

```powershell
python tools/validate_knowledge_base.py --root artifacts/train-ticket/knowledge_base
python tools/validate_knowledge_base.py --root artifacts/online-boutique/knowledge_base
python tools/validate_knowledge_base.py --root artifacts/opentelemetry-demo/knowledge_base
python tools/query_knowledge_base.py --list
python -m pytest tools/tests -q
```

Runtime commands require an explicitly approved isolated namespace and a
working Kubernetes/Chaos Mesh environment. Read
[`governance/README.md`](governance/README.md) and the relevant project
artifact README before running them.

## Paper Preparation

The current strongest paper-facing materials are:

- [`artifacts/train-ticket/paper_prep_stage_summary.md`](artifacts/train-ticket/paper_prep_stage_summary.md)
- [`artifacts/train-ticket/README.md`](artifacts/train-ticket/README.md)
- [`reporting/projects_matrix.md`](reporting/projects_matrix.md)
- [`reporting/submission_index.md`](reporting/submission_index.md)
- [`artifacts/experiments/llm_knowledge_ablation_protocol_v1.md`](artifacts/experiments/llm_knowledge_ablation_protocol_v1.md)

Numbers in a manuscript should cite the smallest machine-readable source
available (`.json`, `.csv`, or a run ledger) and then the human-readable report.
The limitations section must state the fixed commit, project count, sample
size, observation budget, missing trace/production SLO, and any platform block.

The knowledge-base ablation and final method head-to-head comparison are
currently parked future work. Their files are retained for continuation, but
their incomplete intermediate results must not be presented as final paper
evidence or a superiority claim.

## Private GitHub Handoff

The intended repository name is `chaos-atlas` and the display name is
`ChaosAtlas`. The owner has confirmed this name; the repository is still local
until the exact GitHub account, URL, and upload permission are confirmed. The
workspace currently contains no remote-upload command or GitHub credentials.

Before any upload, complete the local checklist in
[`docs/GITHUB_PRIVATE_HANDOFF.md`](docs/GITHUB_PRIVATE_HANDOFF.md), review
`git diff --stat`, and explicitly approve the exact remote URL and branch. No
`git remote add`, `git push`, or GitHub CLI command is run by this archive pass.

## License and Data Boundary

The repository contains third-party source checkouts and generated evidence.
Check the upstream licenses before making the repository public. Keep secrets,
cluster credentials, private endpoints, raw tokens, and unredacted logs out of
the archive. Generated binaries and local environment state should remain
ignored unless a paper reproducibility package explicitly requires them.
