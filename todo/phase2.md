# Dispatcher 구현 및 테스트

## 데이터 베이스 정보
- cron_jobs 테이블: 크론정보를 관리하는 테이블
    ```
    CREATE TABLE IF NOT EXISTS cron_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT,
        cron_expression TEXT NOT NULL,
        handler_name TEXT NOT NULL,
        handler_params TEXT,
        is_enabled INTEGER DEFAULT 1,
        max_retry INTEGER DEFAULT 3,
        timeout_seconds INTEGER DEFAULT 3600,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    ```

- job_executions 테이블: 잡을 생성하고 관리하는 테이블
    ```sql
    CREATE TABLE IF NOT EXISTS job_executions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_id INTEGER NOT NULL,
        scheduled_time TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        started_at TEXT,
        finished_at TEXT,
        retry_count INTEGER DEFAULT 0,
        error_message TEXT,
        result TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (job_id) REFERENCES cron_jobs(id) ON DELETE CASCADE,
        UNIQUE(job_id, scheduled_time)
    );
    ```

## 구조
- 패키지: dispatcher
- 구현 프로그램: dispatcher/dispatcher.py
- sql: dispatcher/sql/dispatcher.sql (aiosql 사용)
- model: dispatcher/model/dispatcher.py
- 설정 파일: config/dispatcher.yaml
    ```yaml
    dispatcher:
      poll_interval_seconds: 60      # 크론 테이블 polling 간격
      max_sleep_seconds: 300         # 최대 sleep 시간 (5분)
      min_cron_interval_seconds: 60  # 최소 크론 실행 간격 (초단위 크론 차단)
    ```

## 라이브러리
- croniter: 크론 표현식 파싱 및 다음 실행 시간 계산

## 구현
1. 지속적으로 cron_jobs 테이블에서 크론정보를 읽음 (polling)
    - poll_interval_seconds 간격으로 테이블 조회
    - 다음 실행까지 sleep하되, max_sleep_seconds(5분)를 넘지 않음
2. 작동해야하는 크론일 경우 job_executions 테이블에 job을 생성함
    - croniter로 현재 시간 기준 실행해야 할 크론인지 판단
    - job의 상태값은 생성시 PENDING
      - job 상태값
        - PENDING = "PENDING"
        - RUNNING = "RUNNING"
        - SUCCESS = "SUCCESS"
        - FAILED = "FAILED"
        - TIMEOUT = "TIMEOUT"
    - 중복 생성 방지: `UNIQUE(job_id, scheduled_time)` 제약 + `ON CONFLICT DO NOTHING` 패턴
    - 초단위 크론 차단: min_cron_interval_seconds(60초) 미만 간격 크론은 생성 시 validation 에러

## 테스트
- 정상 케이스
  - 크론 시간 도달 시 Job이 PENDING 상태로 생성됨
  - scheduled_time이 정확히 기록됨
- 중복 방지
  - 동일 job_id + scheduled_time 조합으로 중복 생성 시도 시 무시됨
  - 다중 Dispatcher 인스턴스에서 동시 생성 시도해도 1개만 생성
- 비활성화 크론
  - is_enabled=0인 크론은 Job 생성 안됨
- 초단위 크론 차단
  - 1분 미만 간격 크론 등록 시 validation 에러
- 에러 격리
  - 특정 크론 파싱 에러 시 다른 크론은 정상 동작
  - DB 일시 장애 후 복구 시 Dispatcher 정상 재개

## 고려사항
- HA 구성시 중복되지 않게 구현 되어야 함
  - DB 중심 설계로 HA 해결 (DB를 Single Source of Truth로 사용)
  - `UNIQUE(job_id, scheduled_time)` 제약으로 Dispatcher 중복 생성 방지
  - Job 생성 시: `INSERT ... WHERE NOT EXISTS` 또는 `ON CONFLICT DO NOTHING` 패턴 사용
  - Job 실행 시 (Phase5): `UPDATE ... WHERE status = 'PENDING' RETURNING id` 패턴으로 Worker 중복 실행 방지
  - PostgreSQL 사용 시 트랜잭션 격리 수준으로 완벽한 동시성 제어 가능

## 에러 처리 방향
- Dispatcher는 상위 레이어로서 하위 패키지(database 등)에서 발생한 예외를 처리
- 주요 처리 전략
  - ConnectionPoolExhaustedError: 로깅 후 일정 시간 대기 후 재시도
  - TransactionError: 로깅 후 해당 크론 스킵, 다음 주기에 재시도
  - QueryExecutionError: 로깅 후 해당 크론 스킵
- Dispatcher 자체 예외
  - CronParseError: 크론 표현식 파싱 실패 시 해당 크론 비활성화 검토
  - JobCreationError: Job 생성 실패 시 로깅 후 다음 주기에 재시도
- 에러 발생 시에도 Dispatcher는 중단되지 않고 계속 실행되어야 함 (장애 격리)

## phase2 이후
- phase3에서는 데이터 베이스 관리 admin을 생성 예정
- phase4에서는 worker pool을 생성 예정
- phase5에서는 dispatcher와 worker pool을 연동 예정