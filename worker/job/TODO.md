# Worker Job Handler 리팩토링 계획

## 현재 상태

핸들러 리팩토링 완료. SQL 파일 분리 작업 필요.

현재 구조:
```
worker/job/
  sql/                    # 공통 SQL (삭제 예정)
    sqlite.sql
    postgres.sql
    mysql.sql
  basic/
  multi_db/
  patterns/
  async_patterns/
```

---

## SQL 파일 분리 계획

각 패키지별로 sql/ 디렉토리를 만들고, 핸들러별 SQL 파일 생성.
멀티 DB 핸들러는 `_sqlite.sql`, `_postgres.sql`, `_mysql.sql` 접미사로 구분.

### basic/sql/
단일 DB라서 파일 하나씩

| 파일 | 용도 | 어댑터 |
|------|------|--------|
| sqlite_crud.sql | SQLite CRUD | aiosqlite |
| postgres_crud.sql | PostgreSQL CRUD | asyncpg |
| mysql_crud.sql | MySQL CRUD | asyncmy |

### multi_db/sql/
멀티 DB라서 DB별로 파일 분리

| 파일 | 용도 | 어댑터 |
|------|------|--------|
| sync_sqlite_to_postgres_sqlite.sql | 동기화 - SQLite 쿼리 | aiosqlite |
| sync_sqlite_to_postgres_postgres.sql | 동기화 - PostgreSQL 쿼리 | asyncpg |
| sync_postgres_to_mysql_postgres.sql | 동기화 - PostgreSQL 쿼리 | asyncpg |
| sync_postgres_to_mysql_mysql.sql | 동기화 - MySQL 쿼리 | asyncmy |
| multi_db_report_sqlite.sql | 리포트 - SQLite 쿼리 | aiosqlite |
| multi_db_report_postgres.sql | 리포트 - PostgreSQL 쿼리 | asyncpg |
| multi_db_report_mysql.sql | 리포트 - MySQL 쿼리 | asyncmy |

### patterns/sql/
단일 DB (sqlite_2)

| 파일 | 용도 | 어댑터 |
|------|------|--------|
| service_layer.sql | 서비스 레이어용 | aiosqlite |
| do_work_pattern.sql | do_work 패턴용 | aiosqlite |

### async_patterns/sql/
멀티 DB 동시 쿼리

| 파일 | 용도 | 어댑터 |
|------|------|--------|
| concurrent_queries_sqlite.sql | 동시 쿼리 - SQLite | aiosqlite |
| concurrent_queries_postgres.sql | 동시 쿼리 - PostgreSQL | asyncpg |
| concurrent_queries_mysql.sql | 동시 쿼리 - MySQL | asyncmy |

---

## 작업 목록

### Phase 1: basic/sql/ 생성
- [ ] basic/sql/ 디렉토리 생성
- [ ] sqlite_crud.sql 생성
- [ ] postgres_crud.sql 생성
- [ ] mysql_crud.sql 생성
- [ ] 핸들러 파일들 SQL 경로 수정

### Phase 2: multi_db/sql/ 생성
- [ ] multi_db/sql/ 디렉토리 생성
- [ ] sync_sqlite_to_postgres_sqlite.sql + _postgres.sql 생성
- [ ] sync_postgres_to_mysql_postgres.sql + _mysql.sql 생성
- [ ] multi_db_report_sqlite.sql + _postgres.sql + _mysql.sql 생성
- [ ] 핸들러 파일들 SQL 경로 수정

### Phase 3: patterns/sql/ 생성
- [ ] patterns/sql/ 디렉토리 생성
- [ ] service_layer.sql 생성
- [ ] do_work_pattern.sql 생성
- [ ] 핸들러 및 서비스 파일들 SQL 경로 수정

### Phase 4: async_patterns/sql/ 생성
- [ ] async_patterns/sql/ 디렉토리 생성
- [ ] concurrent_queries_sqlite.sql + _postgres.sql + _mysql.sql 생성
- [ ] 핸들러 파일 SQL 경로 수정

### Phase 5: 정리
- [ ] 공통 sql/ 디렉토리 삭제
- [ ] README 업데이트

---

## 최종 디렉토리 구조

```
worker/job/
  README.md
  TODO.md
  __init__.py
  sample.py

  basic/
    __init__.py
    sqlite_crud.py
    postgres_crud.py
    mysql_crud.py
    sql/
      sqlite_crud.sql
      postgres_crud.sql
      mysql_crud.sql

  multi_db/
    __init__.py
    sync_sqlite_to_postgres.py
    sync_postgres_to_mysql.py
    multi_db_report.py
    sql/
      sync_sqlite_to_postgres_sqlite.sql
      sync_sqlite_to_postgres_postgres.sql
      sync_postgres_to_mysql_postgres.sql
      sync_postgres_to_mysql_mysql.sql
      multi_db_report_sqlite.sql
      multi_db_report_postgres.sql
      multi_db_report_mysql.sql

  patterns/
    __init__.py
    service_layer.py
    do_work_pattern.py
    service/
      __init__.py
      service_layer_service.py
    sql/
      service_layer.sql
      do_work_pattern.sql

  async_patterns/
    __init__.py
    concurrent_queries.py
    sql/
      concurrent_queries_sqlite.sql
      concurrent_queries_postgres.sql
      concurrent_queries_mysql.sql
```
