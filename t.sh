#!/bin/bash

# 모니터링 갱신 주기 (초)
INTERVAL=2

while true; do
    clear
    echo "====================================================================="
    echo " 🐳 분석 모듈 모니터링 대시보드 | 갱신: ${INTERVAL}초 | $(date +'%Y-%m-%d %H:%M:%S')"
    echo "====================================================================="

    # 1. 컨테이너 실행 상태 파악 (이름으로 필터링)
    PRODUCER_COUNT=$(docker ps -f name=analy-producer --format="{{.Names}}" | wc -l)
    CONSUMER_COUNT=$(docker ps -f name=analy-consumer --format="{{.Names}}" | wc -l)
    REDIS_COUNT=$(docker ps -f name=redis-queue --format="{{.Names}}" | wc -l)

    echo -e "\n[1. 시스템 가동 상태]"
    echo " - Redis 큐     : ${REDIS_COUNT} 개 가동 중"
    echo " - 반장(Producer): ${PRODUCER_COUNT} 개 가동 중"
    echo " - 작업자(Consumer): ${CONSUMER_COUNT} 개 가동 중 (목표: 20개)"

    # 2. Redis 큐 작업 진척도 확인
    echo -e "\n[2. 작업 진행 상황 (Redis)]"
    REDIS_CONTAINER=$(docker ps -q -f name=redis-queue | head -n 1)

    if [ -n "$REDIS_CONTAINER" ]; then
        # 작성하신 container.py의 키 이름(job_queue, working_buses)을 참조했습니다.
        REMAINING_JOBS=$(docker exec $REDIS_CONTAINER redis-cli llen job_queue 2>/dev/null || echo "0")
        WORKING_JOBS=$(docker exec $REDIS_CONTAINER redis-cli scard working_buses 2>/dev/null || echo "0")
        
        echo " - 대기 중인 일거리 (job_queue)     : ${REMAINING_JOBS} 건"
        echo " - 처리 중인 일거리 (working_buses) : ${WORKING_JOBS} 건"
    else
        echo " - ⚠️ Redis 컨테이너를 찾을 수 없습니다."
    fi

    # 3. 시스템 리소스 사용량 (CPU 점유율 높은 순으로 5개만)
    echo -e "\n[3. 리소스 점유율 (CPU TOP 5)]"
    # --no-stream 옵션으로 현재 순간의 스냅샷만 가져옵니다.
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | head -n 6

    # 4. 최근 발생한 에러 로그 캐치 (첫 번째 Consumer 기준)
    echo -e "\n[4. 최근 에러 로그 감시]"
    FIRST_CONSUMER=$(docker ps -q -f name=analy-consumer | head -n 1)
    if [ -n "$FIRST_CONSUMER" ]; then
        ERROR_LOGS=$(docker logs --tail 50 $FIRST_CONSUMER 2>&1 | grep -i "error" | tail -n 3)
        if [ -n "$ERROR_LOGS" ]; then
            echo "$ERROR_LOGS"
        else
            echo " - ✅ 최근 50줄 내 발견된 에러 없음"
        fi
    else
        echo " - ⚠️ 확인 가능한 작업자 컨테이너가 없습니다."
    fi

    echo -e "\n====================================================================="
    echo " (종료하려면 Ctrl + C 를 누르세요)"
    
    sleep $INTERVAL
done