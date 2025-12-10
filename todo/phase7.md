# Phase 7: 운영 품질 강화 + 다중 DB 실전 테스트

## 개요
- 프로덕션 배포 전 필수 기능 추가 (Graceful Shutdown, 헬스체크, JSON 로깅)
- 3개 DB(SQLite, PostgreSQL, MySQL) 동시 연동 샘플 워커 구현
- 기존 6개 샘플 워커(group1/group2)를 다중 DB 예제로 활용

---

## 1. 운영 필수 기능

### 1.1 Graceful Shutdown

**현재 상태:**
- Worker: 이미 구현됨 (worker/main.py:260-268)
- Dispatcher: 미구현 (추가 필요)

**Dispatcher에 추가할 내용:**
```python
# dispatcher/main.py
import signal

def signal_handler():
    logger.info("Received shutdown signal")
    asyncio.create_task(dispatcher.stop())

for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, signal_handler)
```

**타임아웃 추가 (선택):**
- 무한 대기 방지를 위해 shutdown timeout 설정 권장

### 1.2 헬스체크 엔드포인트

**현재 상태:**
- `/health`: 이미 구현됨 (admin/api/router/api.py:179-193)
- `/ready`: 미구현 (추가 필요)

**추가할 내용:**
```python
# admin/api/router/api.py
@router.get("/ready")
async def ready():
    # DB 연결 확인 (실제 쿼리 실행)
    try:
        db = DatabaseRegistry.get('default')
        async with db.transaction(readonly=True) as ctx:
            await ctx.fetch_val("SELECT 1")
        return {"status": "ready", "database": "ok"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not ready", "error": str(e)})
```

### 1.3 JSON 구조화 로깅

**현재 상태:** 미구현 (common/logging.py 생성 필요)

**의존성 추가 필요:** `python-json-logger>=2.0.0`

```python
# common/logging.py
from pythonjsonlogger import jsonlogger

def setup_logging(level="INFO", json_format=True):
    handler = logging.StreamHandler()
    if json_format:
        formatter = jsonlogger.JsonFormatter(
            '%(timestamp)s %(level)s %(name)s %(message)s',
            rename_fields={"levelname": "level", "asctime": "timestamp"}
        )
        handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[handler])
```

출력 예시:
```json
{"timestamp": "2025-01-10T10:00:00Z", "level": "INFO", "name": "worker", "job_id": 123, "message": "Job started"}
```

---

## 2. 다중 DB 샘플 워커 (기존 파일 활용)

**현재 상태:**
- group1/sample1~3.py: 스켈레톤만 존재 (로직 구현 필요)
- group2/sample4~6.py: 파일 없음 (생성 필요)
- Docker Compose: 이미 구현됨 (docker/docker-compose.yaml)

### 2.1 샘플 테이블

각 DB에 동일한 테이블 생성 (init.sql에 추가):

```sql
CREATE TABLE sample_data (
    id SERIAL PRIMARY KEY,  -- SQLite: INTEGER PRIMARY KEY AUTOINCREMENT
    name VARCHAR(255) NOT NULL,
    value TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    writer_handler VARCHAR(50)  -- 어느 핸들러가 썼는지
);
```

### 2.2 파일 구조

```
worker/job/
  group1/                    # SQLite + PostgreSQL 예제
    sample1.py               # SQLite 단일 DB CRUD (스켈레톤 존재)
    sample2.py               # PostgreSQL 단일 DB CRUD (스켈레톤 존재)
    sample3.py               # SQLite -> PostgreSQL 동기화 (스켈레톤 존재)
    sql/
      sqlite.sql             # SQLite용 쿼리 (?, ?)
      postgres.sql           # PostgreSQL용 쿼리 ($1, $2)
    model/
      sample1.py, sample2.py, sample3.py

  group2/                    # MySQL + 3개 DB 복합 예제
    sample4.py               # MySQL 단일 DB CRUD (생성 필요)
    sample5.py               # PostgreSQL -> MySQL 동기화 (생성 필요)
    sample6.py               # 3개 DB 통합 리포트 (생성 필요)
    sql/
      mysql.sql              # MySQL용 쿼리 (%s, %s)
      postgres.sql           # PostgreSQL용 쿼리
    model/
      sample4.py, sample5.py, sample6.py
```

### 2.3 SQL 쿼리 파일 (aiosql)

