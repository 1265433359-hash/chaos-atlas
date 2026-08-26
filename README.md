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

## Paper Mainline

当前论文主线见 [`docs/CHAOSATLAS_PAPER_MAINLINE.md`](docs/CHAOSATLAS_PAPER_MAINLINE.md)：

1. 构建 TestNode、局部影响子图、适用性门禁、证据链和知识库的初始架构；
2. 在 Online Boutique、OpenTelemetry Demo 和 Train Ticket 三个真实项目中验证真实 issue 发现能力；
3. 在方法改进后，于 Sock Shop 上比较使用知识库的完整方法与知识库消融方法；
4. 复现官方 ChaosEater 原生流程，作为不同测量层的阶段参照。

same-pool、预选候选池和 `ChaosEater-adapter` 结果均为冻结历史材料，不进入当前论文主线统计。实验原始目录保持原路径不变。

## Research Scope

The archive retains four case-study families, but the paper mainline assigns
them different roles:

| Case study | Pinned source | Role in the study | Knowledge cards |
|---|---|---|---:|
| Train Ticket | `FudanSELab/train-ticket` @ `313886e99befb94be6cd45f085c98e0019f59829` | Stage-two real-project capability validation; timeout/deadline, call-contract and reachability boundaries | 7 |
| Online Boutique | `GoogleCloudPlatform/microservices-demo` @ `9a4616e77f0f9cbcbecaf27d711c38890dda1404` | Cross-project comparison of delay, loss, probe restart, and multi-fault semantics | 8 |
| OpenTelemetry Demo | `open-telemetry/opentelemetry-demo` @ `2e72d8bcdf754603e956406808630bc9663c992c` | Observability-aware comparison and repeated no-timeout behavior | 2 |
| Sock Shop | `markfink/sock-shop` (pinned artifacts and lab manifest) | Stage-three improved-method comparison: ChaosAtlas-full versus YAML15 Ablation; historical comparison material retained separately | 0 formal cards; project evidence archived |

The old held-out, same-pool, and preselected-candidate tracks under
`artifacts/experiments/` are frozen supplementary material. The current Sock
Shop full-versus-ablation discovery/runtime track is part of the paper mainline;
its exact denominators and review state remain governed by the machine ledgers.

### Sock Shop: improved-method ablation

Sock Shop is the controlled real-project stage for the improved-method
comparison. It tests whether the knowledge view changes autonomous hypothesis
generation and stable weakness discovery under the same business oracle,
runtime lifecycle, and evidence rules.

The current paper-facing headline is recorded in
`docs/SOCK_SHOP_THREE_METHOD_STAGE_REVIEW_2026-08-16.md`: all 114 Full families
have an applicability disposition; 96 entered the runtime cohort, 88 completed
two injections, 8 route-aware DNSChaos families were platform-blocked, and 18
families were rejected by the static gate. The 88 injected families contain 15 stable weaknesses, 3 mixed
results, and 70 no-impact results. The final YAML15 Ablation generated 458 raw
hypotheses, reduced them to 51 families, completed 46 families, and confirmed
9 stable weaknesses. The superseded 12-hypothesis / 2-weakness Ablation is
retained only as historical evidence.

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

Against historical ChaosEater material (`47c4e44`), the comparison is
intentionally layered and is not the pending official full-method experiment:
ChaosEater's Sock Shop run identified deployment availability risks such as
single-replica services and missing PDB/HPA/probe coverage, while this method
also verified request-level delay/loss behavior, source-level timeout
contracts, business responses, recovery, and cleanup. The contribution is
therefore a frozen comparison hypothesis, not a completed current three-method
head-to-head or a claim of overall superiority.

An older Sock Shop Minikube pilot completed `ChaosAtlas-full` and
`ChaosAtlas-ablation` only. Both used the same front-end PodKill mutation and
passed lifecycle cleanup; the official ChaosEater arm was environment-blocked.
That pilot is frozen and must not replace the current autonomous discovery and
ablation evidence.
See `docs/CHAOSATLAS_PROJECT_ARCHIVE_2026-08-13.md` for the exact boundary.

### Next four-project queue

The next active queue is `Online Boutique`, `OpenTelemetry Demo`, `Train Ticket`,
and `TeaStore`. Only `ChaosAtlas-full` and `ChaosAtlas-ablation` are in scope.
Online Boutique has a digest-pinned fresh manifest and is the only project
currently eligible for an authorized Namespace-first dry-run. OpenTelemetry
Demo is blocked on immutable image provenance, Train Ticket is blocked on
missing dependency definitions plus immutable image provenance, and TeaStore
remains blocked on source restoration. The first three may reuse deployment,
oracle, recovery, and collection tooling only after their fresh manifest and
baseline gates pass. The queue manifest is
`artifacts/experiments/chaosatlas_followup_four_projects_2026-08-13/queue_manifest.json`.

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
| `src/chaosatlas/` | Product package and stable orchestration namespaces |
| `projects/` | Versioned, secret-free project profiles |
| `tests/` | Product contract tests and offline fixtures |
| `scripts/` | Inventory, migration, boundary, and acceptance tools |
| `tools/` | Thin compatibility wrappers for the legacy command names |
| `docs/` | Product operations, architecture, and publication documentation |
| `ChaosAtlas-evidence` | Separate evidence archive for inputs, runs, reports, and knowledge snapshots |

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
python -m chaosatlas run --profile projects/sock-shop/profile.json --mode dry-run
python -m chaosatlas run --profile projects/online-boutique/profile.json --mode dry-run
python -m pytest tests/test_repository_architecture.py -q
```

Runtime commands require an explicitly approved isolated namespace and a
working Kubernetes/Chaos Mesh environment. Read
[`docs/operations/README.md`](docs/operations/README.md) and the relevant
project profile before running them.

## Paper Preparation

The current strongest paper-facing materials are:

- Paper-facing reports and experiment ledgers are retained in the separate
  `ChaosAtlas-evidence` archive.

Numbers in a manuscript should cite the smallest machine-readable source
available (`.json`, `.csv`, or a run ledger) and then the human-readable report.
The limitations section must state the fixed commit, project count, sample
size, observation budget, missing trace/production SLO, and any platform block.

The current Sock Shop real-project ablation has completed under the YAML15
protocol and remains subject to `human_review=pending`; it is part of the
mainline, while older ablation runs are frozen. ChaosEater native evidence is
retained as a different-measurement-layer stage reference; a same-layer,
machine-ledgered three-method comparison remains future work.
Same-pool/preselected-candidate results and the adapter comparison remain
frozen historical material and must not be presented as the mainline result or
as a superiority claim.

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
## Product Entry

The supported product entry point is now:

```powershell
python -m chaosatlas run --profile projects/sock-shop/profile.json --mode dry-run
python -m chaosatlas run --profile projects/sock-shop/profile.json --mode live --evidence-root ChaosAtlas-evidence-v2/runs/sock-shop/<run-id>
```

`live` mode is fail-closed: it requires the project profile's runtime gates,
an approved namespace and a working Kubernetes/Chaos Mesh environment. A
platform prerequisite failure is reported as `environment_blocked` and does
not become a weakness or defense claim.

The repository architecture and evidence migration policy are documented in
`docs/superpowers/specs/2026-08-26-repository-architecture-redesign-design.zh-CN.md`
and `docs/repository-migration/README.md`.

Runtime evidence belongs in the separate `ChaosAtlas-evidence` archive. The
legacy `tools/` entry points remain available during the compatibility period.
