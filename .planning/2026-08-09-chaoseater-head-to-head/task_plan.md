# Ours vs ChaosEater Head-to-Head Protocol

目标：在相同输入、候选预算、模型预算、执行环境和评价标准下，比较完整方法与 ChaosEater 的候选发现能力、成本、解释质量和运行安全性。

## Protocol phases

| Phase | Status | Deliverable |
|---|---|---|
| P0 Freeze and preregistration | pending | versions, prompts, budgets, primary endpoint, exclusion rules |
| P1 Atomic blind selection | pending | same-input ranked candidates from ours, official CE, CE adapter, random baseline |
| P2 Candidate normalization | pending | union candidate pool, semantic deduplication, no truth leakage |
| P3 Runtime ground truth | pending | baseline/injection/recovery/cleanup evidence and blinded labels |
| P4 Closed-loop selection | pending | equal two-round feedback budget and exploration cost |
| P5 Holdout/generalization | pending | unseen project/version/fault family evaluation |
| P6 Statistical decision | pending | paired bootstrap/mixed model, superiority or inconclusive verdict |

## Primary decision rule

Primary metric is hidden-set weakness recall@K. Declare ours superior only when the paired 95% CI for ours minus ChaosEater is above 0 and the safety non-inferiority checks pass. Otherwise report tie/inconclusive. Never use the current M1 adapter result as an independent ChaosEater claim.
