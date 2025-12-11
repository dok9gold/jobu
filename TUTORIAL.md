# JobU Tutorial

배치 스케줄러의 원리를 학습하기 위한 튜토리얼입니다.

## 목차

1. [시작하기](#1-시작하기)
2. [Admin 페이지로 크론 등록하기](#2-admin-페이지로-크론-등록하기)
3. [배치 스케줄러 개념](#3-배치-스케줄러-개념)
4. [전체 흐름 따라가기](#4-전체-흐름-따라가기)
5. [핵심 모듈 분석](#5-핵심-모듈-분석)
6. [샘플 Handler 분석](#6-샘플-handler-분석)

---

## 1. 시작하기

### 프로젝트 설치

```bash
# 템플릿에서 프로젝트 생성
pip install jobu
jobu init myproject --template example
cd myproject

# 또는 직접 clone
git clone -b template/example https://github.com/dok9gold/jobu.git myproject
cd myproject
```

### 환경 설정

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### Windows 인코딩 설정

Windows 한글 경로 인코딩 문제는 `main.py`에서 자동 처리됩니다. (별도 설정 불필요)

만약 다른 스크립트 실행 시 인코딩 에러 발생하면:

```powershell
# PowerShell
$env:PYTHONUTF8=1

# CMD
set PYTHONUTF8=1
```

### 첫 실행

```bash
# 전체 실행 (Dispatcher + Worker + Admin)
python main.py

# 개별 실행
python main.py admin       # Admin API만
python main.py dispatcher  # Dispatcher만
python main.py worker      # Worker만
```

실행 후 확인:
- http://localhost:8080/docs - API 문서 (Swagger)
- http://localhost:8080/crons - 크론 관리 화면
- http://localhost:8080/jobs - Job 실행 이력

---

## 2. Admin 페이지로 크론 등록하기

### 크론 관리 화면 접속

브라우저에서 http://localhost:8080/crons 접속

### 크론 등록

| 필드 | 설명 | 예시 |
|------|------|------|
| Name | 크론 이름 (고유값) | `my_first_job` |
| Description | 설명 | `테스트용 크론` |
| Cron Expression | 크론 표현식 | `* * * * *` (매분) |
| Handler Name | 실행할 핸들러 이름 | `sqlite_crud` |
| Handler Params | JSON 파라미터 | `{}` |
| Enabled | 활성화 여부 | 체크 |
| Allow Overlap | 중복 실행 허용 | 체크 |
| Max Retry | 최대 재시도 횟수 | `3` |
| Timeout | 타임아웃 (초) | `3600` |

### 등록 가능한 Handler 목록

| Handler Name | 설명 | 필요 DB |
|--------------|------|---------|
| `sqlite_crud` | SQLite CRUD 예제 | sqlite_2 |
| `postgres_crud` | PostgreSQL CRUD 예제 | postgres_1 (Docker) |
| `mysql_crud` | MySQL CRUD 예제 | mysql_1 (Docker) |
| `sync_sqlite_to_postgres` | SQLite -> PostgreSQL 동기화 | default, postgres_1 (Docker) |
| `sync_postgres_to_mysql` | PostgreSQL -> MySQL 동기화 | postgres_1, mysql_1 (Docker) |
| `multi_db_report` | 3개 DB 집계 리포트 | 전체 DB (Docker) |
| `service_layer` | 서비스 레이어 패턴 예제 | sqlite_2 |
| `do_work_pattern` | 심플 트랜잭션 패턴 예제 | sqlite_2 |
| `concurrent_queries` | 병렬 쿼리 예제 | 전체 DB (Docker) |

### Job 실행 이력 확인

http://localhost:8080/jobs 에서 실행 이력 확인

| 상태 | 의미 |
|------|------|
| PENDING | 대기 중 (Dispatcher가 생성) |
| RUNNING | 실행 중 (Worker가 처리 중) |
| SUCCESS | 성공 |
| FAILED | 실패 |
| RETRY | 재시도 대기 |

---

## 3. 배치 스케줄러 개념

### 배치 vs 실시간 처리

| 구분 | 배치 처리 | 실시간 처리 |
|------|-----------|-------------|
| 처리 시점 | 정해진 시간에 일괄 | 요청 즉시 |
| 예시 | 정산, 리포트, 데이터 동기화 | API 응답, 웹소켓 |
| 특징 | 대량 데이터, 재시도 가능 | 즉각 응답 필요 |

### 크론 표현식

```
* * * * *
| | | | |
| | | | +-- 요일 (0-7, 0과 7은 일요일)
| | | +---- 월 (1-12)
| | +------ 일 (1-31)
| +-------- 시 (0-23)
+---------- 분 (0-59)
```

**예시:**

| 표현식 | 의미 |
|--------|------|
| `* * * * *` | 매분 |
| `0 * * * *` | 매시 정각 |
| `0 0 * * *` | 매일 자정 |
| `0 9 * * 1` | 매주 월요일 오전 9시 |
| `*/5 * * * *` | 5분마다 |
| `0 0 1 * *` | 매월 1일 자정 |

### Dispatcher-Worker 패턴

```
+-------------+     +-----------------+     +---------------+
|  cron_jobs  |---->|   Dispatcher    |---->| job_executions|
| (크론 정보)  |     |  (Job 생성자)    |     |   (Job 큐)    |
+-------------+     +-----------------+     +-------+-------+
                                                   |
                                                   v
                                           +---------------+
                                           |    Worker     |
                                           | (Job 실행자)   |
                                           +-------+-------+
                                                   |
                                                   v
                                           +---------------+
                                           |    Handler    |
                                           |  (비즈니스)    |
                                           +---------------+
```

**역할 분리의 장점:**
- Dispatcher와 Worker를 독립 배포 가능
- Worker 수평 확장으로 처리량 증가
- 한쪽 장애 시 다른 쪽 영향 최소화

---

## 4. 전체 흐름 따라가기

### 흐름 요약

```
[1] cron_jobs 테이블
        |
        v
[2] Dispatcher (폴링)
        | 스케줄 도달 시 Job 생성
        v
[3] job_executions 테이블 (PENDING)
        |
        v
[4] Worker (폴링)
        | PENDING Job 획득 -> RUNNING
        v
[5] Handler 실행
        |
        v
[6] 결과 저장 (SUCCESS/FAILED)
```

### [1] cron_jobs 테이블

크론 스케줄 정보를 저장합니다.

```sql
-- database/sqlite3/sql/init.sql
CREATE TABLE cron_jobs (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    cron_expression TEXT NOT NULL,  -- 크론 표현식
    handler_name TEXT NOT NULL,     -- 실행할 핸들러
    handler_params TEXT,            -- JSON 파라미터
    is_enabled INTEGER DEFAULT 1,   -- 활성화 여부
    ...
);
```

### [2] Dispatcher - Job 생성

`dispatcher/main.py`의 `Dispatcher` 클래스

```python
# 주요 로직 (간략화)
async def _poll_and_dispatch(self):
    # 1. 활성화된 크론 조회
    crons = await self._get_enabled_crons()

    for cron in crons:
        # 2. 다음 실행 시간 계산 (croniter)
        next_time = croniter(cron.cron_expression).get_next()

        # 3. 실행 시점 도달 시 Job 생성
        if next_time <= now:
            await self._create_job_execution(cron, next_time)
```

### [3] job_executions 테이블

실행할 Job 정보를 저장합니다.

```sql
CREATE TABLE job_executions (
    id INTEGER PRIMARY KEY,
    job_id INTEGER NOT NULL,        -- cron_jobs.id
    scheduled_time TEXT NOT NULL,   -- 예정 실행 시간
    status TEXT DEFAULT 'PENDING',  -- 상태
    started_at TEXT,                -- 실행 시작
    finished_at TEXT,               -- 실행 종료
    retry_count INTEGER DEFAULT 0,  -- 재시도 횟수
    error_message TEXT,             -- 에러 메시지
    result TEXT,                    -- 실행 결과 JSON
    ...
);
```

### [4] Worker - Job 폴링 및 실행

`worker/main.py`의 `Worker` 클래스

```python
# 주요 로직 (간략화)
async def _poll_jobs(self):
    # 1. PENDING 상태 Job 조회
    jobs = await self._fetch_pending_jobs()

    for job in jobs:
        # 2. 워커풀에 실행 요청
        await self._worker_pool.submit(job)
```

### [5] Executor - Handler 실행

`worker/executor.py`의 `Executor` 클래스

```python
async def execute(self, job_info: JobInfo):
    # 1. RUNNING 상태로 변경 (claim)
    await self._claim_execution(job_info.id)

    # 2. 핸들러 조회
    handler = get_handler(job_info.handler_name)

    # 3. 핸들러 실행 (타임아웃 적용)
    result = await asyncio.wait_for(
        handler.execute(params),
        timeout=job_info.timeout_seconds
    )

    # 4. 결과 저장
    await self._complete_execution(job_info.id, result)
```

### [6] 상태 변화

```
PENDING -> RUNNING -> SUCCESS
                   -> FAILED -> RETRY -> RUNNING -> ...
```

---

## 5. 핵심 모듈 분석

### Dispatcher 모듈

**위치:** `dispatcher/`

**역할:** 크론 스케줄에 따라 Job 생성

**주요 파일:**
| 파일 | 역할 |
|------|------|
| `main.py` | Dispatcher 메인 로직 |
| `model/dispatcher.py` | 설정 및 데이터 모델 |
| `sql/dispatcher.sql` | SQL 쿼리 |

**핵심 코드:**
```python
# dispatcher/main.py
class Dispatcher:
    async def _poll_and_dispatch(self):
        """활성화된 크론을 폴링하여 Job 생성"""
        crons = await self._get_enabled_crons()
        for cron in crons:
            await self._process_cron(cron)
```

### Worker 모듈

**위치:** `worker/`

**역할:** Job 실행 및 핸들러 관리

**주요 파일:**
| 파일 | 역할 |
|------|------|
| `main.py` | Worker 메인 로직 |
| `executor.py` | Job 실행기 |
| `base.py` | 핸들러 베이스 클래스 |
| `pool.py` | 워커풀 |

**핸들러 등록 방식:**
```python
# worker/base.py
@handler("my_handler")  # 데코레이터로 등록
class MyHandler(BaseHandler):
    async def execute(self, params: HandlerParams) -> HandlerResult:
        # 비즈니스 로직
        pass
```

### Database 모듈

**위치:** `database/`

**역할:** DB 커넥션풀, 트랜잭션 관리

**지원 DB:**
- SQLite (`database/sqlite3/`)
- PostgreSQL (`database/postgres/`)
- MySQL (`database/mysql/`)

**트랜잭션 데코레이터:**
```python
from database import transactional, transactional_readonly, get_connection

# 단일 DB 트랜잭션
@transactional(db)
async def create_data():
    ctx = get_connection('default')
    await ctx.execute("INSERT INTO ...")

# 읽기 전용 트랜잭션
@transactional_readonly(db)
async def read_data():
    ctx = get_connection('default')
    return await ctx.fetch_all("SELECT * FROM ...")

# 멀티 DB 트랜잭션
@transactional(db1, db2)
async def sync_data():
    ctx1 = get_connection('postgres_1')
    ctx2 = get_connection('mysql_1')
    # 둘 다 커밋 또는 둘 다 롤백
```

### Admin 모듈

**위치:** `admin/`

**역할:** 관리 API 및 웹 화면

**주요 URL:**
| URL | 역할 |
|-----|------|
| `/docs` | Swagger API 문서 |
| `/crons` | 크론 관리 화면 |
| `/jobs` | Job 실행 이력 화면 |
| `/api/crons/*` | 크론 CRUD API |
| `/api/jobs/*` | Job 조회 API |

---

## 6. 샘플 Handler 분석

샘플 핸들러는 `worker/job/` 디렉토리에 있습니다.

### 디렉토리 구조

```
worker/job/
  basic/           # 단일 DB CRUD 예제
  multi_db/        # 멀티 DB 트랜잭션 예제
  patterns/        # 코드 구조 패턴
  async_patterns/  # 비동기 고급 패턴
```

### 학습 순서

#### 1단계: Basic - 단일 DB CRUD

가장 기본적인 핸들러 구조를 학습합니다.

**파일:** `worker/job/basic/sqlite_crud.py`

```python
@handler("sqlite_crud")
class SqliteCrudHandler(BaseHandler):
    async def execute(self, params: HandlerParams) -> HandlerResult:
        db = get_db('sqlite_2')

        @transactional(db)
        async def do_work():
            ctx = get_connection('sqlite_2')
            # INSERT
            await queries.insert_sample_data(ctx.connection, ...)
            # SELECT
            rows = await queries.get_sample_data(ctx.connection)
            return rows

        result = await do_work()
        return HandlerResult(action='created', data={'rows': result})
```

#### 2단계: Multi-DB - 멀티 DB 트랜잭션

여러 DB에 걸친 트랜잭션을 학습합니다.

**파일:** `worker/job/multi_db/sync_sqlite_to_postgres.py`

```python
@transactional(sqlite_db, postgres_db)  # 둘 다 커밋 또는 롤백
async def sync():
    sqlite_ctx = get_connection('default')
    pg_ctx = get_connection('postgres_1')

    # SQLite에서 읽기
    data = await sqlite_queries.get_data(sqlite_ctx.connection)

    # PostgreSQL에 쓰기
    await pg_queries.insert_data(pg_ctx.connection, data)
```

#### 3단계: Patterns - 코드 구조 패턴

유지보수하기 좋은 구조를 학습합니다.

**서비스 레이어 패턴:** `worker/job/patterns/service_layer.py`
```
Handler (Controller) -> Service -> Database
```

**do_work 패턴:** `worker/job/patterns/do_work_pattern.py`
```
execute() -> do_work() with @transactional
```

#### 4단계: Async Patterns - 비동기 고급 패턴

성능 최적화를 위한 asyncio 패턴을 학습합니다.

**파일:** `worker/job/async_patterns/concurrent_queries.py`

```python
# asyncio.gather로 병렬 쿼리
results = await asyncio.gather(
    fetch_from_sqlite(),
    fetch_from_postgres(),
    fetch_from_mysql(),
)
```

### 핸들러 목록 요약

| 핸들러 | 카테고리 | 핵심 학습 포인트 |
|--------|----------|------------------|
| `sqlite_crud` | basic | 기본 CRUD, 트랜잭션 |
| `postgres_crud` | basic | PostgreSQL 사용법 |
| `mysql_crud` | basic | MySQL 사용법 |
| `sync_sqlite_to_postgres` | multi_db | 2개 DB 동기화 |
| `sync_postgres_to_mysql` | multi_db | 2개 DB 동기화 |
| `multi_db_report` | multi_db | 3개 DB 읽기 전용 |
| `service_layer` | patterns | Handler -> Service 분리 |
| `do_work_pattern` | patterns | 심플한 트랜잭션 분리 |
| `concurrent_queries` | async_patterns | asyncio.gather 병렬화 |

자세한 내용은 [worker/job/README.md](worker/job/README.md) 참고

---

## 다음 단계

- [CONTRIBUTING.md](CONTRIBUTING.md) - 개발 규칙, 네이밍 규칙
- [PRODUCTION.md](PRODUCTION.md) - 운영 환경 배포 가이드
- [database/README.md](database/README.md) - DB 커넥션풀 상세
