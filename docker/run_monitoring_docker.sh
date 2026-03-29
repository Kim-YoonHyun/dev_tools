#!/bin/bash

# 참고: docker-compose.yml 내 Redis의 container_name이 'redis-server'라고 가정합니다.
# 만약 이름이 다르다면 아래 명령어들의 'redis-server' 부분을 수정해주세요.

watch -n 1 '
echo "====================================================="
echo " 📊 Docker Compose 분산 처리 실시간 대시보드"
echo "====================================================="
echo "[1] 작업 진행 상황 (Redis Queue)"

# 1. 전체 스케줄 목표량
echo -n " 🎯 총 목표 작업량 (total_target): "
docker exec -i redis-server redis-cli GET total_target 2>/dev/null

# 2. 큐에서 대기 중인 갯수
echo -n " 📦 남은 대기열 (job_queue): "
docker exec -i redis-server redis-cli LLEN job_queue 2>/dev/null

# 3. 중복 방지용 자물쇠 명부 (대기 중 + 작업 중)
echo -n " 🔒 중복 방지 예약 명단 (working_buses): "
docker exec -i redis-server redis-cli SCARD working_buses 2>/dev/null

# 4. 현재 CPU를 쓰며 일하고 있는 갯수
echo -n " 🔥 실제 연산 중인 버스 (active_buses): "
docker exec -i redis-server redis-cli SCARD active_buses 2>/dev/null

echo "-----------------------------------------------------"
echo "[2] 글로벌 집계 상황판 (전체 컨테이너 합산)"
# Redis Hash 값을 예쁘게 한 줄씩 출력합니다.
docker exec -i redis-server redis-cli HGETALL current_batch_stats 2>/dev/null | awk "NR%2==1 {printf \" %-10s : \", \$1} NR%2==0 {print \$1}"
echo ""
echo "====================================================="
echo "[3] 컨테이너별 실시간 자원 사용량 (CPU / Memory)"
# 쿠버네티스의 kubectl top pods 대신 docker stats를 1회(--no-stream) 출력하여 보여줍니다.
# consumer나 producer 컨테이너와 테이블 헤더(NAME)만 필터링하여 깔끔하게 보여줍니다.
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep -E "NAME|consumer|producer"
echo "====================================================="
'