# CVE 可利用性复核（2026-08-25）

## 结论

当前没有证据支持为现有 issue 申请 CVE。最接近的两条 checkout 阻塞发现仍是韧性问题，而不是已证明的远程拒绝服务漏洞。

## 复核对象

| 候选 | 已证实事实 | CVE 关键缺口 | 当前处置 |
|---|---|---|---|
| Online Boutique checkout / `#3474` | payment/shipping/email 被故障注入时同步等待；payment 丢包可等待到客户端 10 秒边界；shipping 可能累加两次调用延迟 | 故障来自 Chaos Mesh 内部注入，不是攻击者控制；没有并发资源耗尽、服务级不可用或攻击者权限边界证据 | 保持普通 resilience issue |
| OpenTelemetry Demo emailservice 草稿 | email 丢包时 `PlaceOrder` 在 6/6 复现中到达调用方 deadline；静态报告记录无 HTTP client timeout | 同样依赖内部网络故障注入；没有普通外部请求触发的资源耗尽证据；版本/部署由外部 Helm chart 组合 | 先走普通/安全预咨询，不申报 CVE |

## 入口与权限边界

- Online Boutique 的实验清单中，`checkoutservice` Service 是默认 ClusterIP；对外暴露的是 frontend。现有 `ob_client.py` 通过内部 checkout/cart 地址调用，不能作为互联网攻击入口证明。
- OTel 的最小清单同样只定义 ClusterIP `checkout` Service（`artifacts/opentelemetry-demo/manifests/otel_lab_manifest.yaml:50-60`），现有 client 是实验客户端，不是匿名公网攻击路径证明。

## 证据边界

已有结果证明的是：

- 人为施加 100% 丢包或秒级延迟后，请求同步阻塞或达到实验客户端 deadline；
- 这是应用级 timeout/fallback 缺失的韧性观察。

已有结果没有证明：

- 攻击者无需控制集群网络即可稳定触发同一故障；
- 少量或合理速率的普通请求能够耗尽 goroutine、线程、连接、CPU 或内存；
- 影响会从单个请求扩大到服务级拒绝服务。

## 重新进入安全评估的门槛

只在隔离环境补齐以下证据后再联系 CNA/安全团队：

1. 从 frontend 或明确公开 API 出发，确认匿名/低权限攻击者的最小请求序列。
2. 不使用 Chaos Mesh 改网、杀 Pod 或人为阻断下游；仅用受控并发的普通请求复现。
3. 记录并发数、请求速率、活动连接、goroutine/线程、CPU、内存、5xx 和恢复时间，并证明存在服务级影响。
4. 在固定版本和至少一个对照修复版本上重复，确定受影响版本范围。

在上述门槛未满足前，不应在公开 issue 中使用 CVE、RCE、DoS vulnerability 等定性；若后续门槛满足，OpenTelemetry Demo 应先按其 `SECURITY.md` 私下报告，由维护者/CNA 判断是否分配 CVE。

