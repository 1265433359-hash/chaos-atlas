# Sock Shop 独立轨道台账

> Sock Shop 证据异构，**不并入 run_ledger_master 的 107 条普通 run**。
> 13 条独立证据：8 条契约/真实链路边判定 + 5 条 availability pod-kill。

## 计数

| 类型 | 数量 |
|---|---|
| 契约/真实链路边判定 | 8 |
| availability pod-kill | 5 |
| 合计（独立轨道） | 13 |

## 普通 run records（对照，不混入）

```
普通 run records: 107（TT/OB/OTEL 历史 + OB r2）
Sock Shop independent track evidence: 单独统计，不并入 107
```

## 明细

| record_id | candidate | track | kind | verdict | source |
|---|---|---|---|---|---|
| sock-edge-SOCK-FRONTEND-CARTS-LOSS-100 | SOCK-FRONTEND-CARTS-LOSS-100 | direct | edge_verdict (not a runner run) | weakness | `sock_shop_verdicts.json` |
| sock-edge-SOCK-FRONTEND-CATALOGUE-LOSS-100 | SOCK-FRONTEND-CATALOGUE-LOSS-100 | direct | edge_verdict (not a runner run) | weakness | `sock_shop_verdicts.json` |
| sock-edge-SOCK-ORDERS-PAYMENT-LOSS-100 | SOCK-ORDERS-PAYMENT-LOSS-100 | real_chain | edge_verdict (not a runner run) | defended | `sock_shop_verdicts.json` |
| sock-edge-SOCK-ORDERS-SHIPPING-LOSS-100 | SOCK-ORDERS-SHIPPING-LOSS-100 | real_chain | edge_verdict (not a runner run) | defended | `sock_shop_verdicts.json` |
| sock-edge-SOCK-FRONTEND-CARTS-DELAY-2000 | SOCK-FRONTEND-CARTS-DELAY-2000 | direct | edge_verdict (not a runner run) | weakness | `sock_shop_verdicts.json` |
| sock-edge-SOCK-FRONTEND-CATALOGUE-DELAY-2000 | SOCK-FRONTEND-CATALOGUE-DELAY-2000 | direct | edge_verdict (not a runner run) | weakness | `sock_shop_verdicts.json` |
| sock-edge-SOCK-ORDERS-PAYMENT-DELAY-2000 | SOCK-ORDERS-PAYMENT-DELAY-2000 | real_chain | edge_verdict (not a runner run) | defended | `sock_shop_verdicts.json` |
| sock-edge-SOCK-ORDERS-SHIPPING-DELAY-2000 | SOCK-ORDERS-SHIPPING-DELAY-2000 | real_chain | edge_verdict (not a runner run) | defended | `sock_shop_verdicts.json` |
| sock-avail-carts | SOCK-CARTS-KILL-1 | availability | service_kill (availability sampling, not a runner run) | weakness (no redundancy: single replica, total outage on kill) | `avail_carts_kill.json` |
| sock-avail-front-end | SOCK-FRONT-END-KILL-1 | availability | service_kill (availability sampling, not a runner run) | weakness (no redundancy: single replica, total outage on kill) | `avail_frontend_kill.json` |
| sock-avail-orders | SOCK-ORDERS-KILL-1 | availability | service_kill (availability sampling, not a runner run) | weakness (no redundancy: single replica, total outage on kill) | `avail_orders_kill.json` |
| sock-avail-shipping | SOCK-SHIPPING-KILL-1 | availability | service_kill (availability sampling, not a runner run) | weakness (no redundancy: single replica, total outage on kill) | `avail_shipping_kill.json` |
| sock-avail-user | SOCK-USER-KILL-1 | availability | service_kill (availability sampling, not a runner run) | weakness (no redundancy: single replica, total outage on kill) | `avail_user_kill.json` |
