# Phase 5: Multi-DB Transaction 지원

## 상태: 완료

## 목표
다중 DB 트랜잭션을 데코레이터로 깔끔하게 처리

## 현재 구조 분석

### 기존 코드 (database/sqlite3/connection.py)
- `AsyncConnectionPool`: 싱글톤 커넥션풀
- `Database`: 싱글톤 DB 매니저
- `TransactionContext`: 트랜잭션 실행 컨텍스트
- `TransactionContextManager`: async with용 컨텍스트 매니저
- `@transactional`, `@transactional_readonly`: 데코레이터
- `get_connection()`: ContextVar로 현재 트랜잭션 컨텍스트 반환

### 문제점
1. 싱글톤 구조라 다중 DB 지원 불가
2. `@transactional` 데코레이터가 인자를 받지 않음
3. `get_connection()`이 단일 DB만 반환

---

## 구현 계획

### 1단계: BaseDatabase 추상 클래스
**파일**: `database/base.py`

```python
from abc import ABC, abstractmethod

class BaseDatabase(ABC):
    """DB 추상 클래스 - SQLite, PostgreSQL 등 공통 인터페이스"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    def transaction(self, readonly: bool = False):
        """트랜잭션 컨텍스트 매니저 반환"""
        pass

    @abstractmethod
    async def close(self):
        pass
```

### 2단계: DatabaseRegistry 구현
**파일**: `database/registry.py`

```python
from database.base import BaseDatabase
from database.sqlite3.connection import SQLiteDatabase

class DatabaseRegistry:
    """다중 DB 인스턴스 관리 (이름 기반)"""
    _databases: dict[str, BaseDatabase] = {}

    @classmethod
    def register(cls, name: str, db: BaseDatabase):
        cls._databases[name] = db

    @classmethod
    def get(cls, name: str) -> BaseDatabase:
        if name not in cls._databases:
            raise KeyError(f"Database '{name}' not registered")
        return cls._databases[name]

    @classmethod
    def get_all(cls) -> dict[str, BaseDatabase]:
        return cls._databases.copy()

    @classmethod
    async def init_from_config(cls, config: dict):
        """
        config/database.yaml에서 다중 DB 초기화

        databases:
          jobu:
            type: sqlite
            path: data/jobu.db
          business:
            type: sqlite
            path: data/business.db
        """
        for name, db_config in config.get('databases', {}).items():
            db_type = db_config.get('type', 'sqlite')

            if db_type == 'sqlite':
                db = await SQLiteDatabase.create(name, db_config)
            # elif db_type == 'postgres':
            #     db = await PostgresDatabase.create(name, db_config)
            else:
                raise ValueError(f"Unsupported database type: {db_type}")

            cls.register(name, db)

    @classmethod
    async def close_all(cls):
        for db in cls._databases.values():
            await db.close()
        cls._databases.clear()
```

### 3단계: SQLiteDatabase 클래스 (Database 대체)
**파일**: `database/sqlite3/connection.py`

변경사항:
- `Database` -> `SQLiteDatabase`로 이름 변경
- `BaseDatabase` 상속
- 싱글톤 제거, 인스턴스 기반으로 변경
- `name` 속성으로 DB 식별

```python
from database.base import BaseDatabase

class SQLiteDatabase(BaseDatabase):
    """SQLite 데이터베이스 구현"""

    def __init__(self, name: str, config: dict):
        super().__init__(name)
        self._config = config
        self._pool: AsyncConnectionPool = None

    @classmethod
    async def create(cls, name: str, config: dict) -> 'SQLiteDatabase':
        instance = cls(name, config)
        await instance._initialize()
        return instance

    async def _initialize(self):
        # 기존 초기화 로직 (pool 생성 등)
        ...

    def transaction(self, readonly: bool = False) -> 'ManagedTransaction':
        return ManagedTransaction(self, readonly)

    async def close(self):
        if self._pool:
            await self._pool.close()
```

