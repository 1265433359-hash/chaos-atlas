# Held-out Candidate Prequalification: Batch 2

Date: 2026-08-10  
Protocol: `heldout_protocol_v1_1`

## Result

This batch has **no qualifying project**. The fixed gates remain `protected >= 16`, `unprotected >= 16`, `unknown >= 16`, and `legal_total >= 48`, plus a reproducible Kubernetes/Helm/Compose deployment, observability, and executable delay/loss/kill paths.

The review used GitHub API metadata, repository trees, and bounded raw-file reads. It did not clone a complete repository, create snapshots or pools, deploy, inject faults, or run an experiment.

## Candidate decisions

| Candidate | Fixed ref | Decision | Blocking reason |
|---|---|---|---|
| YAS | `179e813568c345bad3fce985088b5535e57481aa` | fail | Retry/circuit exists, but no bounded per-request timeout; protected upper bound is 0 |
| Robot Shop | `55292e2199f2fb00a165b1f7d3045fe7f8922038` | fail | `0/36/42`, legal `78`; protected gate fails |
| Bank of Anthos | `5413c77d50ec4d4b6b5ef4c1350f463123be97e6` | fail | `12/14/12`, legal `38` |
| cloud-native-ecommerce-platform | `211157cd6921f363457579b1775a4557577d89f3` | fail | Too few deployable targets for unprotected/legal minima |
| Quarkus Super Heroes | `d95fce081000cc945d3e7a9748359cef6a91e01c` | fail | Small fixed service graph; legal upper bound below `48` |
| Coolstore Microservices | `2fe75484298968b68a767b351871d32d93632aa3` | fail | Small fixed service graph; legal upper bound below `48` |
| Pitstop | `3813291853007e60e4aab912fe6e8ccc7aa3a134` | fail | Small API/service graph |
| ThingsBoard | `684f92bbfd0cf48015b6e42f5592bc0c2fc18038` | fail | No confirmed unified Kubernetes/Helm entrypoint |
| IBM cloud-native-starter | `62f55c434c6928847981af9ef171550df827fbec` | fail | Collection of independent tutorials, not one project |
| ultimate-stack | `5b94132675a54490489d8f65757e70b60043d428` | fail | About five business services; quota impossible |
| tetrate-todos | `baa455c6f028096efa9dfc23bfc0c742995e65ce` | fail | About four business services; quota impossible |
| Terraform ecommerce on GKE | `b25304fe6867c86ae9ee7e5b49fb8e05b39b0c6a` | fail | Online Boutique project-family leakage |
| UHI | `a1c471437551d33b84174158c837258ce5708d29` | fail | Unified deployment boundary unresolved |
| Acme Air | `f16122729873ef0449ea276dfb2d2a1d45bebb40` | fail | No confirmed required deployment entrypoint |
| µBench | `176c8f14f2740414436078d5dcd969d38dd4acd4` | fail | Generates synthetic apps; no fixed application contract |
| AWS retail-store-sample-app | `1a28474f2461459f42e6b393db59e7d1434d4aec` | fail | Six application services; legal candidate upper bound below `48` |
| eShopOnContainers (`dev`) | `b6965936842cab32553543c1abe8a68714956f44` | fail | Envoy `connect_timeout` is connection-level; only one request timeout route, protected `< 16` |
| habitcentric | `f7b32260dc90bcbdfacad40cde8a893ef28a289c` | fail | Four main services; quota impossible |
| OCI Micronaut Mushop | `69772b97696a49b7e03c8edb2b501fa72b6e73f8` | fail | Small fixed service graph; quota impossible |
| Unguard | `7272adc616b692aa1a0063be3d4ff8c973b6cc87` | fail | Service/target upper bound below `48` |

## Important classification rules applied

- A connection timeout is not a request timeout.
- Retry or circuit-breaker configuration without a bounded request timeout is not protected-delay evidence.
- Load generators, test tools, and synthetic benchmark generators are not business kill targets.
- Projects from an already used benchmark family cannot fill the held-out denominator.
- A large source tree or many infrastructure files does not establish one executable comparable application.

## Stop decision

No candidate from this batch may proceed to full intake, snapshot construction, candidate-pool freezing, deployment, pilot, or formal execution. The protocol quotas were not lowered, and historical projects were not used to fill a deficit.

The current evidence therefore supports only the honest status: **candidate search batch exhausted without a pass**.
