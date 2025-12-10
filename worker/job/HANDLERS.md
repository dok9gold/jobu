# Worker Handlers

## 테스트용

### sample
- 위치: [sample.py](sample.py)
- 용도: 테스트용 핸들러 (sleep, 실패 시뮬레이션)
- params:
  - `sleep_seconds`: 대기 시간 (초)
  - `should_fail`: true면 에러 발생
  - `message`: 결과 메시지

## 샘플 핸들러 (Phase 7)

### sample1
- 위치: [group1/sample1.py](group1/sample1.py)
- DB: sqlite_2 (단일)
- 용도: SQLite CRUD 예제
- params:
  - `action`: "read" (기본) | "write"
  - `name`: 데이터 이름 (write시)
  - `value`: 데이터 값 (write시)

### sample2
- 위치: [group1/sample2.py](group1/sample2.py)
- DB: postgres_1 (단일)
- 용도: PostgreSQL CRUD 예제
- params:
  - `action`: "read" (기본) | "write"
  - `name`: 데이터 이름 (write시)
  - `value`: 데이터 값 (write시)

### sample3
- 위치: [group1/sample3.py](group1/sample3.py)
- DB: sqlite_2, postgres_1 (2개 트랜잭션)
- 용도: SQLite -> PostgreSQL 데이터 동기화
- params: 없음

### sample4
- 위치: [group2/sample4.py](group2/sample4.py)
- DB: mysql_1 (단일)
- 용도: MySQL CRUD 예제
- params:
  - `action`: "read" (기본) | "write"
  - `name`: 데이터 이름 (write시)
  - `value`: 데이터 값 (write시)

### sample5
- 위치: [group2/sample5.py](group2/sample5.py)
- DB: postgres_1, mysql_1 (2개 트랜잭션)
- 용도: PostgreSQL -> MySQL 데이터 동기화
- params: 없음

### sample6
- 위치: [group2/sample6.py](group2/sample6.py)
- DB: sqlite_2, postgres_1, mysql_1 (3개 readonly)
- 용도: 3개 DB 집계 리포트
- params: 없음

## DB 설정

| DB명 | 타입 | 용도 | Docker |
|------|------|------|--------|
| default | SQLite | 시스템 (cron_jobs, job_executions) | X |
| sqlite_2 | SQLite | 샘플 데이터 | X |
| postgres_1 | PostgreSQL | 샘플 데이터 | O |
| mysql_1 | MySQL | 샘플 데이터 | O |
