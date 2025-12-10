# Dispatcher 모듈

크론 기반 Job 생성 모듈입니다. cron_jobs 테이블을 폴링하여 실행 시점에 도달한 크론에 대해 PENDING 상태의 Job을 생성합니다.

## 동작 원리

```
[cron_jobs] --폴링--> [Dispatcher] --생성--> [job_executions (PENDING)]
```

1. 설정된 주기(poll_interval)로 활성화된 크론 조회
2. 각 크론의 다음 실행 시점 계산 (croniter)
3. 실행 시점 도달 시 job_executions에 PENDING Job 생성
4. Worker가 PENDING Job을 가져가서 실행

## 구조

```
dispatcher/
  main.py          # Dispatcher 클래스, 메인 루프
  exception.py     # 예외 클래스
  model/
    dispatcher.py  # CronJob, DispatcherConfig
  sql/
    dispatcher.sql # SQL 쿼리
```

## 설정

`config/dispatcher.yaml`

```yaml
dispatcher:
  database: default              # 사용할 DB (database.yaml에 정의된 이름)
  poll_interval_seconds: 60      # 폴링 주기 (초)
  max_sleep_seconds: 300         # 최대 대기 시간 (초)
  min_cron_interval_seconds: 60  # 최소 크론 간격 (1분 미만 차단)
```

## 실행

```bash
python -m dispatcher.main
```

## 사용법

### Job 생성 흐름

1. Admin API로 크론 등록 (`POST /api/crons`)
2. Dispatcher가 poll_interval마다 활성화된 크론 조회
3. 크론 표현식 기반으로 다음 실행 시점 계산
4. 실행 시점 도달 시 job_executions 테이블에 PENDING Job 생성
5. Worker가 PENDING Job을 claim하여 실행

### 주요 기능

#### HA 구성 시 중복 방지
- UNIQUE(job_id, scheduled_time) 제약 조건
- ON CONFLICT DO NOTHING 패턴으로 중복 생성 방지

#### allow_overlap 기능
- allow_overlap=0: 이전 Job이 미완료(PENDING/RUNNING)면 새 Job 생성 스킵
- allow_overlap=1: 항상 새 Job 생성

#### 크론 간격 제한
- 1분 미만 간격 크론 차단 (min_cron_interval_seconds)

## Job 상태

| 상태 | 설명 |
|------|------|
| PENDING | 생성됨, 실행 대기 |
| RUNNING | Worker가 실행 중 |
| SUCCESS | 성공 완료 |
| FAILED | 실패 (재시도 포함) |
| TIMEOUT | 타임아웃 |

## 예외

| 예외 | 설명 |
|------|------|
| CronParseError | 크론 표현식 파싱 실패 |
| CronIntervalTooShortError | 1분 미만 간격 크론 |
| JobCreationError | Job 생성 실패 |

## 테스트

```bash
python -m pytest test/dispatcher_test.py -v
```
