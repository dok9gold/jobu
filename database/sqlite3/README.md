# SQLite3 비동기 커넥션풀

SQLite3 데이터베이스를 위한 비동기 커넥션풀 모듈입니다. aiosqlite 기반으로 동작하며, 트랜잭션 관리 기능을 제공합니다.

## 목차

1. [주요 기능](#주요-기능)
2. [구조](#구조)
3. [설정](#설정)
4. [초기화](#초기화)
5. [사용법](#사용법)
6. [API 레퍼런스](#api-레퍼런스)
7. [예외](#예외)
8. [테스트](#테스트)
9. [설정 옵션 상세](#설정-옵션-상세)

## 주요 기능

| 기능 | 설명 |
|------|------|
| 비동기 커넥션풀 | 설정된 크기만큼 커넥션을 미리 생성하여 재사용 |
| 트랜잭션 데코레이터 | `@transactional`, `@transactional_readonly` |
| 수동 트랜잭션 | `begin()`, `commit()`, `rollback()` 직접 제어 |
| 읽기 전용 모드 | 쓰기 쿼리 실행 시 예외 발생 |
| 커넥션 타임아웃 | 풀 고갈 시 대기 후 타임아웃 처리 |
| 유휴 커넥션 정리 | 일정 시간 미사용 커넥션 자동 재생성 |
| SQL 로깅 | 실행되는 모든 쿼리 로깅 |

## 구조

```
database/sqlite3/
  __init__.py       # 공개 API
  connection.py     # SQLiteDatabase, AsyncConnectionPool
  sql/
    init.sql        # 초기 테이블 생성
```

## 설정

`config/database.yaml` 파일에서 설정합니다.

```yaml
databases:
  default:
    type: sqlite
    path: data/jobu.db
    pool:
      pool_size: 5          # 커넥션풀 크기
      pool_timeout: 30.0    # 커넥션 획득 대기 시간 (초)
      max_idle_time: 300.0  # 유휴 커넥션 재생성 시간 (초)
    options:
      busy_timeout: 5000    # SQLite busy timeout (밀리초)
      journal_mode: "WAL"   # 저널 모드
      synchronous: "NORMAL" # 동기화 수준
      cache_size: -2000     # 캐시 크기 (음수: KB, 양수: 페이지)
      foreign_keys: true    # 외래키 제약조건 활성화

  business:                 # 추가 DB
    type: sqlite
    path: data/business.db
```

## 초기화

`DatabaseRegistry`를 통해 초기화합니다.

```python
import yaml
from database.registry import DatabaseRegistry

# 설정 로드
with open("config/database.yaml") as f:
    config = yaml.safe_load(f)

# 데이터베이스 초기화
await DatabaseRegistry.init_from_config(config)

# 특정 DB만 초기화
await DatabaseRegistry.init_from_config(config, ['default'])
```

종료 시:
```python
await DatabaseRegistry.close_all()
```

## 사용법

### 트랜잭션 데코레이터

가장 권장하는 방식입니다. 함수 실행 전 트랜잭션을 시작하고, 정상 종료 시 커밋, 예외 발생 시 롤백합니다.

```python
from database import transactional, get_connection

@transactional
async def create_job(name: str, cron_expr: str) -> int:
    ctx = get_connection()
    cursor = await ctx.execute(
        "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
        (name, cron_expr, "default_handler")
    )
    return cursor.lastrowid


@transactional
async def update_job(job_id: int, name: str) -> None:
    ctx = get_connection()
    await ctx.execute(
        "UPDATE cron_jobs SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (name, job_id)
    )
```

동작 방식:
1. 커넥션풀에서 커넥션 획득
2. `BEGIN IMMEDIATE` 실행 (쓰기 락 획득)
3. 함수 실행
4. 성공 시 `COMMIT`, 예외 시 `ROLLBACK`
5. 커넥션 반환

### 읽기 전용 트랜잭션

조회 전용 함수에 사용합니다. 쓰기 쿼리 실행 시 `ReadOnlyTransactionError`가 발생합니다.

```python
from database import transactional_readonly, get_connection

@transactional_readonly
async def get_job(job_id: int) -> dict | None:
    ctx = get_connection()
    row = await ctx.fetch_one(
        "SELECT * FROM cron_jobs WHERE id = ?",
        (job_id,)
    )
    return dict(row) if row else None


@transactional_readonly
async def get_all_jobs() -> list[dict]:
    ctx = get_connection()
    rows = await ctx.fetch_all("SELECT * FROM cron_jobs WHERE is_enabled = 1")
    return [dict(row) for row in rows]
```

동작 방식:
1. 커넥션풀에서 커넥션 획득
2. `BEGIN DEFERRED` 실행 (읽기 전용)
3. 함수 실행 (INSERT/UPDATE/DELETE 시도 시 예외)
4. `COMMIT`
5. 커넥션 반환

### 수동 트랜잭션

여러 작업을 세밀하게 제어해야 할 때 사용합니다.

```python
from database.registry import DatabaseRegistry

db = DatabaseRegistry.get('default')

async with db.transaction() as ctx:
    # 첫 번째 작업
    await ctx.execute(
        "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
        ("job1", "0 * * * *", "handler1")
    )

    # 조건부 커밋/롤백
    if some_condition:
        await ctx.commit()
    else:
        await ctx.rollback()
```

읽기 전용 수동 트랜잭션:
```python
async with db.transaction(readonly=True) as ctx:
    rows = await ctx.fetch_all("SELECT * FROM cron_jobs")
```

### 다중 DB 트랜잭션

```python
from database import transactional, get_connection, DatabaseRegistry

db1 = DatabaseRegistry.get('default')
db2 = DatabaseRegistry.get('business')

@transactional(db1, db2)
async def sync_data():
    ctx1 = get_connection('default')
    ctx2 = get_connection('business')

    await ctx1.execute("UPDATE ...")
    await ctx2.execute("INSERT ...")
    # 둘 다 성공하면 커밋, 하나라도 실패하면 롤백
```

## API 레퍼런스

### Database

| 메서드 | 설명 |
|--------|------|
| `Database.init(config)` | 데이터베이스 초기화 (싱글톤) |
| `get_db()` | 현재 Database 인스턴스 반환 |
| `db.transaction(readonly=False)` | 트랜잭션 컨텍스트 매니저 반환 |
| `db.close()` | 데이터베이스 연결 종료 |
| `db.pool` | 커넥션풀 인스턴스 반환 |

### TransactionContext

| 메서드 | 설명 |
|--------|------|
| `ctx.execute(sql, params)` | SQL 실행, Cursor 반환 |
| `ctx.executemany(sql, params_list)` | 다중 SQL 실행 |
| `ctx.fetch_one(sql, params)` | 단일 행 조회 |
| `ctx.fetch_all(sql, params)` | 모든 행 조회 |
| `ctx.begin()` | 트랜잭션 시작 (수동 모드) |
| `ctx.commit()` | 트랜잭션 커밋 |
| `ctx.rollback()` | 트랜잭션 롤백 |

### AsyncConnectionPool

| 속성/메서드 | 설명 |
|-------------|------|
| `pool.size` | 전체 커넥션 수 |
| `pool.available` | 사용 가능한 커넥션 수 |
| `pool.acquire(timeout)` | 커넥션 획득 |
| `pool.release(conn)` | 커넥션 반환 |

## 예외

| 예외 | 발생 조건 |
|------|-----------|
| `ConnectionPoolExhaustedError` | 타임아웃 내 커넥션 획득 실패 |
| `TransactionError` | 트랜잭션 관련 일반 에러 |
| `ReadOnlyTransactionError` | 읽기 전용 트랜잭션에서 쓰기 시도 |
| `QueryExecutionError` | 쿼리 실행 실패 |

### 예외 처리 예시

```python
from database import (
    transactional,
    get_connection,
    ConnectionPoolExhaustedError,
    ReadOnlyTransactionError,
)

@transactional
async def risky_operation():
    ctx = get_connection()
    try:
        await ctx.execute("INSERT INTO ...")
    except Exception as e:
        # 예외 발생 시 자동 롤백됨
        raise

# 커넥션풀 고갈 처리
try:
    result = await risky_operation()
except ConnectionPoolExhaustedError:
    # 재시도 로직 또는 에러 응답
    pass
```

## 설정 옵션 상세

### 커넥션풀 설정 (pool)

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `pool_size` | 5 | 동시에 유지할 커넥션 수 |
| `pool_timeout` | 30.0 | 커넥션 획득 최대 대기 시간 (초) |
| `max_idle_time` | 300.0 | 유휴 커넥션 재생성 기준 시간 (초) |

### SQLite 옵션 (options)

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `busy_timeout` | 5000 | 락 대기 시간 (밀리초) |
| `journal_mode` | WAL | 저널 모드 (DELETE, TRUNCATE, PERSIST, MEMORY, WAL, OFF) |
| `synchronous` | NORMAL | 동기화 수준 (OFF, NORMAL, FULL, EXTRA) |
| `cache_size` | -2000 | 페이지 캐시 크기 (음수: KB 단위) |
| `foreign_keys` | true | 외래키 제약조건 활성화 |

### journal_mode 선택 가이드

| 모드 | 특징 | 권장 상황 |
|------|------|-----------|
| WAL | 읽기/쓰기 동시 가능, 높은 성능 | 일반적인 웹 애플리케이션 (권장) |
| DELETE | 트랜잭션마다 저널 삭제 | 단일 쓰기, 간단한 사용 |
| MEMORY | 저널을 메모리에 저장 | 속도 중요, 데이터 손실 허용 |

### synchronous 선택 가이드

| 모드 | 특징 | 권장 상황 |
|------|------|-----------|
| NORMAL | WAL 모드에서 안전하고 빠름 | WAL 모드 사용 시 (권장) |
| FULL | 모든 쓰기를 디스크에 동기화 | 데이터 무결성 최우선 |
| OFF | 동기화 안함 | 테스트 환경, 임시 데이터 |
