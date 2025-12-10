# jobu - Example Template

샘플 핸들러가 포함된 jobu 예제 템플릿입니다.

> **요구사항:** Python 3.12+, Docker

## 빠른 시작

### 1. 프로젝트 생성

```bash
pip install jobu
jobu init myproject --template template/example
cd myproject
```

### 2. Docker로 DB 실행

```bash
cd docker
docker-compose up -d
```

PostgreSQL(5432)과 MySQL(3306)이 실행됩니다.

### 3. 가상환경 설정 및 의존성 설치

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 실행

```bash
python main.py
```

Admin, Dispatcher, Worker가 모두 실행됩니다.

### 5. 샘플 크론 등록

http://localhost:8080/crons 접속 후 샘플 핸들러 등록:

| handler_name | cron_expr | 설명 |
|--------------|-----------|------|
| sqlite_crud | */1 * * * * | SQLite CRUD (Docker 불필요) |
| postgres_crud | */2 * * * * | PostgreSQL CRUD |
| mysql_crud | */3 * * * * | MySQL CRUD |
| sync_sqlite_to_postgres | */5 * * * * | SQLite -> PostgreSQL 동기화 |
| sync_postgres_to_mysql | */5 * * * * | PostgreSQL -> MySQL 동기화 |
| multi_db_report | */10 * * * * | 3개 DB 집계 리포트 |
| service_layer | */1 * * * * | 서비스 레이어 패턴 |
| do_work_pattern | */2 * * * * | do_work 패턴 |
| concurrent_queries | */3 * * * * | 비동기 병렬 쿼리 |

### 6. 실행 확인

http://localhost:8080/jobs 에서 Job 실행 이력을 확인할 수 있습니다.

## 관리자 페이지

| URL | 설명 |
|-----|------|
| http://localhost:8080/docs | API 문서 (Swagger) |
| http://localhost:8080/crons | 크론 관리 화면 |
| http://localhost:8080/jobs | 잡 이력 화면 |

## 샘플 핸들러 구조

```
worker/job/
  basic/                # 단일 DB CRUD 예제
    sqlite_crud.py      # SQLite (Docker 불필요)
    postgres_crud.py    # PostgreSQL
    mysql_crud.py       # MySQL
  multi_db/             # 멀티 DB 트랜잭션 예제
    sync_sqlite_to_postgres.py
    sync_postgres_to_mysql.py
    multi_db_report.py
  patterns/             # 코드 구조 패턴
    service_layer.py    # Spring MVC 스타일
    do_work_pattern.py  # 심플 패턴
  async_patterns/       # 비동기 고급 패턴
    concurrent_queries.py
```

## 더 알아보기

- [worker/job/README.md](worker/job/README.md) - 핸들러 개발 가이드
- [CONTRIBUTING.md](CONTRIBUTING.md) - 개발 규칙
- [PRODUCTION.md](PRODUCTION.md) - 운영 환경 가이드