#### group1/sql/sqlite.sql
```sql
-- name: insert_sample_data<!
INSERT INTO sample_data (name, value, writer_handler) VALUES (?, ?, ?);

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;

-- name: get_all_sample_data
SELECT * FROM sample_data;

-- name: get_last_insert_id$
SELECT last_insert_rowid();

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: count_by_handler
SELECT writer_handler, COUNT(*) as cnt FROM sample_data GROUP BY writer_handler;
```

#### group1/sql/postgres.sql
```sql
-- name: insert_sample_data_returning^
INSERT INTO sample_data (name, value, writer_handler)
VALUES ($1, $2, $3) RETURNING id;

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;

-- name: get_all_sample_data
SELECT * FROM sample_data;

-- name: upsert_sample_data!
INSERT INTO sample_data (id, name, value, writer_handler)
VALUES ($1, $2, $3, $4)
ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    value = EXCLUDED.value;

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: count_by_handler
SELECT writer_handler, COUNT(*) as cnt FROM sample_data GROUP BY writer_handler;
```

#### group2/sql/mysql.sql
```sql
-- name: insert_sample_data!
INSERT INTO sample_data (name, value, writer_handler) VALUES (%s, %s, %s);

-- name: get_sample_data
SELECT id, name, value FROM sample_data LIMIT 10;

-- name: get_last_insert_id$
SELECT LAST_INSERT_ID();

-- name: upsert_sample_data!
INSERT INTO sample_data (id, name, value, writer_handler)
VALUES (%s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    value = VALUES(value);

-- name: count_sample_data$
SELECT COUNT(*) FROM sample_data;

-- name: count_by_handler
SELECT writer_handler, COUNT(*) as cnt FROM sample_data GROUP BY writer_handler;
```

### 2.4 Group1: SQLite + PostgreSQL

#### sample1.py - SQLite(sqlite_2) 단일 DB CRUD
```python
# worker/job/group1/sample1.py
import aiosql
from pathlib import Path
from worker.base import BaseHandler, handler
from database import transactional, transactional_readonly, get_connection, DatabaseRegistry

queries = aiosql.from_path(Path(__file__).parent / "sql" / "sqlite.sql", "aiosqlite")

@handler("sample1")
class Sample1Handler(BaseHandler):
    """SQLite(sqlite_2) 단일 DB CRUD 예제 - Docker 없이 테스트 가능"""

    async def execute(self, params: dict):
        db = DatabaseRegistry.get('sqlite_2')  # 두 번째 SQLite DB

        action = params.get('action', 'read')

        if action == 'write':
            @transactional(db)
            async def write_data():
                ctx = get_connection('sqlite_2')
                await queries.insert_sample_data(
                    ctx.conn, params.get('name', 'test'), params.get('value', ''), 'sample1'
                )
                return await queries.get_last_insert_id(ctx.conn)

            data_id = await write_data()
            return {"action": "write", "id": data_id}

        else:  # read
            @transactional_readonly(db)
            async def read_data():
                ctx = get_connection('sqlite_2')
                return await queries.get_sample_data(ctx.conn)

            rows = await read_data()
            return {"action": "read", "count": len(rows), "data": rows}
```

#### sample2.py - PostgreSQL 단일 DB CRUD
```python
# worker/job/group1/sample2.py
import aiosql
from pathlib import Path
from worker.base import BaseHandler, handler
from database import transactional, transactional_readonly, get_connection, DatabaseRegistry

queries = aiosql.from_path(Path(__file__).parent / "sql" / "postgres.sql", "asyncpg")

@handler("sample2")
class Sample2Handler(BaseHandler):
    """PostgreSQL 단일 DB CRUD 예제"""

    async def execute(self, params: dict):
        db = DatabaseRegistry.get('postgres_1')

        action = params.get('action', 'read')

        if action == 'write':
            @transactional(db)
            async def write_data():
                ctx = get_connection('postgres_1')
                row = await queries.insert_sample_data_returning(
                    ctx.conn, params.get('name', 'test'), params.get('value', ''), 'sample2'
                )
                return row['id']

            data_id = await write_data()
            return {"action": "write", "id": data_id, "db": "postgres"}

        else:
            @transactional_readonly(db)
            async def read_data():
                ctx = get_connection('postgres_1')
                return await queries.get_sample_data(ctx.conn)

            rows = await read_data()
            return {"action": "read", "count": len(rows), "db": "postgres"}
```

