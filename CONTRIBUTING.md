# Contributing Guide

JobU 프로젝트 개발 규칙 및 컨벤션 가이드입니다.

## 패키지 구조 원칙

각 모듈(dispatcher, worker, admin)은 독립적으로 관리합니다.
- 모듈 간 의존성은 database만 공유
- 각 모듈은 자체 model/, sql/ 패키지 보유
- 비즈니스 로직, 구조체, SQL 쿼리 분리

```
module/
  main.py           # 진입점
  model/            # 입출력 및 엔티티 구조체
  sql/              # aiosql용 .sql 파일
```

## 네이밍 규칙

### 클래스명: PascalCase
```python
class EmailHandler:
    pass

class WorkerPool:
    pass
```

### 함수명, 변수명: snake_case
```python
def get_enabled_jobs():
    pass

user_name = "test"
job_queue = []
```

### 상수: UPPER_SNAKE_CASE
```python
MAX_WORKERS = 10
DATABASE_PATH = "./jobu.db"
```

### 파일명, 모듈명: snake_case
```
email_handler.py
worker_pool.py
cron_job_mapper.py
```

## 코딩 규칙

### 일반
- 파일 인코딩은 UTF-8
- DB 인코딩은 UTF-8 mb4 권장
- 모든 설정은 config/*.yaml에서 관리
- 코드 및 md 파일에 이모티콘 사용 금지

### 설계 원칙
- 불필요한 함수 생성 금지, 과도한 함수 분리 지양
- 정의된 패키지 구조 외 사용 금지
- 간결한 프로그램 지향, 복잡하게 생각하지 않음

### 트랜잭션
- 기본적으로 handler 단위로 제어
- @transactional, @transactional_readonly 데코레이터 사용

### 에러 처리
- 에러 처리는 공통으로 처리
- 에러 처리와 재시도 로직은 분리

## 시간대(Timezone) 규칙

### 원칙
- DB 저장: UTC 사용 (SQLite CURRENT_TIMESTAMP 기본값)
- 조회/표시: KST(UTC+9)로 변환하여 표시

### 변환 예시
```python
from datetime import timezone, timedelta

KST = timezone(timedelta(hours=9))

# UTC -> KST 변환
created_at_kst = created_at_utc.replace(tzinfo=timezone.utc).astimezone(KST)
```

### 이유
- 글로벌 환경 대비
- 서버 시간대 무관하게 일관된 시간 관리

## 테스트

### 실행
```bash
# 전체 테스트
python -m pytest test/ -v

# 모듈별 테스트
python -m pytest test/sqlite3_test.py -v
python -m pytest test/dispatcher_test.py -v
python -m pytest test/worker_test.py -v
python -m pytest test/admin_test.py -v

# PostgreSQL 테스트 (Docker 필요)
cd docker && docker-compose up -d postgres
python -m pytest test/database/test_postgres.py -v

# MySQL 테스트 (Docker 필요)
cd docker && docker-compose up -d mysql
python -m pytest test/database/test_mysql.py -v
```

### 테스트 파일 위치
```
test/
  sqlite3_test.py           # SQLite DB 테스트
  dispatcher_test.py        # Dispatcher 테스트
  worker_test.py            # Worker 테스트
  admin_test.py             # Admin API 테스트
  database/
    test_postgres.py        # PostgreSQL 테스트
    test_mysql.py           # MySQL 테스트
```

## 커밋 메시지

### 형식
```
<type>: <subject>

<body>
```

### 타입
- feat: 새로운 기능
- fix: 버그 수정
- docs: 문서 변경
- refactor: 리팩토링
- test: 테스트 추가/수정
- chore: 빌드, 설정 변경
