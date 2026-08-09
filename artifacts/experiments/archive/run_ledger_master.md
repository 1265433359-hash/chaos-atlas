# 主实验台账（Master Run Ledger）

> 合并：历史 83 次 lifecycle-complete 注入 + r2 24 次尝试 = 107 条运行记录
> 独立注入：**91**（历史 83）+ r2 有效观测 17（8 首跑 + 9 确认）
> r2 无效基线：**7/24**（checkout 服务批次中途重启）

## 状态口径

| 状态 | 数量 | 说明 |
|---|---|---|
| confirmation_run | 9 | 见 run_ledger_master.json |
| independent_injection | 91 | 见 run_ledger_master.json |
| invalid_baseline | 7 | 见 run_ledger_master.json |

## 独立注入（historical 83）按项目

| 项目 | 数量 |
|---|---|
| OB | 41 |
| OTEL | 28 |
| TT | 22 |

## 派生文件（不计入独立实验）

derived/prediction/summary 共 67 个文件，详见 run_ledger_master.json `derived_files`。

## r2 无效基线文件（显式记录）

- `artifacts/experiments/execution/remediation/r2_runs/OB-CART-LOSS-100_confirm.json`
- `artifacts/experiments/execution/remediation/r2_runs/OB-CHECKOUT-LOSS-100_confirm.json`
- `artifacts/experiments/execution/remediation/r2_runs/OB-CHECKOUT-LOSS-100_confirm2.json`
- `artifacts/experiments/execution/remediation/r2_runs/OB-CURRENCY-LOSS-100_confirm.json`
- `artifacts/experiments/execution/remediation/r2_runs/OB-EMAIL-LOSS-100_confirm.json`
- `artifacts/experiments/execution/remediation/r2_runs/OB-PRODUCTCATALOG-LOSS-100_confirm.json`
- `artifacts/experiments/execution/remediation/r2_runs/OB-SHIPPING-LOSS-100_confirm.json`
