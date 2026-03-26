#!/bin/bash


watch -n 1 '
echo "====================================================="
echo " 📊 K8s 분산 처리 실시간 대시보드"
echo "====================================================="
echo "[1] 작업 진행 상황 (Redis Queue)"
echo -n " 📦 남은 대기열 (job_queue): "
kubectl exec -i deployment/redis-master -- redis-cli LLEN job_queue
echo -n " 🏃 연산 중인 버스 (working_buses): "
kubectl exec -i deployment/redis-master -- redis-cli SCARD working_buses
echo "-----------------------------------------------------"
echo "[2] 글로벌 집계 상황판 (전체 10개 파드 합산)"
# Redis Hash 값을 예쁘게 한 줄씩 출력합니다.
kubectl exec -i deployment/redis-master -- redis-cli HGETALL current_batch_stats | awk "NR%2==1 {printf \" %-10s : \", \$1} NR%2==0 {print \$1}"
echo "====================================================="
echo "[3] 파드별 실시간 자원 사용량 (CPU / Memory)"
kubectl top pods | grep analy-consumer
echo "====================================================="
'

# watch -n 1 '
# echo "========================================="
# echo " 📊 K8s 분산 처리 모니터링 대시보드"
# echo "========================================="
# echo "[1] 작업 진행 상황 (Redis)"
# echo -n " 📦 남은 대기열 (job_queue): "
# kubectl exec -i deployment/redis-master -- redis-cli LLEN job_queue
# echo -n " 🏃 연산 중인 버스 (working_buses): "
# kubectl exec -i deployment/redis-master -- redis-cli SCARD working_buses
# echo ""
# echo "[2] 파드별 실시간 자원 사용량 (CPU / Memory)"
# kubectl top pods
# echo "========================================="
# echo "[3] 노드(서버) 전체 자원 여유량"
# kubectl top nodes
# '