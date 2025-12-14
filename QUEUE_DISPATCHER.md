# QueueDispatcher 구현 완료

## 변경 사항 요약

### 1. Dispatcher 모듈 리팩토링

```
dispatcher/
  __init__.py           # re-export (기존 호환성 유지)
  cron/                 # 기존 Cron Dispatcher
    main.py
    model/
    sql/
    exception.py
  queue/                # 신규 Queue Dispatcher
    main.py
    adapter/
      base.py           # BaseQueueAdapter 인터페이스
      kafka.py          # KafkaAdapter 구현
    model/
    sql/
    exception.py
```

### 2. 스키마 변경 (job_executions 테이블)

```sql
-- 추가된 컬럼
handler_name VARCHAR(255) NOT NULL  -- 핸들러 이름 (event 실행용)
params JSONB                        -- 실행 시점 파라미터 스냅샷
param_source VARCHAR(20)            -- 'cron' / 'event'

-- 변경된 컬럼
job_id INTEGER                      -- NOT NULL -> nullable (event는 job_id 없이 실행 가능)
```

### 3. Docker Compose (Kafka 추가)

```yaml
# docker/docker-compose.yaml
services:
  postgres:    # 기존
  mysql:       # 기존
  zookeeper:   # 신규
  kafka:       # 신규
```

### 4. 전처리 파이프라인 핸들러

```
worker/job/pipeline/
  pandas_preprocess.py   # CSV -> Parquet 전처리
  pydantic_validator.py  # 데이터 검증
  db_loader.py           # PostgreSQL COPY 적재
```

---

## 파라미터 처리 흐름

### Cron 실행 (기존)
```
cron_jobs.handler_params -> job_executions.params
param_source: "cron"
```

### Event 실행 (신규)
```
cron_jobs.handler_params (base) + event_params (message) -> 머지 -> job_executions.params
param_source: "event"
충돌 시 event_params가 우선
```

---

## 사용법

### 기본 실행 (Cron Dispatcher + Worker + Admin)

```bash
python main.py
```

### 개별 컴포넌트 실행

```bash
python main.py dispatcher           # Cron Dispatcher만
python main.py queue_dispatcher     # Queue Dispatcher만
python main.py worker               # Worker만
python main.py admin                # Admin API만
python main.py dispatcher worker    # 복수 선택
```

### Queue Dispatcher 실행 (Kafka 필요)

```bash
# 1. Docker 환경 시작
cd docker && docker-compose up -d

# 2. Queue Dispatcher + Worker 실행
python main.py queue_dispatcher worker
```

---

## Docker Compose 사용법

### 전체 서비스 시작

```bash
cd docker
docker-compose up -d
```

### 개별 서비스 시작

```bash
# PostgreSQL만
docker-compose up -d postgres

# Kafka만 (Zookeeper 자동 시작)
docker-compose up -d kafka
```

### 서비스 확인

```bash
docker-compose ps
```

### 로그 확인

```bash
docker-compose logs -f kafka
docker-compose logs -f postgres
```

### 종료

```bash
docker-compose down

# 볼륨까지 삭제
docker-compose down -v
```

### 포트 정보

| 서비스 | 포트 |
|--------|------|
| PostgreSQL | 5432 |
| MySQL | 3306 |
| Kafka | 9092 (host), 29092 (container) |
| Zookeeper | 2181 |

---

## Kafka 메시지 포맷

```json
{
    "handler_name": "pandas_preprocess",
    "params": {
        "input_path": "/data/raw/sample.csv",
        "output_path": "/data/processed/sample.parquet"
    },
    "job_id": null
}
```

### 테스트 메시지 전송 (kafkacat)

```bash
echo '{"handler_name": "sample_handler", "params": {"key": "value"}}' | \
  kafkacat -P -b localhost:9092 -t jobu-events
```

---

## 설정 파일

### config/queue.yaml

```yaml
queue_dispatcher:
  database: default
  kafka_bootstrap_servers: localhost:9092
  kafka_group_id: jobu-queue-dispatcher
  kafka_topic: jobu-events
  kafka_auto_offset_reset: earliest
  kafka_max_poll_records: 10
```

---

## 아키텍처

```
[cron_jobs] --> [Cron Dispatcher] --> [job_executions] --> [Worker] --> [Handler]
                                       (param_source: "cron")

[Kafka] --> [Queue Dispatcher] --> [job_executions] --> [Worker] --> [Handler]
                                    (param_source: "event")
```