### 4단계: ManagedTransaction 구현
**파일**: `database/sqlite3/connection.py`

```python
class ManagedTransaction:
    """다중 DB 트랜잭션용 컨텍스트 매니저"""

    def __init__(self, db: SQLiteDatabase, readonly: bool = False):
        self._db = db
        self._readonly = readonly
        self._pooled_conn: PooledConnection = None
        self._ctx: TransactionContext = None

    async def __aenter__(self) -> TransactionContext:
        self._pooled_conn = await self._db.pool.acquire()
        self._ctx = TransactionContext(self._pooled_conn.connection, self._readonly)

        if self._readonly:
            await self._pooled_conn.connection.execute("BEGIN DEFERRED")
        else:
            await self._pooled_conn.connection.execute("BEGIN IMMEDIATE")
        self._ctx._in_transaction = True

        # ContextVar에 DB 이름으로 저장
        _set_connection(self._db.name, self._ctx)
        return self._ctx

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type:
                await self._ctx.rollback()
            else:
                await self._ctx.commit()
        finally:
            _clear_connection(self._db.name)
            await self._db.pool.release(self._pooled_conn)
```

### 5단계: ContextVar 다중 DB 지원
**파일**: `database/sqlite3/connection.py`

```python
# 기존 (단일 DB)
_current_connection: ContextVar[Optional[TransactionContext]] = ...

# 변경 (다중 DB - 이름 기반)
_current_connections: ContextVar[dict[str, TransactionContext]] = ContextVar(
    '_current_connections', default={}
)

def _set_connection(db_name: str, ctx: TransactionContext):
    conns = _current_connections.get().copy()
    conns[db_name] = ctx
    _current_connections.set(conns)

def _clear_connection(db_name: str):
    conns = _current_connections.get().copy()
    conns.pop(db_name, None)
    _current_connections.set(conns)

def get_connection(db_name: str = 'default') -> TransactionContext:
    """특정 DB의 현재 트랜잭션 컨텍스트 반환"""
    conns = _current_connections.get()
    if db_name not in conns:
        raise RuntimeError(f"No active transaction for DB '{db_name}'")
    return conns[db_name]
```

### 6단계: transactional 데코레이터 수정
**파일**: `database/sqlite3/connection.py`

```python
from contextlib import AsyncExitStack
from database.base import BaseDatabase

def transactional(*dbs, readonly: bool = False):
    """
    다중 DB 트랜잭션 데코레이터

    @transactional(jobu_db)
    @transactional(jobu_db, biz_db)
    @transactional(jobu_db, readonly=True)
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with AsyncExitStack() as stack:
                for db in dbs:
                    await stack.enter_async_context(
                        db.transaction(readonly=readonly)
                    )
                return await func(*args, **kwargs)
        return wrapper

    # @transactional (인자 없이) 호환성 - default DB 사용
    if len(dbs) == 1 and callable(dbs[0]) and not isinstance(dbs[0], BaseDatabase):
        func = dbs[0]
        from database.registry import DatabaseRegistry
        dbs = (DatabaseRegistry.get('default'),)
        return decorator(func)

    return decorator
```

### 7단계: config/database.yaml 다중 DB 설정
**파일**: `config/database.yaml`

```yaml
databases:
  default:  # 기본 DB (하위 호환용)
    type: sqlite
    path: data/jobu.db
    pool:
      pool_size: 5
      pool_timeout: 30.0
    options:
      journal_mode: WAL

  # 같은 타입(sqlite) 여러 개 가능
  # business:
  #   type: sqlite
  #   path: data/business.db
  #   pool:
  #     pool_size: 3

  # analytics:
  #   type: sqlite
  #   path: data/analytics.db
```

### 8단계: 하위 호환성 유지
기존 코드가 깨지지 않도록:

