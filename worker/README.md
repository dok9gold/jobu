# Worker 모듈

PENDING 상태의 Job을 폴링하여 실행하는 워커풀 모듈입니다.

## 동작 원리

```
[job_executions (PENDING)] --폴링--> [WorkerPool] --실행--> [Handler]
```

1. 설정된 주기(poll_interval)로 PENDING Job 조회
2. Job claim (PENDING -> RUNNING)
3. handler_name으로 핸들러 조회
4. 핸들러 실행 (타임아웃 적용)
5. 결과에 따라 SUCCESS/FAILED/TIMEOUT 처리
6. 실패 시 retry_count < max_retry면 PENDING으로 복귀

## 구조

```
worker/
  main.py          # WorkerPool, 메인 루프
  executor.py      # Job 실행기
  base.py          # BaseHandler, @handler 데코레이터
  exception.py     # 예외 클래스
  model/
    executor.py    # JobInfo
  sql/
    worker.sql     # SQL 쿼리
  job/             # 비즈니스 핸들러 (하위 폴더 재귀 탐색)
```

## 설정

`config/worker.yaml`

```yaml
worker:
  database: default               # job 관리용 DB (database.yaml에 정의된 이름)
  databases:                      # 핸들러에서 사용할 추가 DB들
    - business
    - analytics
  pool_size: 5                    # 동시 실행 워커 수
  poll_interval_seconds: 5        # PENDING 잡 폴링 주기
  claim_batch_size: 10            # 한번에 가져올 잡 수
  shutdown_timeout_seconds: 30    # graceful shutdown 대기 시간
```

- `database`: Job 관리(claim, 상태 업데이트)에 사용하는 DB
- `databases`: 핸들러에서 비즈니스 로직에 사용할 추가 DB 목록

## 실행

```bash
python -m worker.main
```

## 사용법

### 핸들러 작성

`worker/job/` 하위에 파일 생성 후 `@handler` 데코레이터 사용:

```python
# worker/job/email.py
from worker.base import BaseHandler, handler

@handler("email")
class EmailHandler(BaseHandler):
    async def execute(self, params: dict):
        # params: cron_jobs.handler_params (JSON)
        recipient = params.get("to")
        # 비즈니스 로직
        return {"sent": True}  # job_executions.result에 저장
```

### 그룹별 관리

```
worker/job/
  notification/
    __init__.py
    email.py       # @handler("email")
    slack.py       # @handler("slack")
    model/         # notification 전용 모델
    sql/           # notification 전용 SQL
```

### 핸들러에서 다중 DB 사용

`config/worker.yaml`에 `databases`로 추가 DB를 설정하면 핸들러에서 사용 가능:

```python
# worker/job/sync.py
from worker.base import BaseHandler, handler
from database.registry import DatabaseRegistry
from database import transactional, get_connection

@handler("sync")
class SyncHandler(BaseHandler):
    async def execute(self, params: dict):
        db1 = DatabaseRegistry.get('default')
        db2 = DatabaseRegistry.get('business')

        @transactional(db1, db2)
        async def sync_data():
            ctx1 = get_connection('default')
            ctx2 = get_connection('business')
            # 다중 DB 트랜잭션
            await ctx1.execute("UPDATE ...")
            await ctx2.execute("INSERT ...")

        await sync_data()
        return {"synced": True}
```

### 재시도 로직

1. 핸들러 실행 실패 또는 타임아웃 발생
2. retry_count 증가
3. retry_count < max_retry면 PENDING으로 복귀
4. retry_count >= max_retry면 FAILED/TIMEOUT 유지

## 예외

### Worker 예외

| 예외 | 설명 |
|------|------|
| HandlerNotFoundError | 핸들러를 찾을 수 없음 |

### DB 예외 처리 (Executor)

| 예외 | 로그 레벨 | 설명 |
|------|----------|------|
| ConnectionPoolExhaustedError | WARNING | 커넥션풀 고갈 (일시적 문제) |
| TransactionError | ERROR | 트랜잭션 에러 |
| QueryExecutionError | ERROR | 쿼리 실행 에러 |

