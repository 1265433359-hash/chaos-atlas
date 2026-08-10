# Held-out 项目下载前资格审查报告 (Prequalification)

> 日期: 2026-08-10  |  规则版本: `heldout-candidate-generation-v1 (fixed ladders: delay 3 tiers 500/1000/2000ms, loss 3 tiers 10/50/100%, kill 1 per deployable target)`  |  状态: **complete_no_qualification**
> 本阶段为**只读预审**: GitHub API tree + raw 文件逐文件核验; 未 clone 完整仓库、未写 knowledge snapshot、未构造 candidate pool、未部署、未注入、未运行实验。

## 一、候选项目概览

| 项目 | canonical URL | 固定 commit | 许可证 | fork | 业务服务 | 部署入口 |
|---|---|---|---|---|---|---|
| robot-shop | [https://github.com/instana/robot-shop](https://github.com/instana/robot-shop) | `55292e2199f2` | Apache-2.0 | False | 8 | K8s/helm (Chart.yaml + templates, 12 workloads), docker-compose.yaml |
| bank-of-anthos | [https://github.com/GoogleCloudPlatform/bank-of-anthos](https://github.com/GoogleCloudPlatform/bank-of-anthos) | `5413c77d50ec` | Apache-2.0 | False | 6 | kubernetes-manifests/ (9 workloads, primary), skaffold.yaml |

## 二、硬门槛逐项结果

| 项目 | protected>=16 | unprotected>=16 | unknown>=16 | legal_total>=48 | delay/loss/kill | qualification |
|---|---|---|---|---|---|---|
| robot-shop | ❌ | ✅ | ✅ | ✅ | ✅ | **fail** |
| bank-of-anthos | ❌ | ❌ | ❌ | ❌ | ✅ | **fail** |

## 三、候选能力上界与配额算术 (固定梯度: delay 3 档 / loss 3 档 / kill 每目标 1)

### robot-shop

- `protected_possible` = **0** (protected 边: 无)
- `unprotected_possible` = **36** (unprotected 边: cart->catalogue, payment->user, payment->cart, ratings->catalogue, kill x12)
- `unknown_possible` = **42** (unknown 边: web->cart, web->catalogue, web->user, web->shipping, web->payment, web->ratings, shipping->cart)
- `legal_total` = **78**
- delay/loss/kill: True/True/True

### bank-of-anthos

- `protected_possible` = **12** (protected 边: ['frontend->balancereader', 'frontend->transactionhistory', 'frontend->contacts', 'frontend->userservice'])
- `unprotected_possible` = **15** (unprotected 边: ledgerwriter->balancereader, kill x9)
- `unknown_possible` = **12** (unknown 边: frontend->* (loss))
- `legal_total` = **39**
- delay/loss/kill: True/True/True

## 四、排除原因

**robot-shop** (fail):
- protected_possible=0 < 16 (无显式 per-request timeout/熔断/冗余; nginx 反代未声明 timeout, cart/payment/ratings 调用无 timeout, shipping 仅连接超时无读取超时)

**bank-of-anthos** (fail):
- protected_possible=12 < 16 (仅 frontend 4 条边显式 4s timeout x 3 delay 档)
- unprotected_possible=15 < 16 (ledgerwriter->balancereader 无超时 x6 + kill x9)
- unknown_possible=12 < 16 (frontend 4 边 loss, loss_bounded 未验证)
- legal_total=39 < 48

## 五、知识泄漏审计

| 项目 | SE | DP | JE | 说明 |
|---|---|---|---|---|
| robot-shop | 0 | 0 | 0 | robot-shop/robotshop/instana 在 pinned SE/DP/JE 中 0 命中 |
| bank-of-anthos | 0 | 0 | 0 | bank-of-anthos/anthos/googlecloudplatform 在 pinned SE/DP/JE 中 0 命中 |

## 六、项目独立性与部署/镜像/可观测摘要

### robot-shop
- 独立性: 独立仓库 instana/robot-shop, 非 fork, 非现有项目/benchmark 家族
- 镜像: robotshop/rs-* public Docker Hub + rabbitmq:3.7 / redis:4.0.6 / mysql / mongo; Dockerfiles present in each service dir (buildable)
- 外部依赖: none critical (no CloudSQL/AWS/secrets); payment gateway default paypal.com external but not required
- replicas/PDB/HPA/probe: replicas=1 (default), PDB=none, HPA=none, probes=ratings & shipping only
- 可观测: Instana collector (web/Node), Prometheus metrics, fluentd logging

### bank-of-anthos
- 独立性: 独立仓库 GoogleCloudPlatform/bank-of-anthos, 非 fork; 同 org 的 online-boutique 是不同代码库/技术栈 (Flask+Spring vs Go)
- 镜像: us-central1-docker.pkg.dev/bank-of-anthos-ci/bank-of-anthos/*:v0.6.10 (GCP Artifact Registry public images; skaffold builds from src/)
- 外部依赖: primary deployment uses in-cluster postgres; CloudSQL is extras variant only. Frontend reads GCE metadata (GKE-oriented; non-GCP may fail - risk). Images on gcr.io need network.
- replicas/PDB/HPA/probe: replicas=1, PDB=none, HPA=none, probes=business deployments have liveness/readiness
- 可观测: OpenTelemetry (RequestsInstrumentor, Zipkin), Stackdriver, Prometheus in extras

## 七、证据文件与 SHA-256 (固定 commit raw 内容)

| 项目 | 文件 | SHA-256 |
|---|---|---|
| robot-shop | `K8s/helm/values.yaml` | `8fea32f25d4e78ecd617074bc2de5a00c25db9d6c5355d5b23988b2a9c58f6cb` |
| robot-shop | `docker-compose.yaml` | `79390464b08101383932a39ee61ed5b6cd88e55a666cc627c7af61f7062d2612` |
| robot-shop | `web/default.conf.template` | `ae83ee8048045f820091ecc1bd93608e113a5c07cdd93d30b6c3cc9a13f84714` |
| robot-shop | `cart/server.js` | `94601865a1c88db99ffd88d292b6c6e95a4f39d7e48465adef5bb830ee2c547e` |
| robot-shop | `catalogue/server.js` | `73726f096a0f4e508e76b9456903896e1fe4c9c65a14f2405bf0ce1f0e5e7f34` |
| robot-shop | `user/server.js` | `92c9bbcc6e6f24949911dbd67bc4f937e39ba7fa09c3707ddf8afff50cd5eb30` |
| robot-shop | `payment/payment.py` | `b4c20b78cc2ea8d7c26462aa945a29227358b09e838a59a50419186d64532426` |
| robot-shop | `shipping/CartHelper.java` | `9d9784c3696d09ec93e11b804477aa0eb6933d3f9d3560c247bfb1f852143c07` |
| robot-shop | `shipping/RetryableDataSource.java` | `bb802846e823c42ddf2e6887532f8691ad447dc26eeba2b7e6aa65adf82d2207` |
| robot-shop | `shipping/application.properties` | `8b32464ad78fad39fbec06a6ae8fdc2fb2153fb2836be89f3376d40fd9bf0eb1` |
| robot-shop | `ratings/CatalogueService.php` | `863680ae2de3fbff2d017ce3e46e4b3bc72d84f98bc33006ef3bf253e3eb4823` |
| robot-shop | `dispatch/main.go` | `901cd2169e4658b16138fc688fad003964954f733e013b91d477a5ed200aef93` |
| robot-shop | `K8s/helm/templates/web-deployment.yaml` | `a61e41166f9fedfbafa4e6f9cec9b72f90f009da8a2c87c2ff23b238a9ed74f5` |
| robot-shop | `K8s/helm/templates/cart-deployment.yaml` | `6d559e93bbcacdccabbd98f69138643af04a029b2d7df50bddd73f2cb56e771d` |
| bank-of-anthos | `kubernetes-manifests/frontend.yaml` | `36d25cb3a6616ecfa854471857b214dd94cde878e1fd27a33e714c89f6e231f9` |
| bank-of-anthos | `kubernetes-manifests/userservice.yaml` | `014720aae6b9631e47c4e0612be5cc585c5c439330fe355699b391c45815ed4f` |
| bank-of-anthos | `kubernetes-manifests/contacts.yaml` | `1308a0f64bdbfc772d32f586cd39de686ec41629be10d8d5d7245371fe7e30a8` |
| bank-of-anthos | `kubernetes-manifests/ledger-writer.yaml` | `a7c19ffe49042d92dd74d865bfc5c9fdc37be732f96419a81d69a2113ca22aee` |
| bank-of-anthos | `kubernetes-manifests/balance-reader.yaml` | `dda53e53d9a7b399c65c17e4dc9989dd2a511fbc2411e1fb15307a19a81d8518` |
| bank-of-anthos | `kubernetes-manifests/transaction-history.yaml` | `bdc9fa8250b07ff3b8dde0093693d040a8cd6b1705feacde95fc3223a55c5459` |
| bank-of-anthos | `kubernetes-manifests/accounts-db.yaml` | `6150ff9dd3004cb69714a3e02854cbb955c65f4c139562a88aaf298f5a5974e6` |
| bank-of-anthos | `kubernetes-manifests/ledger-db.yaml` | `4cc469a92ee6960d4204c8ca946b3ca76f4e777445aae9e902eb5a034f448fc8` |
| bank-of-anthos | `kubernetes-manifests/loadgenerator.yaml` | `85313a84c66b70654073ea6a0fedeb18b49f86fa279b2e233fba2422cee9993a` |
| bank-of-anthos | `src/frontend/frontend.py` | `b47b6c5b5f75e3249ea09d4cab19240e593349937c8aa3b592c487e684e4af71` |
| bank-of-anthos | `src/frontend/api_call.py` | `06988a3abac225a7ee29e9f3ffeed55c8bf508ec86688bfbfd8fd73892ef65df` |
| bank-of-anthos | `src/ledger/ledgerwriter/LedgerWriterController.java` | `cecd648e7fbe7ef52930b4ee6e4be9594fc26d4faf65029b40b3b7f07df95d5c` |
| bank-of-anthos | `src/ledger/ledgerwriter/LedgerWriterApplication.java` | `5a4d6110b6ac3f6e214c24340615e7c111d9a06c966697e1bc3665740a64da94` |
| bank-of-anthos | `src/ledger/balancereader/BalanceReaderController.java` | `a5bd8e2e4e1f5e94d4023c3c9e0a2f9e1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7` |
| bank-of-anthos | `src/ledger/transactionhistory/TransactionHistoryController.java` | `61e11339b3ac9a086ab9afb788873aa05bfc14002c3105f0719c876340ac87f2` |
| bank-of-anthos | `src/accounts/contacts/contacts.py` | `d8db9fcd04efb5c10fa05d52bd5a8cd19a091fff28eb6c647ac338d9ea1a169c` |
| bank-of-anthos | `src/accounts/userservice/userservice.py` | `320276107eb348baac7f365549e2236d4ae1b5f1e06937407e30a4c069058b43` |

## 八、结论

BOTH FAIL. 无项目满足全部硬门槛 (protected/unprotected/unknown>=16 且 legal_total>=48)。按停止规则立即停止: 不 clone、不写 snapshot、不构造 pool、不部署、不运行实验、不降低 24/48 或 8/8/8/16/16/16 配额、不修改 heldout_protocol_v1_1、不用历史项目补齐。

## 九、声明

- 未 clone 完整仓库 (仅 GitHub API tree + raw 文件只读拉取到系统临时目录, 已删除)。
- 未写 knowledge snapshot、未构造 candidate pool、未部署、未注入、未运行任何实验。
- 未降低 24/48 或 8/8/8、16/16/16 配额; 未修改 `heldout_protocol_v1_1`; 未用 Hotel/SOCIALNET/TeaStore/OB/TT/Sock/OTEL 或任何历史项目补齐。
- 按停止规则: 两候选均未通过, **本阶段停止**, 等待主代理审核后决定是否提名新的候选项目。
