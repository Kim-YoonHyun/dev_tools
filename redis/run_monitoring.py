import redis
import os
import time
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

def run_dashboard():
    # 환경변수에서 호스트를 찾고, 없으면 기본값(127.0.0.1) 사용
    redis_host = os.environ.get('REDIS_HOST', '127.0.0.1')
    
    try:
        r = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
        r.ping() # 연결 확인
    except Exception as e:
        print(f"❌ Redis 연결 실패 ({redis_host}:6379): {e}")
        return

    # 첫 번째 CPU 퍼센트 호출은 0.0을 반환하므로 미리 한 번 호출해 둡니다.
    if HAS_PSUTIL:
        psutil.cpu_percent(interval=None)

    while True:
        try:
            # 터미널 화면 지우기 (watch 명령어 효과)
            os.system('clear' if os.name == 'posix' else 'cls')
            
            print("=====================================================")
            print(" 📊 통합 분산 처리 실시간 대시보드 (Redis 직접 연결)")
            print("=====================================================")
            
            # --- [추가된 시스템 자원 모니터링 섹션] ---
            if HAS_PSUTIL:
                # CPU 정보 (직전 호출 이후의 평균 사용률)
                cpu_usage = psutil.cpu_percent(interval=None)
                cpu_remain = 100.0 - cpu_usage
                
                # 메모리 정보
                mem = psutil.virtual_memory()
                mem_total_gb = mem.total / (1024 ** 3)
                mem_used_gb = mem.used / (1024 ** 3)
                mem_remain_gb = mem.available / (1024 ** 3)
                mem_usage_percent = mem.percent
                
                print("[0] 🖥️ 운영 서버 시스템 자원 현황")
                print(f" ⚙️  CPU 사용률: {cpu_usage:>5.1f}%  |  🟢 남은 CPU 공간: {cpu_remain:>5.1f}%")
                print(f" 🧠 RAM 사용률: {mem_usage_percent:>5.1f}%  |  🟢 남은 메모리:   {mem_remain_gb:>5.1f} GB (총 {mem_total_gb:.1f} GB)")
                print("-----------------------------------------------------")
            else:
                print("[0] 🖥️ 시스템 자원 현황 (psutil 패키지 미설치로 비활성화)")
                print("-----------------------------------------------------")
            # ----------------------------------------

            print("[1] 🏢 작업 진행 상황 (Redis Queue)")
            
            # Redis 데이터 가져오기
            total_target = r.get('total_target') or "0"
            job_queue = r.llen('job_queue')
            working_buses = r.scard('working_buses')
            active_buses = r.scard('active_buses')
            
            print(f" 🎯 총 목표 작업량 (total_target): {total_target}")
            print(f" 📦 남은 대기열 (job_queue): {job_queue}")
            print(f" 🔒 중복 방지 예약 명단 (working_buses): {working_buses}")
            print(f" 🔥 실제 연산 중인 버스 (active_buses): {active_buses}")
            
            print("-----------------------------------------------------")
            print("[2] 🌐 글로벌 집계 상황판 (전체 작업자 합산)")
            
            # Redis Hash 데이터 가져와서 정렬해 출력
            batch_stats = r.hgetall('current_batch_stats')
            if batch_stats:
                for key, value in batch_stats.items():
                    print(f" {key:<10} : {value}")
            else:
                print(" 집계 데이터가 없습니다.")
                
            print("=====================================================")
            print("종료하려면 Ctrl+C 를 누르세요.")
            
            # 1초 대기 후 화면 갱신
            time.sleep(1)
            
        except KeyboardInterrupt:
            # Ctrl+C 입력 시 깔끔하게 종료
            print("\n모니터링을 종료합니다.")
            break
        except Exception as e:
            print(f"\n데이터를 불러오는 중 에러 발생: {e}")
            time.sleep(2)

if __name__ == "__main__":
    run_dashboard()