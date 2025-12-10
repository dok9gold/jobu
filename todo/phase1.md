# SQLite 커넥션풀 구현 및 테스트

## 구조
- 패키지: database/sqlite3
- 커넥션 구현 프로그램: database/sqlite3/connection.py
- 초기 테이블 생성 쿼리: database/sqlite3/sql/init.sql (aiosql 사용)
- 패키지 연결: __init__.py
- 설정 파일: config/database.yaml
  - database > sqlite > something... 구조

## 라이브러리 선정
- 동기 방식: sqlite3 (표준 라이브러리)
- 비동기 방식: aiosqlite
- 선정 기준
  - 프로젝트가 비동기 기반이므로 aiosqlite 사용
  - aiosql과의 호환성 확인 필요
  - aiosqlite는 sqlite3를 래핑하므로 sqlite3 설정 그대로 사용 가능

## 구현
1. sqlite 라이브러리 선정 (aiosqlite)
2. 커넥션풀 구현 (싱글톤)
3. 트랜잭션 구현 (데코레이터 사용)
4. 수동 트랜잭션 구현, (commit, rollback, flush...), 트랜잭션 데코레이터와 무관하게 작동 되어야 함
5. sql 쿼리, 결과 로그 구현 (console)
   - console 로그를 구현 하고, 추후 핸들러를 통해 elk 및 기타 로깅시스템에도 연동이 되어야 하므로, 빈 핸들러는 만들어서 TODO로 남겨 놓기
6. 비지니스로직에서 해당 DB커넥션을 로직내 전역변수로 간결하게 불러와서 사용 할 수 있어야 함
7. batch 모드 read only 모드 등의 구현이 가능한지 검토 해봐야 함

## 커넥션풀 설정
```yaml
# config/database.yaml
database:
  sqlite:
    path: "./data/jobu.db"           # DB 파일 경로
    pool_size: 5                      # 커넥션풀 크기
    pool_timeout: 30                  # 커넥션 대기 타임아웃 (초)
    busy_timeout: 5000                # SQLite busy timeout (밀리초)
    journal_mode: "WAL"               # WAL 모드 (동시성 향상)
    synchronous: "NORMAL"             # 동기화 모드 (FULL, NORMAL, OFF)
    cache_size: -2000                 # 캐시 크기 (음수: KB, 양수: 페이지)
    foreign_keys: true                # 외래키 제약조건 활성화
```

## 트랜잭션 데코레이터 사용 예시
```python
from database.sqlite3 import get_db, transactional, transactional_readonly

# 기본 트랜잭션 (자동 commit/rollback)
@transactional
async def create_job(job_data: JobInput) -> JobOutput:
    db = get_db()
    result = await db.execute(queries.insert_job, job_data.dict())
    return JobOutput(id=result.lastrowid)

# 읽기 전용 트랜잭션
@transactional_readonly
async def get_job_list() -> list[JobEntity]:
    db = get_db()
    rows = await db.fetch_all(queries.select_jobs)
    return [JobEntity(**row) for row in rows]

# 수동 트랜잭션
async def batch_process():
    db = get_db()
    try:
        await db.begin()
        for item in items:
            await db.execute(queries.update_item, item)
            if should_commit_batch:
                await db.commit()
                await db.begin()
        await db.commit()
    except Exception:
        await db.rollback()
        raise
```

## 테스트
- 테스트 파일: test/sqlite3_test.py
- 테스트 케이스
  1. 커넥션풀 기본 동작
     - 프로그램 파일내 전역변수로 간결하게 커넥션을 불러와서 사용 가능해야함
     - 커넥션풀을 여러개 불러와서 사용 가능해야 함
  2. 트랜잭션 동작
     - 데코레이터를 통한 자동 트랜잭션이 비지니스 로직 단위로 설정 되어야 함
     - 예외 발생시 자동 롤백 확인
     - 수동 트랜잭션(commit, rollback)이 정상 작동해야 함
  3. 커넥션풀 한계 테스트
     - 커넥션풀이 설정된 개수 이상으로 불러 왔을 경우 대기가 되는지 확인
     - 타임아웃 초과시 에러 발생 확인
  4. readOnly 모드 테스트
     - readOnly 트랜잭션에서 쓰기 시도시 에러 발생 확인
  5. 로깅 테스트
     - SQL 쿼리 및 실행 결과가 콘솔에 출력되는지 확인

## aiosql 쿼리 파일 규칙
```sql
-- name: get_job_by_id^
-- 단일 row 반환 (^)
SELECT * FROM jobs WHERE id = :id;

-- name: get_all_jobs
-- 복수 row 반환 (기본)
SELECT * FROM jobs WHERE enabled = :enabled;

-- name: insert_job<!
-- INSERT 후 lastrowid 반환 (<!)
INSERT INTO jobs (name, cron_expr, handler) VALUES (:name, :cron_expr, :handler);

-- name: update_job!
-- UPDATE/DELETE 실행, affected rows 반환 (!)
UPDATE jobs SET enabled = :enabled WHERE id = :id;

-- name: delete_job!
DELETE FROM jobs WHERE id = :id;
```

## 고려사항
- __init__.py를 활용해서 다른 프로그램에서 import를 간결하게 할 수 있도록 설정
- 커넥션 풀 설정 및 기타 DB설정값은 config/* 에서 관리
- exception 관리는 database 패키지에서 자체적으로 하지 않고 프로젝트 공통으로 관리
- 비지니스로직에서는 전역변수로 get_db()와 같은 함수를 사용해 간결하게 디비 연결 구현
- 트랜잭션은 비지니스로직단으로 관리, worker 프로그램 단위
- 트랜잭션은 기본적으로 비지니스로직에서 설정하나 예외적으로 수동으로 commit, rollback 등을 할 수 있어야 함
- database/sqlite3 패키지에 구현하도록 하고 추후 타 DB를 사용할 경우 database/{some DB}.. 에 구현함
- 비지니스로직에서 타 DB 혹은 타 커넥션을 사용할 수 있도록 설계 되어야 함
- 다중 트랜잭션 구현도 검토 해봐야하고 만약 불가하다면 수동 트랜잭션모드를 활성화 해서 각각 commit, rollback 할 수 있어야 함
- 트랜잭션에는 readOnly 모드가 있어야 함
- 기본적으로 모든 디비 기능은 aiosql를 사용하여 구현 함

## SQLite 성능 최적화 설정
- WAL(Write-Ahead Logging) 모드 사용으로 읽기/쓰기 동시성 향상
- busy_timeout 설정으로 락 대기 시간 조절
- 적절한 cache_size 설정으로 메모리 활용 최적화
- PRAGMA 설정은 커넥션 생성시 자동 적용되도록 구현

## 에러 처리 방향
- database 패키지에서는 예외를 발생시키기만 하고, 처리는 공통 에러 핸들러에서 수행
- 주요 예외 유형
  - ConnectionPoolExhaustedError: 커넥션풀 고갈
  - TransactionError: 트랜잭션 관련 에러
  - QueryExecutionError: 쿼리 실행 에러
- 에러 발생시 로깅 후 상위로 전파