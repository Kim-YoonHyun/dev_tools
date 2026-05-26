import redis
import os

def flush_redis_queues():
    # 환경변수에서 호스트를 찾고, 없으면 기본값(127.0.0.1) 사용
    redis_host = os.environ.get('REDIS_HOST', '127.0.0.1')
    
    try:
        r = redis.Redis(host=redis_host, port=6379, db=0, decode_responses=True)
        r.ping() # 연결 확인
        
        # 삭제할 키 목록 (active_buses 등 추가 가능)
        keys_to_delete = ['job_queue', 'working_buses', 'active_buses', 'current_batch_stats']
        
        # delete 명령어는 여러 개의 키를 한 번에 지울 수 있습니다.
        deleted_count = r.delete(*keys_to_delete)
        print(f"✅ Redis 초기화 완료: {deleted_count}개의 키가 삭제되었습니다.")
        
    except Exception as e:
        print(f"❌ Redis 연결 또는 삭제 실패: {e}")

if __name__ == "__main__":
    flush_redis_queues()