# Database 모듈

다중 데이터베이스 커넥션풀 및 트랜잭션 관리 모듈입니다.

## 동작 원리

```
[Application] --@transactional--> [DatabaseRegistry] --acquire--> [ConnectionPool]
                                         |
                    +--------------------+--------------------+
                    |                    |                    |
              [SQLiteDatabase]    [PostgresDatabase]    [MySQLDatabase]
```

1. `DatabaseRegistry.init_from_config()`로 설정 파일 기반 DB 초기화
2. `@transactional` 데코레이터가 커넥션풀에서 커넥션 획득
3. ContextVar로 트랜잭션 컨텍스트 전파
4. 함수 종료 시 자동 커밋/롤백 및 커넥션 반환

## 지원 데이터베이스

| DB | 라이브러리 | Placeholder |
|----|------------|-------------|
| SQLite3 | aiosqlite | `?` |
| PostgreSQL | asyncpg | `$1, $2, ...` |
| MySQL | asyncmy | `%s` |

## 구조

```
database/
  __init__.py       # 공개 API (transactional, get_connection 등)
  base.py           # BaseDatabase 추상 클래스
  context.py        # ContextVar 기반 트랜잭션 컨텍스트 관리
  transaction.py    # @transactional 데코레이터 (DB 종류 무관)
  exception.py      # 공통 예외 클래스
  registry.py       # DatabaseRegistry (다중 DB 관리)
  sqlite3/          # SQLite3 구현체
    connection.py   # SQLiteDatabase
  postgres/         # PostgreSQL 구현체
    connection.py   # PostgresDatabase
  mysql/            # MySQL 구현체
    connection.py   # MySQLDatabase
```

## 설정

`config/database.yaml`에서 다중 DB를 설정합니다.

```yaml
databases:
  default:
    type: sqlite
    path: data/jobu.db
    pool:
      pool_size: 5

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
```

## 사용법

### 초기화

```python
from database.registry import DatabaseRegistry

# 전체 DB 초기화
await DatabaseRegistry.init_from_config(config)

# 특정 DB만 초기화
await DatabaseRegistry.init_from_config(config, ['default', 'business'])
```

### 단일 DB 트랜잭션

```python
from database import transactional, transactional_readonly, get_connection

@transactional
async def create_job():
    ctx = get_connection()  # default DB
    await ctx.execute("INSERT INTO ...")

@transactional_readonly
async def get_jobs():
    ctx = get_connection()
    return await ctx.fetch_all("SELECT ...")
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

### 종료

```python
await DatabaseRegistry.close_all()
```

## 예외

| 예외 | 발생 조건 |
|------|-----------|
| ConnectionPoolExhaustedError | 타임아웃 내 커넥션 획득 실패 |
| TransactionError | 트랜잭션 관련 일반 에러 |
| ReadOnlyTransactionError | 읽기 전용 트랜잭션에서 쓰기 시도 |
| QueryExecutionError | 쿼리 실행 실패 |

## Docker 개발 환경

PostgreSQL, MySQL 테스트용 Docker 환경:

```bash
cd docker
docker-compose up -d          # 전체 실행
docker-compose up -d postgres # PostgreSQL만
docker-compose up -d mysql    # MySQL만
```

자세한 내용은 [docker/README.md](../docker/README.md) 참조.

