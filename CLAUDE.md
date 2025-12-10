# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

jobu (Job Unified) - Python 기반 통합 배치 스케줄링 시스템. RDB에 크론 정보를 저장하고, Dispatcher가 스케줄에 따라 Job을 생성하면 Worker가 실행하는 구조.

```
[cron_jobs] --Dispatcher--> [job_executions] --Worker--> [Handler]
```

## Commands

```bash
# 의존성 설치
pip install -r requirements.txt

# 테스트 실행
python -m pytest test/ -v

# 단일 테스트 실행
python -m pytest test/dispatcher_test.py -v
python -m pytest test/worker_test.py::test_function_name -v

# Admin API 서버 (개발)
python -m uvicorn admin.main:app --reload --port 8080

# 개별 모듈 실행
python -m dispatcher.main
python -m worker.main

# 통합 실행 (루트 main.py)
python main.py                    # 전체 실행 (dispatcher + worker + admin)
python main.py dispatcher         # Dispatcher만
python main.py worker             # Worker만
python main.py dispatcher worker  # 복수 선택
```

## Architecture

### 모듈 구조
각 모듈(dispatcher, worker, admin)은 독립적으로 관리. 모듈 간 의존성은 database만 공유.

```
module/
  main.py           # 진입점
  exception.py      # 예외 클래스
  model/            # 입출력 및 엔티티 구조체
  sql/              # aiosql용 .sql 파일
```

### 핵심 컴포넌트

- **database/__init__.py**: 공통 API (`transactional`, `get_connection` 등)
- **database/registry.py**: `DatabaseRegistry`로 다중 DB 관리, `init_from_config(config, db_names)`로 선택적 초기화
- **database/sqlite3/connection.py**: SQLite 비동기 커넥션풀 (aiosqlite)
- **database/postgres/connection.py**: PostgreSQL 비동기 커넥션풀 (asyncpg)
- **database/mysql/connection.py**: MySQL 비동기 커넥션풀 (asyncmy)
- **dispatcher/main.py**: 크론 폴링 및 PENDING Job 생성, `UNIQUE(job_id, scheduled_time)` + `ON CONFLICT DO NOTHING`으로 HA 환경 중복 방지
- **worker/main.py**: WorkerPool, 세마포어 기반 동시 실행 제어
- **worker/base.py**: `@handler` 데코레이터로 핸들러 자동 등록
- **admin/main.py**: FastAPI 기반 Admin API, Jinja2 템플릿

### Worker 핸들러 작성

`worker/job/` 하위에 파일 생성:

```python
from worker.base import BaseHandler, handler

@handler("email")
class EmailHandler(BaseHandler):
    async def execute(self, params: dict):
        # params: cron_jobs.handler_params (JSON)
        return {"sent": True}  # job_executions.result에 저장
```

### 트랜잭션 사용

```python
from database import transactional, transactional_readonly, get_connection

@transactional
async def create_job(job_data):
    ctx = get_connection()
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

### SQL 쿼리 관리

aiosql 사용. SQL 파일은 각 모듈의 `sql/` 폴더에 위치:
- `database/sqlite3/sql/init.sql`: 초기 테이블 생성
- `dispatcher/sql/dispatcher.sql`: Dispatcher 쿼리
- `worker/sql/worker.sql`: Worker 쿼리
- `admin/api/sql/admin.sql`: Admin API 쿼리

**주의**: DB별 Placeholder가 다름
| DB | Placeholder | 예시 |
|----|-------------|------|
| SQLite | `?` | `WHERE id = ?` |
| PostgreSQL | `$1, $2` | `WHERE id = $1` |
| MySQL | `%s` | `WHERE id = %s` |

### 설정 파일

`config/*.yaml`에서 관리:
- `database.yaml`: 다중 DB 커넥션풀 설정 (databases.default, databases.business 등)
- `dispatcher.yaml`: database, 폴링 주기, 크론 간격 제한
- `worker.yaml`: database (job 관리), databases (핸들러용 추가 DB), 워커풀 크기
- `admin.yaml`: database, API 서버 설정

## Conventions

### 네이밍
- 클래스: PascalCase (`EmailHandler`, `WorkerPool`)
- 함수/변수: snake_case (`get_enabled_jobs`, `user_name`)
- 상수: UPPER_SNAKE_CASE (`MAX_WORKERS`)
- 파일: snake_case (`email_handler.py`)

### 코딩 규칙
- 파일 인코딩: UTF-8
- 시간대: DB는 UTC 저장, 표시는 KST(UTC+9) 변환
- 불필요한 함수 생성 금지, 과도한 함수 분리 지양
- 간결한 프로그램 지향
- 코드 및 md 파일에 이모티콘 사용 금지

### Job 상태
| 상태 | 설명 |
|------|------|
| PENDING | 생성됨, 실행 대기 |
| RUNNING | Worker가 실행 중 |
| SUCCESS | 성공 완료 |
| FAILED | 실패 (재시도 포함) |
| TIMEOUT | 타임아웃 |

### 커밋 메시지
```
<type>: <subject>

<body>
```
타입: feat, fix, docs, refactor, test, chore
