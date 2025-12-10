# Phase 6: PostgreSQL, MySQL 커넥션풀 개발 및 Docker 환경 구성

## 개요
기존 SQLite 구현체를 참고하여 PostgreSQL과 MySQL 커넥션풀을 구현하고, Docker를 통한 개발/테스트 환경을 구성한다.

## 현재 구조 분석

### 공통 인터페이스
- `BaseDatabase` (database/base.py): 추상 클래스, `transaction()`, `close()` 메서드 정의
- `DatabaseRegistry` (database/registry.py): 다중 DB 인스턴스 관리, `init_from_config()`에서 type별 분기 처리
- `TransactionContext`: 트랜잭션 컨텍스트 관리 (execute, fetch_one, fetch_all 등)
- `transactional` 데코레이터: 다중 DB 트랜잭션 지원 (Best-Effort 방식)

### 구현 필요 항목
각 DB 구현체에서 구현해야 할 클래스:
1. `PoolConfig` - 커넥션풀 설정
2. `PooledConnection` - 풀에서 관리되는 연결
3. `TransactionContext` - 트랜잭션 컨텍스트 (execute, fetch_one, fetch_all 등)
4. `AsyncConnectionPool` - 비동기 커넥션풀
5. `ManagedTransaction` - 트랜잭션 컨텍스트 매니저
6. `XxxDatabase(BaseDatabase)` - 메인 데이터베이스 클래스

---

## 구현 계획

### 1. Docker 환경 구성

#### 1.1 docker-compose.yaml 작성
```yaml
# docker/docker-compose.yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: jobu
      POSTGRES_PASSWORD: jobu_dev
      POSTGRES_DB: jobu
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init/postgres:/docker-entrypoint-initdb.d
    deploy:
      resources:
        limits:
          memory: 256M
        reservations:
          memory: 128M

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root_dev
      MYSQL_USER: jobu
      MYSQL_PASSWORD: jobu_dev
      MYSQL_DATABASE: jobu
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
      - ./init/mysql:/docker-entrypoint-initdb.d
    deploy:
      resources:
        limits:
          memory: 512M
        reservations:
          memory: 256M

volumes:
  postgres_data:
  mysql_data:
```

#### 1.2 초기화 SQL 스크립트
- `docker/init/postgres/init.sql` - PostgreSQL 테이블 생성
- `docker/init/mysql/init.sql` - MySQL 테이블 생성

---

### 2. PostgreSQL 구현체

#### 2.1 디렉토리 구조
```
database/
  postgres/
    __init__.py
    connection.py    # PostgresDatabase, AsyncConnectionPool, TransactionContext
    sql/
      init.sql       # 초기 테이블 생성 (PostgreSQL 문법)
```

#### 2.2 의존성 추가
```
asyncpg>=0.29.0
```

#### 2.3 주요 구현 사항
- `asyncpg` 라이브러리 사용 (고성능 비동기 PostgreSQL 드라이버)
- PostgreSQL 고유 설정: `statement_timeout`, `idle_in_transaction_session_timeout`
- 트랜잭션: `BEGIN` / `COMMIT` / `ROLLBACK`
- Placeholder: `$1, $2, ...` (SQLite와 다름, 내부 변환 또는 사용자 주의)
- Row factory: `asyncpg.Record` (dict-like 접근 가능)

#### 2.4 TransactionContext 메서드
```python
class TransactionContext:
    async def execute(self, sql: str, *args) -> str  # status
    async def executemany(self, sql: str, args: list) -> None
    async def fetch_one(self, sql: str, *args) -> Optional[Record]
    async def fetch_all(self, sql: str, *args) -> list[Record]
```

---

### 3. MySQL 구현체

#### 3.1 디렉토리 구조
```
database/
  mysql/
    __init__.py
    connection.py    # MySQLDatabase, AsyncConnectionPool, TransactionContext
    sql/
      init.sql       # 초기 테이블 생성 (MySQL 문법)
```

#### 3.2 의존성 추가
```
asyncmy>=0.2.9
```