#### sample3.py - SQLite -> PostgreSQL 동기화
```python
# worker/job/group1/sample3.py
import aiosql
from pathlib import Path
from worker.base import BaseHandler, handler
from database import transactional, get_connection, DatabaseRegistry

sqlite_queries = aiosql.from_path(Path(__file__).parent / "sql" / "sqlite.sql", "aiosqlite")
pg_queries = aiosql.from_path(Path(__file__).parent / "sql" / "postgres.sql", "asyncpg")

@handler("sample3")
class Sample3Handler(BaseHandler):
    """SQLite -> PostgreSQL 2개 DB 동기화 예제"""

    async def execute(self, params: dict):
        sqlite_db = DatabaseRegistry.get('default')
        pg_db = DatabaseRegistry.get('postgres_1')

        @transactional(sqlite_db, pg_db)
        async def sync_sqlite_to_pg():
            sqlite_ctx = get_connection('default')
            pg_ctx = get_connection('postgres_1')

            rows = await sqlite_queries.get_all_sample_data(sqlite_ctx.conn)

            synced = 0
            for row in rows:
                await pg_queries.upsert_sample_data(
                    pg_ctx.conn, row['id'], row['name'], row['value'], 'sample3'
                )
                synced += 1

            return synced

        count = await sync_sqlite_to_pg()
        return {"synced": count, "from": "sqlite", "to": "postgres"}
```

### 2.5 Group2: MySQL + 3개 DB 복합

> **참고**: asyncmy 드라이버 사용. aiosql에서 `"asyncmy"` 어댑터로 SQL 파일 로드 가능.

#### sample4.py - MySQL 단일 DB CRUD
```python
# worker/job/group2/sample4.py
from worker.base import BaseHandler, handler
from database import transactional, transactional_readonly, get_connection, DatabaseRegistry

@handler("sample4")
class Sample4Handler(BaseHandler):
    """MySQL 단일 DB CRUD 예제"""

    async def execute(self, params: dict):
        db = DatabaseRegistry.get('mysql_1')
        action = params.get('action', 'read')

        if action == 'write':
            @transactional(db)
            async def write_data():
                ctx = get_connection('mysql_1')
                await ctx.execute(
                    "INSERT INTO sample_data (name, value, writer_handler) VALUES (%s, %s, %s)",
                    (params.get('name', 'test'), params.get('value', ''), 'sample4')
                )
                return await ctx.fetch_val("SELECT LAST_INSERT_ID()")

            data_id = await write_data()
            return {"action": "write", "id": data_id, "db": "mysql"}

        else:
            @transactional_readonly(db)
            async def read_data():
                ctx = get_connection('mysql_1')
                return await ctx.fetch_all("SELECT id, name, value FROM sample_data LIMIT 10")

            rows = await read_data()
            return {"action": "read", "count": len(rows), "db": "mysql"}
```

#### sample5.py - PostgreSQL -> MySQL 동기화
```python
# worker/job/group2/sample5.py
import aiosql
from pathlib import Path
from worker.base import BaseHandler, handler
from database import transactional, get_connection, DatabaseRegistry

pg_queries = aiosql.from_path(
    Path(__file__).parent.parent / "group1" / "sql" / "postgres.sql", "asyncpg"
)

@handler("sample5")
class Sample5Handler(BaseHandler):
    """PostgreSQL -> MySQL 2개 DB 동기화 예제"""

    async def execute(self, params: dict):
        pg_db = DatabaseRegistry.get('postgres_1')
        mysql_db = DatabaseRegistry.get('mysql_1')

        @transactional(pg_db, mysql_db)
        async def sync_pg_to_mysql():
            pg_ctx = get_connection('postgres_1')
            mysql_ctx = get_connection('mysql_1')

            rows = await pg_queries.get_all_sample_data(pg_ctx.connection)

            synced = 0
            for row in rows:
                await mysql_ctx.execute(
                    """INSERT INTO sample_data (id, name, value, writer_handler)
                       VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE
                           name = VALUES(name), value = VALUES(value), writer_handler = VALUES(writer_handler)""",
                    (row['id'], row['name'], row['value'], 'sample5_sync')
                )
                synced += 1

            return synced

        count = await sync_pg_to_mysql()
        return {"synced": count, "from": "postgres", "to": "mysql"}
```

