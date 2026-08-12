# ChaosAtlas Project-Clustered Statistics

Status: **incomplete_missing_projects**. Observed projects: 1/10.

Seeds are repeated measurements within a project; LLM calls are not independent samples.

## Project summaries

| Project | Arm | Seeds | valid_output_rate | compiler_acceptance_rate | executable_rate | confirmed_weakness_yield | protected_target_yield | method_invalid_rate | environment_blocked_rate | call_chain_coverage | call_chain_depth | recovery_success | token_cost | human_review_time |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P02 | ChaosAtlas-KB | 1 | 1 | 1 |  | 0.5 | 0.5 |  |  |  |  | 1 | 3.518e+04 |  |
| P02 | ChaosAtlas-noKB | 1 | 1 | 1 |  | 0.5 | 0.5 |  |  |  |  | 1 | 3.455e+04 |  |
| P02 | ChaosEater-adapter | 1 |  |  |  |  |  |  |  |  |  |  | 9228 |  |
| P02 | ChaosEater-adapter-open | 1 | 1 | 1 |  | 1 | 0 |  |  |  |  | 1 | 2.377e+04 |  |

## KB minus noKB by project

| Project | valid_output_rate | compiler_acceptance_rate | executable_rate | confirmed_weakness_yield | protected_target_yield | method_invalid_rate | environment_blocked_rate | call_chain_coverage | call_chain_depth | recovery_success | token_cost | human_review_time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| P02 | 0 | 0 |  | 0 | 0 |  |  |  |  | 0 | 624 |  |

## Difference distributions across projects

| Metric | Projects | Mean | Median | SD | Min | Max |
|---|---:|---:|---:|---:|---:|---:|
| valid_output_rate | 1 | 0 | 0 | 0 | 0 | 0 |
| compiler_acceptance_rate | 1 | 0 | 0 | 0 | 0 | 0 |
| executable_rate | 0 |  |  |  |  |  |
| confirmed_weakness_yield | 1 | 0 | 0 | 0 | 0 | 0 |
| protected_target_yield | 1 | 0 | 0 | 0 | 0 | 0 |
| method_invalid_rate | 0 |  |  |  |  |  |
| environment_blocked_rate | 0 |  |  |  |  |  |
| call_chain_coverage | 0 |  |  |  |  |  |
| call_chain_depth | 0 |  |  |  |  |  |
| recovery_success | 1 | 0 | 0 | 0 | 0 | 0 |
| token_cost | 1 | 624 | 624 | 0 | 624 | 624 |
| human_review_time | 0 |  |  |  |  |  |