#### 3.3 주요 구현 사항
- `asyncmy` 라이브러리 사용 (Cython 기반, aiosql 공식 지원)
- MySQL 고유 설정: `charset`, `autocommit`, `sql_mode`
- 트랜잭션: `START TRANSACTION` / `COMMIT` / `ROLLBACK`
- Placeholder: `%s` (SQLite의 `?`와 다름)
- Row factory: `DictCursor` 사용으로 dict-like 접근

#### 3.4 TransactionContext 메서드
```python
class TransactionContext:
    async def execute(self, sql: str, parameters=None) -> int  # affected rows
    async def executemany(self, sql: str, parameters: list) -> int
    async def fetch_one(self, sql: str, parameters=None) -> Optional[dict]
    async def fetch_all(self, sql: str, parameters=None) -> list[dict]
```

---

### 4. DatabaseRegistry 수정

#### 4.1 registry.py 업데이트
```python
async def init_from_config(cls, config: dict, db_names: Optional[List[str]] = None) -> None:
    ...
    if db_type == 'sqlite':
        from database.sqlite3.connection import SQLiteDatabase
        db = await SQLiteDatabase.create(name, db_config)
    elif db_type == 'postgres':
        from database.postgres.connection import PostgresDatabase
        db = await PostgresDatabase.create(name, db_config)
    elif db_type == 'mysql':
        from database.mysql.connection import MySQLDatabase
        db = await MySQLDatabase.create(name, db_config)
    else:
        raise ValueError(f"Unsupported database type: {db_type}")
```

---

### 5. config/database.yaml 확장

```yaml
databases:
  default:
    type: sqlite
    path: "data/jobu.db"
    pool:
      pool_size: 5
      pool_timeout: 30.0
      max_idle_time: 300.0
    options:
      busy_timeout: 5000
      journal_mode: "WAL"

  postgres_main:
    type: postgres
    host: localhost
    port: 5432
    database: jobu
    user: jobu
    password: jobu_dev
    pool:
      min_size: 2
      max_size: 10
      max_inactive_connection_lifetime: 300.0
    options:
      statement_timeout: 30000  # ms
      timezone: "UTC"

  mysql_main:
    type: mysql
    host: localhost
    port: 3306
    database: jobu
    user: jobu
    password: jobu_dev
    pool:
      minsize: 2
      maxsize: 10
      pool_recycle: 300
    options:
      charset: "utf8mb4"
      autocommit: false
```

---

### 6. 테스트 작성

#### 6.1 단위 테스트
- `test/database/test_postgres.py` - PostgreSQL 커넥션풀 테스트
- `test/database/test_mysql.py` - MySQL 커넥션풀 테스트

#### 6.2 통합 테스트
- 다중 DB 트랜잭션 테스트 (SQLite + PostgreSQL)
- 트랜잭션 롤백 테스트
- 커넥션풀 고갈 테스트

---

## 구현 순서

1. Docker 환경 구성 (`docker/docker-compose.yaml`, 초기화 SQL)
2. PostgreSQL 구현체 개발 (`database/postgres/`)
3. MySQL 구현체 개발 (`database/mysql/`)
4. DatabaseRegistry 수정 (type별 분기 추가)
5. config/database.yaml 예시 업데이트
6. 테스트 작성 및 검증
7. README 업데이트

---

## 참고 사항

### SQL Placeholder 차이점
| DB | Placeholder | 예시 |
|----|-------------|------|
| SQLite | `?` | `SELECT * FROM users WHERE id = ?` |
| PostgreSQL | `$1, $2, ...` | `SELECT * FROM users WHERE id = $1` |
| MySQL | `%s` | `SELECT * FROM users WHERE id = %s` |

### 트랜잭션 Best-Effort 방식
- `@transactional(db1, db2)`는 모든 DB가 성공해야 커밋
- 하나라도 실패하면 모든 DB 롤백 시도
- 롤백 실패 시 로깅만 수행 (Best-Effort)
- 2PC(Two-Phase Commit) 미지원 (단순 구현)

### aiosql 호환성
- PostgreSQL: `aiosql`의 `asyncpg` 드라이버 지원
- MySQL: `aiosql`의 `asyncmy` 드라이버 지원
- 각 모듈별 SQL 파일은 해당 DB 문법에 맞게 작성 필요