#### sample6.py - 3개 DB 통합 리포트
```python
# worker/job/group2/sample6.py
import aiosql
from pathlib import Path
from worker.base import BaseHandler, handler
from database import transactional_readonly, get_connection, DatabaseRegistry

sqlite_queries = aiosql.from_path(
    Path(__file__).parent.parent / "group1" / "sql" / "sqlite.sql", "aiosqlite"
)
pg_queries = aiosql.from_path(
    Path(__file__).parent.parent / "group1" / "sql" / "postgres.sql", "asyncpg"
)

@handler("sample6")
class Sample6Handler(BaseHandler):
    """3개 DB 통합 리포트 예제 (readonly)"""

    async def execute(self, params: dict):
        sqlite_db = DatabaseRegistry.get('sqlite_2')
        pg_db = DatabaseRegistry.get('postgres_1')
        mysql_db = DatabaseRegistry.get('mysql_1')

        @transactional_readonly(sqlite_db, pg_db, mysql_db)
        async def gather_report():
            sqlite_ctx = get_connection('sqlite_2')
            pg_ctx = get_connection('postgres_1')
            mysql_ctx = get_connection('mysql_1')

            sqlite_count = await sqlite_queries.count_sample_data(sqlite_ctx.connection)
            pg_count = await pg_queries.count_sample_data(pg_ctx.connection)
            mysql_count = await mysql_ctx.fetch_val("SELECT COUNT(*) FROM sample_data")

            return {
                "counts": {
                    "sqlite": sqlite_count,
                    "postgres": pg_count,
                    "mysql": mysql_count,
                    "total": sqlite_count + pg_count + mysql_count
                }
            }

        return await gather_report()
```

---

## 3. 테스트 시나리오

### 3.1 통합 테스트 추가

```python
# test/database/test_multi_db_integration.py

class TestMultiDbIntegration:
    """3개 DB 동시 연동 테스트"""

    @pytest.mark.asyncio
    async def test_three_db_transaction_commit(self):
        """SQLite + PostgreSQL + MySQL 동시 커밋"""
        pass

    @pytest.mark.asyncio
    async def test_three_db_transaction_rollback(self):
        """하나라도 실패 시 모두 롤백"""
        pass

    @pytest.mark.asyncio
    async def test_sample_handlers(self):
        """샘플 핸들러 6개 실행 테스트"""
        pass
```

### 3.2 실행 가이드

```bash
# 1. Docker 환경 실행
cd docker && docker-compose up -d

# 2. 테스트 실행
python -m pytest test/database/test_multi_db_integration.py -v

# 3. 샘플 워커 등록 (Admin API)
# sample1: SQLite CRUD
curl -X POST http://localhost:8080/api/crons \
  -H "Content-Type: application/json" \
  -d '{"name": "sqlite_crud", "cron_expression": "* * * * *", "handler_name": "sample1", "handler_params": {"action": "read"}}'

# sample3: SQLite -> PostgreSQL 동기화
curl -X POST http://localhost:8080/api/crons \
  -H "Content-Type: application/json" \
  -d '{"name": "sync_sqlite_pg", "cron_expression": "* * * * *", "handler_name": "sample3"}'

# sample6: 3개 DB 통합 리포트
curl -X POST http://localhost:8080/api/crons \
  -H "Content-Type: application/json" \
  -d '{"name": "multi_db_report", "cron_expression": "* * * * *", "handler_name": "sample6"}'
```

---

## 4. 구현 순서

1. Graceful Shutdown 구현 (dispatcher만 - worker는 이미 구현됨)
2. 헬스체크 `/ready` 엔드포인트 추가 (admin - `/health`는 이미 구현됨)
3. JSON 로깅 설정 (common/logging.py 생성)
4. 샘플 워커 구현 (sample1~3 로직 추가, sample4~6 파일 생성)
5. config/database.yaml에 postgres_1, mysql_1 설정 활성화
6. 통합 테스트 작성
7. 문서 업데이트

---

## 5. 의존성 추가

```
# requirements.txt에 추가
python-json-logger>=2.0.0
```

---

## 6. 설정 파일 수정

**config/database.yaml** (현재 주석 처리됨, 활성화 필요):
```yaml
databases:
  default:
    type: sqlite
    path: "data/jobu.db"

  sqlite_2:
    type: sqlite
    path: "data/sample.db"  # 샘플용 두 번째 SQLite (Docker 없이 테스트 가능)

  postgres_1:
    type: postgres
    host: localhost
    port: 5432
    user: jobu
    password: jobu
    database: jobu
    pool_size: 5

  mysql_1:
    type: mysql
    host: localhost
    port: 3306
    user: jobu
    password: jobu
    database: jobu
    pool_size: 5
```