#!/bin/bash
----
렉이 걸리는 문제 해결 필요----
# @log: 자동화 스크립트용 파일
# --- 설정 변수 (운영 환경에 맞게 변경) ---
IMAGE_TAR="bus_rt_monitoring_b3.0.31_doc.tar.gz"
# YAML_FILE="k8s-cronjob.yaml"
YAML_FILE="k8s-mq-architecture.yaml"
INI_FILE="/home/gj_anly/ipconfig_cryp.ini"

echo "🚀 에어갭 운영 환경 K8s 배포 파이프라인 시작..."

# 1. K8s 환경에 도커 이미지 로드
echo "📦 1/3: 쿠버네티스 엔진에 도커 이미지 로드 중 (minikube image load)..."
minikube image load $IMAGE_TAR

# 2. ConfigMap (ini 설정 파일) 무중단 갱신
# 기존 ConfigMap이 있어도 에러 없이 덮어쓰는 스마트 업데이트 방식 적용
echo "⚙️ 2/3: ipconfig_cryp.ini 파일 K8s ConfigMap으로 주입 중..."
kubectl create configmap ipconfig-cmap --from-file=$INI_FILE -o yaml --dry-run=client | kubectl apply -f -

# 3. 쿠버네티스 CronJob 적용 (스케줄 및 이미지 배포)
echo "☸️ 3/3: K8s CronJob Manifest(YAML) 적용 중..."
kubectl apply -f $YAML_FILE

# ==========================================================
# 💡 [핵심 추가] 작업자 파드 무중단 재시작 (Rolling Update)
# ==========================================================
echo "🔄 작업자(Consumer) 파드들에게 새로운 설정/이미지를 적용하기 위해 교대(Restart)를 지시합니다..."
kubectl rollout restart deployment/analy-consumer
# ==========================================================

# 4. 최종 상태 확인
echo "====================================="
echo "✅ 배포 프로세스가 완료되었습니다!"
echo "📌 현재 CronJob 상태:"
kubectl get cronjob
echo "📌 현재 실행 중인 파드 상태:"
kubectl get pods