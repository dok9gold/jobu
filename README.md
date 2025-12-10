# jobu (Job Unified)

Python 기반 통합 배치 스케줄링 시스템

> **요구사항:** Python 3.12+

## 개요

RDB에 크론 정보를 저장하고, Dispatcher가 스케줄에 따라 Job을 생성하면 Worker가 실행하는 구조입니다.

```
[cron_jobs] --Dispatcher--> [job_executions] --Worker--> [Handler]
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
| [dispatcher](dispatcher/README.md) | 크론 기반 Job 생성 |
| [worker](worker/README.md) | Job 실행 워커풀 |

**흐름:** Admin에서 크론 등록 -> Dispatcher가 스케줄에 맞춰 Job 생성 -> Worker가 Job 실행

## 구조

```
jobu/
  config/       # 설정 파일
  database/     # DB 커넥션풀 (SQLite, PostgreSQL, MySQL)
  dispatcher/   # Job 생성
  worker/       # Job 실행
  admin/        # 관리 API
  docker/       # Docker 개발 환경
```

## 설치

```bash
# 가상환경 생성 및 활성화
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

## 실행

```bash
# Admin API
python -m uvicorn admin.main:app --reload --port 8080

# Dispatcher
python -m dispatcher.main

# Worker
python -m worker.main

# Docker (PostgreSQL, MySQL 개발환경)
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
