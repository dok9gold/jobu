# Dispatcher 모듈

Job 생성 모듈입니다. 두 가지 방식으로 Job을 생성할 수 있습니다:

- **Cron Dispatcher**: 크론 스케줄 기반 Job 생성
- **Queue Dispatcher**: 외부 큐(Kafka 등) 이벤트 기반 Job 생성

## 동작 원리

```
[cron_jobs] --폴링--> [Cron Dispatcher] --생성--> [job_executions (PENDING)]

[Kafka] --consume--> [Queue Dispatcher] --생성--> [job_executions (PENDING)]
                                                          |
                                                          v
                                                    [Worker 실행]
```

## 구조

```
dispatcher/
  __init__.py              # re-export (기존 호환성 유지)
  cron/                    # Cron 기반 Dispatcher
    main.py                # Dispatcher 클래스
    exception.py           # 예외 클래스
    model/
      dispatcher.py        # CronJob, DispatcherConfig
    sql/
      dispatcher.sql       # SQL 쿼리
  queue/                   # Queue 기반 Dispatcher
    main.py                # QueueDispatcher 클래스
    exception.py           # 예외 클래스
    adapter/
      base.py              # BaseQueueAdapter 인터페이스
      kafka.py             # KafkaAdapter 구현
    model/
      queue.py             # QueueMessage, QueueDispatcherConfig
    sql/
      queue_dispatcher.sql # SQL 쿼리
```

## Cron Dispatcher

크론 표현식 기반으로 정해진 시간에 Job을 생성합니다.

### 설정

`config/dispatcher.yaml`

```yaml
dispatcher:
  database: default              # 사용할 DB
  poll_interval_seconds: 60      # 폴링 주기 (초)
  max_sleep_seconds: 300         # 최대 대기 시간 (초)
  min_cron_interval_seconds: 60  # 최소 크론 간격 (1분 미만 차단)
```

### 실행

```bash
python -m dispatcher.cron.main
python main.py dispatcher
```

### 주요 기능

- HA 구성 시 중복 방지: `UNIQUE(job_id, scheduled_time)` + `ON CONFLICT DO NOTHING`
- allow_overlap: 이전 Job 미완료 시 새 Job 생성 스킵 옵션
- 크론 간격 제한: 1분 미만 간격 차단

## Queue Dispatcher

외부 큐에서 메시지를 수신하여 Job을 생성합니다.

### 설정

`config/queue.yaml`

```yaml
queue_dispatcher:
  database: default
  kafka_bootstrap_servers: localhost:9092
  kafka_group_id: jobu-queue-dispatcher
  kafka_topic: jobu-events
```

### 실행

```bash
python -m dispatcher.queue.main
python main.py queue_dispatcher
```

### 메시지 포맷

```json
{
  "handler_name": "my_handler",
  "params": {"key": "value"},
  "job_id": 123
}
```

- `handler_name` (필수): 실행할 핸들러 이름
- `params` (선택): 핸들러에 전달할 파라미터
- `job_id` (선택): cron_jobs와 연결할 경우

### 어댑터 확장

`BaseQueueAdapter`를 구현하여 다른 큐 시스템 지원 가능:

```python
from dispatcher.queue.adapter.base import BaseQueueAdapter

class SQSAdapter(BaseQueueAdapter):
    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def receive(self) -> AsyncIterator[QueueMessage]: ...
    async def complete(self, message: QueueMessage) -> None: ...
    async def abandon(self, message: QueueMessage) -> None: ...
```

## Job 상태

| 상태 | 설명 |
|------|------|
| PENDING | 생성됨, 실행 대기 |
| RUNNING | Worker가 실행 중 |
| SUCCESS | 성공 완료 |
| FAILED | 실패 (재시도 포함) |
| TIMEOUT | 타임아웃 |

## param_source

Job 생성 출처를 구분합니다:

| 값 | 설명 |
|----|------|
| cron | Cron Dispatcher가 생성 |
| event | Queue Dispatcher가 생성 |
