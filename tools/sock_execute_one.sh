#!/bin/bash
# Sock Shop 候选执行器：完整生命周期（基线→注入→自然结束→恢复→清理）
# 用法: bash tools/sock_execute_one.sh <svc> <fault> <curl_path> <duration_sleep>
set -e
SVC=$1          # carts|catalogue|payment|shipping
FAULT=$2        # delay|loss
PATH_URL=$3     # curl 路径
MUT="/mnt/c/APP/project/chaos/artifacts/sock-shop/mutations-httpchaos/sock-${SVC}-${FAULT}.yaml"
export KUBECONFIG=/root/.kube/config

IP=$(kubectl get pod -n sock-shop-lab -l name=$SVC -o jsonpath='{.items[0].status.podIP}')
echo "=== [$SVC-$FAULT] IP=$IP ==="

echo "--- 基线（3次）---"
docker exec chaos-kind-control-plane sh -c 'for i in 1 2 3; do s=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$0:80$1 2>/dev/null); e=$(date +%s%N); echo "  基线 $i: HTTP $R $(( (e-s)/1000000 ))ms"; done' $IP $PATH_URL | tail -3

echo "--- apply $FAULT ---"
kubectl apply -f $MUT 2>&1 | tail -1
sleep 15

echo "--- 注入中（5次）---"
docker exec chaos-kind-control-plane sh -c 'for i in 1 2 3 4 5; do s=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$0:80$1 2>/dev/null); e=$(date +%s%N); echo "  注入 $i: HTTP $R $(( (e-s)/1000000 ))ms"; done' $IP $PATH_URL | tail -5

echo "--- 等 duration 自然结束（35s）---"
sleep 35

echo "--- 恢复测量 ---"
docker exec chaos-kind-control-plane sh -c 'for i in 1 2 3; do s=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$0:80$1 2>/dev/null); e=$(date +%s%N); echo "  恢复 $i: HTTP $R $(( (e-s)/1000000 ))ms"; done' $IP $PATH_URL | tail -3

echo "--- 清理 CR + 重启 pod 恢复网络 ---"
PHC=$(kubectl get podhttpchaos -n sock-shop-lab --no-headers 2>/dev/null | awk '{print $1}')
[ -n "$PHC" ] && kubectl patch podhttpchaos $PHC -n sock-shop-lab -p '{"metadata":{"finalizers":[]}}' --type=merge >/dev/null 2>&1 && kubectl delete podhttpchaos $PHC -n sock-shop-lab >/dev/null 2>&1
kubectl delete httpchaos -n sock-shop-lab --all >/dev/null 2>&1
kubectl rollout restart deploy/$SVC -n sock-shop-lab 2>&1 | tail -1
sleep 20
IP2=$(kubectl get pod -n sock-shop-lab -l name=$SVC -o jsonpath='{.items[0].status.podIP}')
docker exec chaos-kind-control-plane sh -c 's=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 http://$0:80$1 2>/dev/null); e=$(date +%s%N); echo "  重启后验证: HTTP $R $(( (e-s)/1000000 ))ms" 2>/dev/null' $IP2 $PATH_URL | tail -1
echo "=== [$SVC-$FAULT] 完成 ==="
