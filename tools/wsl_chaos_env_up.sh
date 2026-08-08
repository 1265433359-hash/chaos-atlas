#!/bin/bash
# 一键恢复 chaos 环境（WSL 重启后）
# 用法: bash wsl_chaos_env_up.sh  或 在 WSL 内: wsl -u root -e bash /mnt/c/APP/project/chaos/tools/wsl_chaos_env_up.sh
set -e

echo "=== 1. 加载内核模块 ==="
for m in ip_tables iptable_nat nf_nat nft_compat nf_tables br_netfilter overlay veth; do
  modprobe $m 2>/dev/null && echo "  loaded $m"
done

echo "=== 2. 启动 containerd + dockerd ==="
pgrep containerd >/dev/null || { nohup containerd > /tmp/containerd.log 2>&1 & sleep 4; echo "  containerd started"; }
pgrep dockerd >/dev/null || { nohup dockerd --host=unix:///var/run/docker.sock > /tmp/dockerd.log 2>&1 & sleep 10; echo "  dockerd started"; }
docker version --format '  Server {{.Server.Version}}' 2>&1 | head -1

echo "=== 3. 恢复 kind 集群 ==="
if docker ps -a --format '{{.Names}}' | grep -q chaos-kind-control-plane; then
  docker start chaos-kind-control-plane >/dev/null 2>&1 && echo "  kind node restarted"
  sleep 15
  export KUBECONFIG=/root/.kube/config
  kubectl get nodes 2>&1 | head -2
  kubectl wait --for=condition=Ready node/chaos-kind-control-plane --timeout=120s 2>&1 | tail -1
else
  echo "  kind node 不存在，需 kind create cluster --name chaos-kind"
fi

echo "=== 4. 验证 broute 表 ==="
ebtables-legacy -t broute -L 2>&1 | head -3

echo "=== DONE ==="
