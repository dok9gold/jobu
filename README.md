# jobu (Job Unified)

Python 기반 통합 배치 스케줄링 시스템

> **요구사항:** Python 3.12+

## 개요

RDB에 크론 정보를 저장하고, Dispatcher가 스케줄에 따라 Job을 생성하면 Worker가 실행하는 구조입니다.
Kafka 등 메시지 큐를 통한 이벤트 기반 Job 실행도 지원합니다.

```
[cron_jobs] --Cron Dispatcher--> [job_executions] --Worker--> [Handler]
[Kafka]     --Queue Dispatcher-->
```

## 특징

- Dispatcher/Worker 분리로 HA 구성 용이
- 다중 DB 지원 (SQLite, PostgreSQL, MySQL)
- 다중 DB 트랜잭션 지원 (`@transactional(db1, db2)`)
- 비즈니스 로직과 model/sql 분리
- aiosql 기반 SQL 쿼리 관리
- 비동기 커넥션풀 지원
- Admin API로 크론/잡 관리

## 모듈

| 모듈 | 설명 |
|------|------|
| [admin](admin/README.md) | 관리 API 및 모니터링 화면 |
| [database](database/README.md) | DB 커넥션풀, 트랜잭션 관리 |
| [dispatcher](dispatcher/README.md) | Job 생성 (Cron/Queue) |
| [worker](worker/README.md) | Job 실행 워커풀 |

**흐름:**
- **Cron:** Admin에서 크론 등록 -> Cron Dispatcher가 스케줄에 맞춰 Job 생성 -> Worker가 Job 실행
- **Event:** Kafka 메시지 수신 -> Queue Dispatcher가 Job 생성 -> Worker가 Job 실행

## 구조

```
jobu/
  config/       # 설정 파일
  database/     # DB 커넥션풀 (SQLite, PostgreSQL, MySQL)
  dispatcher/   # Job 생성
    cron/       # 크론 기반 Job 생성
    queue/      # 메시지 큐 기반 Job 생성 (Kafka)
  worker/       # Job 실행
  admin/        # 관리 API
  docker/       # Docker 개발 환경 (PostgreSQL, MySQL, Kafka)
```

## 설치

```bash
pip install jobu
```

## 빠른 시작

```bash
# 새 프로젝트 생성
jobu init myproject
cd myproject

# 가상환경 설정
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 실행
python main.py
```

### 템플릿 옵션

```bash
jobu init myproject                     # 기본 (main 브랜치)
jobu init myproject --template sample   # sample 브랜치
```

## 개발 환경 설치

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### Windows 인코딩 설정

Windows에서 한글 경로 문제로 인코딩 에러 발생 시:

```powershell
# PowerShell
$env:PYTHONUTF8=1

# CMD
set PYTHONUTF8=1
```

영구 설정: 시스템 환경변수에 `PYTHONUTF8=1` 추가

## 실행

```bash
# 전체 실행 (Cron Dispatcher + Worker + Admin)
python main.py

# 개별 실행
python main.py dispatcher          # Cron Dispatcher
python main.py queue_dispatcher    # Queue Dispatcher (Kafka)
python main.py worker              # Worker
python main.py admin               # Admin API

# 모듈 직접 실행
python -m uvicorn admin.main:app --reload --port 8080

# Docker (PostgreSQL, MySQL, Kafka 개발환경)
cd docker && docker-compose up -d
```

## 관리자 페이지

| URL | 설명 |
|-----|------|
| http://localhost:8080/docs | API 문서 (Swagger) |
| http://localhost:8080/crons | 크론 관리 화면 |
| http://localhost:8080/jobs | 잡 이력 화면 |

## 개발 가이드

- [CONTRIBUTING.md](CONTRIBUTING.md) - 네이밍 규칙, 개발 규칙, 시간대 규칙
- [PRODUCTION.md](PRODUCTION.md) - 운영 환경 배포 및 설정 가이드