```python
# 기존 사용법 (계속 동작)
@transactional
async def create_job():
    ctx = get_connection()  # default DB
    ...

# 새 사용법 - 이름으로 DB 지정
jobu_db = DatabaseRegistry.get('default')
biz_db = DatabaseRegistry.get('business')

@transactional(jobu_db, biz_db)
async def sync_data():
    jobu_ctx = get_connection('default')
    biz_ctx = get_connection('business')
    ...
```

---

## 파일 구조

```
database/
  __init__.py          # DatabaseRegistry, get_connection export
  base.py              # BaseDatabase 추상 클래스 (신규)
  registry.py          # DatabaseRegistry 클래스 (신규)
  sqlite3/
    __init__.py
    connection.py      # SQLiteDatabase (싱글톤 제거, 다중 인스턴스)
    sql/
      init.sql

config/
  database.yaml        # databases: 키 아래 다중 DB 설정
```

---

## 구현 순서

| 순서 | 작업 | 파일 |
|------|------|------|
| 1 | BaseDatabase 추상 클래스 | database/base.py |
| 2 | DatabaseRegistry 구현 | database/registry.py |
| 3 | SQLiteDatabase 클래스 (싱글톤 제거) | database/sqlite3/connection.py |
| 4 | ManagedTransaction 구현 | database/sqlite3/connection.py |
| 5 | ContextVar 다중 DB 지원 | database/sqlite3/connection.py |
| 6 | transactional 데코레이터 수정 | database/sqlite3/connection.py |
| 7 | config/database.yaml 구조 변경 | config/database.yaml |
| 8 | 기존 테스트 수정 및 신규 테스트 추가 | test/ |

---

## 테스트 항목

### 단위 테스트 (test/multi_db_test.py)

1. **단일 DB 트랜잭션**
   - 커밋 성공
   - 롤백 (예외 발생 시)
   - readonly 모드에서 write 차단

2. **다중 SQLite DB 트랜잭션**
   - 2개 SQLite DB 커밋 성공
   - 첫 번째 DB에서 예외 -> 모두 롤백
   - 두 번째 DB에서 예외 -> 모두 롤백
   - 같은 타입 DB 여러 개 동시 사용

3. **하위 호환성**
   - `@transactional` (인자 없음) -> default DB 사용
   - `get_connection()` (인자 없음) -> default DB 반환

4. **DatabaseRegistry**
   - 다중 DB 등록/조회
   - config에서 여러 DB 초기화
   - 존재하지 않는 DB 조회 시 KeyError

---

## 제한사항

### 커밋 순간 부분 실패
```
db1.commit() 성공 -> db2.commit() 실패 -> db1은 이미 커밋됨
```
- 진짜 분산 트랜잭션(2PC) 없이는 해결 불가
- 멱등성으로 커버 (재시도해도 안전한 로직 설계 필요)

### SQLite 제약
- SQLite는 단일 writer lock이라 다중 DB 동시 write 시 성능 이슈 가능
- 프로덕션에서는 PostgreSQL 등 사용 권장

---

## 향후 확장

### PostgreSQL 지원 추가 시
```python
# database/postgres/connection.py
class PostgresDatabase(BaseDatabase):
    def transaction(self, readonly: bool = False):
        return PostgresManagedTransaction(self, readonly)
```

```yaml
# config/database.yaml
databases:
  default:
    type: sqlite
    path: data/jobu.db

  business:
    type: postgres
    host: localhost
    port: 5432
    database: myapp
    user: admin
    password: secret

  analytics:
    type: sqlite
    path: data/analytics.db
```

```python
# 사용 예시 - SQLite 2개 + PostgreSQL 1개
default_db = DatabaseRegistry.get('default')    # SQLite
biz_db = DatabaseRegistry.get('business')       # PostgreSQL
analytics_db = DatabaseRegistry.get('analytics') # SQLite

@transactional(default_db, biz_db, analytics_db)
async def sync_all():
    default_ctx = get_connection('default')
    biz_ctx = get_connection('business')
    analytics_ctx = get_connection('analytics')
    ...
```

---

