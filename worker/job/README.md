# 핸들러 개발 가이드

학습 목적별로 정리된 예제 핸들러들입니다.

## 디렉토리 구조

```
worker/job/
  basic/                # 단일 DB CRUD 예제
    sql/                # basic 전용 SQL 파일
  multi_db/             # 멀티 DB 트랜잭션 예제
    sql/                # multi_db 전용 SQL 파일
  patterns/             # 코드 구조 패턴
    sql/                # patterns 전용 SQL 파일
  async_patterns/       # 비동기 고급 패턴
    sql/                # async_patterns 전용 SQL 파일
```

## 핸들러 목록

| 핸들러 | 카테고리 | 설명 | 사용 DB |
|--------|----------|------|---------|
| `sqlite_crud` | basic | SQLite CRUD (Docker 불필요) | sqlite_2 |
| `postgres_crud` | basic | PostgreSQL CRUD | postgres_1 |
| `mysql_crud` | basic | MySQL CRUD | mysql_1 |
| `sync_sqlite_to_postgres` | multi_db | 2개 DB 동기화 트랜잭션 | default -> postgres_1 |
| `sync_postgres_to_mysql` | multi_db | 2개 DB 동기화 트랜잭션 | postgres_1 -> mysql_1 |
| `multi_db_report` | multi_db | 3개 DB 집계 리포트 (읽기 전용) | sqlite_2, postgres_1, mysql_1 |
| `service_layer` | patterns | Spring MVC 스타일 (Handler -> Service) | sqlite_2 |
| `do_work_pattern` | patterns | 심플한 트랜잭션 분리 | sqlite_2 |
| `concurrent_queries` | async_patterns | asyncio.gather 병렬 쿼리 | sqlite_2, postgres_1, mysql_1 |

## 학습 순서

### 1. Basic - 단일 DB CRUD

여기서 시작하세요. 핸들러 기본 구조와 단일 DB 트랜잭션을 배웁니다.

```python
from worker.base import BaseHandler, handler
from database import transactional, get_connection, get_db

@handler("my_handler")
class MyHandler(BaseHandler):
    async def execute(self, params: HandlerParams) -> HandlerResult:
        db = get_db('sqlite_2')

        @transactional(db)
        async def work():
            ctx = get_connection('sqlite_2')
            # ctx.connection으로 DB 작업 수행
            return result

        return await work()
```

**파일:**
- [sqlite_crud.py](basic/sqlite_crud.py) - 이것부터 시작 (Docker 불필요)
- [postgres_crud.py](basic/postgres_crud.py)
- [mysql_crud.py](basic/mysql_crud.py)

### 2. Multi-DB - 멀티 DB 트랜잭션

여러 데이터베이스에 걸친 트랜잭션 관리 방법을 배웁니다.

```python
@transactional(db1, db2)  # 둘 다 커밋 또는 둘 다 롤백
async def sync_data():
    ctx1 = get_connection('postgres_1')
    ctx2 = get_connection('mysql_1')
    # DB 간 데이터 동기화
```

**파일:**
- [sync_sqlite_to_postgres.py](multi_db/sync_sqlite_to_postgres.py)
- [sync_postgres_to_mysql.py](multi_db/sync_postgres_to_mysql.py)
- [multi_db_report.py](multi_db/multi_db_report.py) - 읽기 전용 멀티 DB

### 3. Patterns - 코드 구조 패턴

유지보수하기 좋은 핸들러 구조화 방법을 배웁니다.

**서비스 레이어 패턴 (Spring MVC 스타일):**
```
Handler (Controller) -> Service -> Database
- Handler: 요청/응답 처리
- Service: 비즈니스 로직 + 트랜잭션 경계
```

**do_work 패턴 (심플):**
```
execute() -> do_work() with @transactional
- 가장 단순한 트랜잭션 분리
- 모든 로직을 하나의 함수에
```

**파일:**
- [service_layer.py](patterns/service_layer.py) + [service/](patterns/service/)
- [do_work_pattern.py](patterns/do_work_pattern.py)

### 4. Async Patterns - 비동기 고급 패턴

성능 최적화를 위한 asyncio 패턴을 배웁니다.

```python
# asyncio.gather로 동시 쿼리
results = await asyncio.gather(
    fetch_from_db1(),
    fetch_from_db2(),
    fetch_from_db3(),
)
```

**파일:**
- [concurrent_queries.py](async_patterns/concurrent_queries.py)

## 새 핸들러 만들기

1. 적절한 디렉토리에 새 파일 생성
2. 같은 디렉토리의 `sql/` 폴더에 SQL 파일 생성
3. `@handler("이름")` 데코레이터로 핸들러 클래스 정의
4. `execute(self, params: HandlerParams) -> HandlerResult` 구현
5. DB 작업에 `@transactional` 또는 `@transactional_readonly` 사용

```python
from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, get_connection, get_db

@handler("my_new_handler")
class MyNewHandler(BaseHandler):
    async def execute(self, params: HandlerParams) -> HandlerResult:
        # 비즈니스 로직
        return HandlerResult(action='done', data={})
```

## SQL 파일 관리

각 패키지별로 `sql/` 디렉토리에 핸들러별 SQL 파일을 둡니다.

**단일 DB 핸들러:**
```
basic/sql/sqlite_crud.sql      # sqlite_crud 핸들러용
basic/sql/postgres_crud.sql    # postgres_crud 핸들러용
```

**멀티 DB 핸들러 (DB별로 파일 분리):**
```
multi_db/sql/sync_sqlite_to_postgres_sqlite.sql    # SQLite 쿼리
multi_db/sql/sync_sqlite_to_postgres_postgres.sql  # PostgreSQL 쿼리
```

aiosql로 SQL 쿼리 로드:
```python
import aiosql
from pathlib import Path

# 단일 DB
queries = aiosql.from_path(
    Path(__file__).parent / "sql" / "sqlite_crud.sql",
    "aiosqlite"
)

# 멀티 DB
sqlite_queries = aiosql.from_path(
    Path(__file__).parent / "sql" / "sync_sqlite_to_postgres_sqlite.sql",
    "aiosqlite"
)
pg_queries = aiosql.from_path(
    Path(__file__).parent / "sql" / "sync_sqlite_to_postgres_postgres.sql",
    "asyncpg"
)
```

## DB 설정

| DB 이름 | 타입 | 용도 | Docker |
|---------|------|------|--------|
| default | SQLite | 시스템 (cron_jobs, job_executions) | 불필요 |
| sqlite_2 | SQLite | 샘플 데이터 | 불필요 |
| postgres_1 | PostgreSQL | 샘플 데이터 | 필요 |
| mysql_1 | MySQL | 샘플 데이터 | 필요 |

## 테스트용 핸들러

테스트 목적의 `sample` 핸들러도 있습니다:
- 위치: [sample.py](sample.py)
- 용도: 테스트용 (sleep, 실패 시뮬레이션)
- params:
  - `sleep_seconds`: 대기 시간 (초)
  - `should_fail`: true면 에러 발생
  - `message`: 결과 메시지
