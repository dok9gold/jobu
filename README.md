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
| sample1 | */1 * * * * | 1분마다 실행 |
| sample2 | */2 * * * * | 2분마다 실행 |
| sample3 | */3 * * * * | 3분마다 실행 |
| sample4 | */1 * * * * | MySQL 예제 |
| sample5 | */2 * * * * | MySQL 예제 |
| sample6 | */3 * * * * | MySQL 예제 |
| sample7 | */1 * * * * | SQLite 예제 |
| sample8 | */2 * * * * | SQLite 예제 |
| sample9 | */3 * * * * | SQLite 예제 |

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
  sample.py           # 단일 파일 핸들러
  group1/             # PostgreSQL 예제
    sample1.py
    sample2.py
    sample3.py
  group2/             # MySQL 예제
    sample4.py
    sample5.py
    sample6.py
  group3/             # SQLite 예제
    sample7.py
    sample8.py
    sample9.py
```

## 더 알아보기

- [worker/job/HANDLERS.md](worker/job/HANDLERS.md) - 핸들러 작성 가이드
- [CONTRIBUTING.md](CONTRIBUTING.md) - 개발 규칙
- [PRODUCTION.md](PRODUCTION.md) - 운영 환경 가이드