## 실제 구현 결과

### 구현 완료 항목

| 순서 | 작업 | 파일 | 상태 |
|------|------|------|------|
| 1 | BaseDatabase 추상 클래스 | database/base.py | 완료 |
| 2 | DatabaseRegistry 구현 | database/registry.py | 완료 |
| 3 | SQLiteDatabase 클래스 (싱글톤 제거) | database/sqlite3/connection.py | 완료 |
| 4 | ManagedTransaction 구현 | database/sqlite3/connection.py | 완료 |
| 5 | ContextVar 다중 DB 지원 | database/sqlite3/connection.py | 완료 |
| 6 | transactional 데코레이터 수정 | database/sqlite3/connection.py | 완료 |
| 7 | config/database.yaml 구조 변경 | config/database.yaml | 완료 |
| 8 | 기존 테스트 수정 및 신규 테스트 추가 | test/sqlite3_test.py | 완료 |

### 추가 구현 (계획 외)

#### 모듈별 DB 설정

각 모듈(dispatcher, worker, admin)이 자신이 사용할 DB만 초기화하도록 설정 추가:

| 모듈 | 설정 파일 | 추가 필드 |
|------|-----------|-----------|
| dispatcher | config/dispatcher.yaml | `database: default` |
| worker | config/worker.yaml | `database: default`, `databases: []` |
| admin | config/admin.yaml | `database: default` |

#### DatabaseRegistry.init_from_config() 개선

```python
# 기존: 전체 DB 초기화
await DatabaseRegistry.init_from_config(config)

# 추가: 특정 DB만 초기화
await DatabaseRegistry.init_from_config(config, ['default'])
await DatabaseRegistry.init_from_config(config, ['default', 'business'])
```

#### Worker databases 설정

Worker는 job 관리용 DB와 핸들러용 추가 DB를 분리:

```yaml
# config/worker.yaml
worker:
  database: default               # job 관리용 DB
  databases:                      # 핸들러에서 사용할 추가 DB들
    - business
    - analytics
  pool_size: 5
```

```python
# worker/main.py
config = WorkerConfig(**worker_config.get("worker", {}))
db_names = [config.database] + config.databases
await DatabaseRegistry.init_from_config(db_config, db_names)
```

### 수정된 파일 목록

#### 코드
- database/base.py (신규)
- database/registry.py (신규)
- database/sqlite3/connection.py (대폭 수정)
- config/database.yaml (구조 변경)
- config/dispatcher.yaml (database 필드 추가)
- config/worker.yaml (database, databases 필드 추가)
- config/admin.yaml (database 필드 추가)
- dispatcher/model/dispatcher.py (DispatcherConfig.database 추가)
- dispatcher/main.py (선택적 DB 초기화)
- worker/main.py (WorkerConfig.database/databases 추가, 선택적 DB 초기화)
- admin/main.py (선택적 DB 초기화)

#### 문서
- README.md
- CLAUDE.md
- database/README.md
- database/sqlite3/README.md
- dispatcher/README.md
- worker/README.md
- admin/README.md

### 테스트 결과

```
67 passed in 14.38s
```

다중 DB 트랜잭션 테스트 (test/sqlite3_test.py::TestMultiDatabase):
- test_multi_db_commit: 2개 DB 동시 커밋
- test_multi_db_rollback_on_first_db_error: 첫 번째 DB 에러 시 전체 롤백
- test_multi_db_rollback_on_second_db_error: 두 번째 DB 에러 시 전체 롤백
- test_database_registry: DatabaseRegistry CRUD
- test_get_connection_error: 트랜잭션 없이 get_connection 호출 시 에러

### 하위 호환성

기존 코드 변경 없이 동작:

```python
# 기존 사용법 (계속 동작)
@transactional
async def create_job():
    ctx = get_connection()  # default DB
    ...

@transactional_readonly
async def get_jobs():
    ctx = get_connection()
    return await ctx.fetch_all("SELECT ...")
```
