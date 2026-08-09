#!/bin/bash
# OB 混合池候选执行：基线 -> 注入 -> 自然结束 -> 恢复
# 用法: bash ob_mixed_execute.sh <mutation_name> <curl_path>
MUT=$1; PATH_URL=$2
export KUBECONFIG=/root/.kube/config
FE_IP=$(kubectl get pod -n online-boutique-lab -l app=frontend -o jsonpath='{.items[0].status.podIP}')

echo "=== 基线（3次）==="
docker exec chaos-eater-cluster-control-plane sh -c 'for i in 1 2 3; do s=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://$0:8080$1 2>/dev/null); e=$(date +%s%N); echo "  基线 $i: HTTP $R $(( (e-s)/1000000 ))ms"; done' $FE_IP "$PATH_URL" | tail -3

echo "=== apply $MUT ==="
kubectl apply -f /mnt/c/APP/project/chaos/artifacts/online-boutique/mutations-mixed/$MUT.yaml 2>&1 | tail -1
sleep 15

echo "=== 注入中（5次）==="
docker exec chaos-eater-cluster-control-plane sh -c 'for i in 1 2 3 4 5; do s=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://$0:8080$1 2>/dev/null); e=$(date +%s%N); echo "  注入 $i: HTTP $R $(( (e-s)/1000000 ))ms"; done' $FE_IP "$PATH_URL" | tail -5

echo "--- 等 duration 自然结束 ---"
sleep 35

echo "=== 恢复（3次）==="
docker exec chaos-eater-cluster-control-plane sh -c 'for i in 1 2 3; do s=$(date +%s%N); R=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 http://$0:8080$1 2>/dev/null); e=$(date +%s%N); echo "  恢复 $i: HTTP $R $(( (e-s)/1000000 ))ms"; done' $FE_IP "$PATH_URL" | tail -3

echo "=== 清理残留 ==="
kubectl delete networkchaos -n online-boutique-lab --all 2>&1 | tail -1
kubectl delete podnetworkchaos -n online-boutique-lab --all 2>&1 | tail -1
echo "=== $MUT 完成 ==="
