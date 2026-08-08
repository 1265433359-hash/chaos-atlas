# HTTPChaos 可行性验证记录（自定义 WSL2 内核）

## 结论
**HTTPChaos 边级注入在自定义内核上完全可用**。这是本实验环境首次实现 HTTP 层（而非 NetworkChaos 服务级）的边级注入。

## 证据链

| 指标 | 基线 | 注入中（3s delay） | 清理后 |
|------|------|-------------------|--------|
| 集群内 node→pod 延迟 | ~7ms | **15038 ms** | ebtables 规则 0 条 |
| port-forward 路径 | 5-20ms | 不经过拦截路径 | 5ms |

- tproxy 日志确认：`request matched` + `delay: Some(3s)` 已应用于 front-end:8079 流量
- ebtables broute/nat 表在清理后 entries: 0（规则完整回收）

## 技术突破链条
1. WSL2 官方内核缺 `CONFIG_BRIDGE_EBT_BROUTE` → HTTPChaos 报 "kernel doesn't support ebtables 'nat' table"
2. 编译自定义内核（6.18.33.2 同源），内置：
   - `CONFIG_BRIDGE=y` + `CONFIG_BRIDGE_NF_EBTABLES_LEGACY=y`
   - `CONFIG_BRIDGE_EBT_BROUTE=y`（broute 表）
   - `CONFIG_BRIDGE_EBT_T_NAT=y` + `CONFIG_BRIDGE_EBT_REDIRECT=y`（tproxy 劫持关键）
   - `CONFIG_BRIDGE_EBT_T_FILTER=y` + 全部 EBT_* 目标
   - `CONFIG_ISO9660_FS=y`（docker-desktop VM 引导依赖）
   - `CONFIG_NETFILTER_XT_MATCH_ADDRTYPE=y`（dockerd iptables NAT 依赖）
3. 发现自定义内核破坏 docker-desktop VM 引导（对照实验：官方内核 20s 就绪）→ **绕开 docker-desktop，在 Ubuntu WSL 内跑 dockerd + kind**
4. WSL 内装 dockerd（containerd 29.1.3）+ 全套内核模块编译安装 + 镜像加速器（daocloud/dockerproxy）

## 关键配置（供复现）
- 内核源码: `C:\APP\tools\wsl-kernel-src`（git clone linux-msft-wsl-6.18.33.2）
- 编译产物: `C:\APP\tools\wsl-kernel\vmlinux`（466MB）
- `.wslconfig`: `kernel=C:\\APP\\tools\\wsl-kernel\\vmlinux` + `memory=20GB`
- 环境恢复脚本: `tools/wsl_chaos_env_up.sh`

## 诚实边界
- 集群内 node→pod 连接在 20GB 高负载下有 10s 基线噪声（port-forward 路径 5ms 干净）
- 本验证为单点测试（front-end 1 个边），候选池验证需要 6-8 个边级候选的完整生命周期
