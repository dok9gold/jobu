# Phase 4: WorkerPool 구현

## 개요
Dispatcher가 생성한 PENDING 상태의 job_executions를 폴링하여 실제로 실행하는 워커풀 모듈

## 사용 테이블

### job_executions (읽기/쓰기)
```sql
id, job_id, scheduled_time, status, started_at, finished_at,
retry_count, error_message, result, created_at
```
- status: PENDING -> RUNNING -> SUCCESS/FAILED/TIMEOUT

### cron_jobs (읽기 - JOIN)
```sql
handler_name, handler_params, max_retry, timeout_seconds
```

## 사용 쿼리 (worker/sql/worker.sql)
- `get_pending_executions`: PENDING 잡 목록 조회 (LIMIT 적용)
- `claim_execution`: PENDING -> RUNNING 원자적 변경
- `complete_execution`: status를 SUCCESS로 변경, result 저장
- `fail_execution`: status를 FAILED로 변경, error_message 저장, retry_count 증가
- `timeout_execution`: status를 TIMEOUT으로 변경
- `reset_to_pending`: 재시도시 PENDING으로 복귀

## 파일 구조
```
worker/
  main.py              # WorkerPool 클래스 + 엔트리포인트
  executor.py          # 개별 잡 실행 로직
  handler/
    base.py            # BaseHandler + @handler 데코레이터 + get_handler()
    sample.py          # 테스트용 샘플 핸들러
  sql/
    worker.sql         # 워커 전용 쿼리 (잡 실행/상태 관리)
config/
  worker.yaml          # 워커 설정
test/
  worker_test.py       # 워커풀 테스트
```

## 구현 항목

### 1. config/worker.yaml
```yaml
worker:
  pool_size: 5                # 동시 실행 워커 수
  poll_interval_seconds: 5    # PENDING 잡 폴링 주기
  claim_batch_size: 10        # 한번에 가져올 잡 수
  shutdown_timeout_seconds: 30  # graceful shutdown 대기 시간
```

### 2. worker/handler/base.py - BaseHandler + @handler 데코레이터
```python
from abc import ABC, abstractmethod
from typing import Any

# 핸들러 레지스트리 (모듈 레벨)
_registry: dict[str, type["BaseHandler"]] = {}

def handler(name: str):
    """핸들러 등록 데코레이터"""
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator

def get_handler(name: str) -> "BaseHandler":
    """핸들러 인스턴스 반환"""
    if name not in _registry:
        raise HandlerNotFoundError(name)
    return _registry[name]()

class BaseHandler(ABC):
    @abstractmethod
    async def execute(self, params: dict) -> Any:
        """잡 실행 로직. 결과 반환 또는 예외 발생"""
        pass
```

### 3. 핸들러 사용 예시
```python
# worker/handler/sample.py
from worker.handler.base import BaseHandler, handler

@handler("sample")
class SampleHandler(BaseHandler):
    async def execute(self, params: dict):
        # 배치 로직 구현
        return {"status": "done"}
```
- 데코레이터만 붙이면 자동 등록
- registry.py 파일 별도로 필요 없음

### 4. worker/executor.py - Executor
- 단일 잡 실행 담당
- `execute(job_info) -> None`
  1. start_execution 호출 (RUNNING)
  2. 핸들러 조회 및 인스턴스 생성
  3. asyncio.wait_for로 타임아웃 적용하여 실행
  4. 성공: complete_execution 호출
  5. 실패: fail_execution 호출, retry 판단
  6. 타임아웃: timeout_execution 호출, retry 판단
- retry 조건: job_executions.retry_count < cron_jobs.max_retry이면 PENDING으로 복귀
  - 예: max_retry=3이면 최초 1회 + 재시도 3회 = 총 4회 시도
  - 실패/타임아웃마다 retry_count 증가 (0 -> 1 -> 2 -> 3)
  - retry_count >= max_retry면 FAILED/TIMEOUT 상태 유지 (더 이상 재시도 안함)

### 5. worker/main.py - WorkerPool
```python
class WorkerPool:
    def __init__(self, config):
        self.pool_size = config['pool_size']
        self.poll_interval = config['poll_interval_seconds']
        # ...

    async def start(self):
        """워커풀 시작 - 폴링 루프"""
        pass

    async def stop(self):
        """graceful shutdown"""
        pass

    async def _poll_and_assign(self):
        """PENDING 잡 조회 후 워커에 할당"""
        pass
```

### 6. worker/handler/sample.py - SampleHandler
- 테스트용 샘플 핸들러
- params로 sleep_seconds, should_fail 등 받아서 동작 제어

### 7. test/worker_test.py
- WorkerPool 단위 테스트
- Executor 테스트 (성공/실패/타임아웃)
- @handler 데코레이터 + get_handler() 테스트
- 통합 테스트 (Dispatcher -> WorkerPool)

## 상태 전이
```
PENDING --[워커 선점]--> RUNNING --[성공]--> SUCCESS
                           |
                           +--[실패]--> FAILED --[retry<max]--> PENDING
                           |
                           +--[타임아웃]--> TIMEOUT --[retry<max]--> PENDING
```

## 주요 고려사항

### 잡 선점 (Claim)
- 여러 워커 인스턴스가 동시에 같은 잡을 가져가지 않도록
- 방법 1: SELECT FOR UPDATE (PostgreSQL)
- 방법 2: UPDATE ... WHERE status='PENDING' RETURNING (atomic)
- SQLite에서는 단일 프로세스 가정, 또는 UPDATE 후 affected rows 확인

### 타임아웃 처리
```python
try:
    result = await asyncio.wait_for(
        handler.execute(params),
        timeout=timeout_seconds
    )
except asyncio.TimeoutError:
    await timeout_execution(execution_id)
```

### Graceful Shutdown
- SIGINT/SIGTERM 수신시
- 새 잡 폴링 중단
- 실행중인 잡 완료 대기 (shutdown_timeout까지)
- 대기 초과시 강제 종료

### 에러 격리
- 한 핸들러의 에러가 다른 워커에 영향 없음
- 각 잡은 독립적인 try-except로 감싸서 실행

## 구현 순서
1. config/worker.yaml 작성
2. worker/sql/worker.sql 작성
3. worker/handler/base.py (BaseHandler + @handler 데코레이터)
4. worker/executor.py (Executor)
5. worker/main.py (WorkerPool)
6. worker/handler/sample.py (SampleHandler)
7. test/worker_test.py 작성 및 테스트
8. README.md 업데이트 (Worker 실행 방법 추가)
