"""Queue Dispatcher 관련 모델"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class QueueDispatcherConfig:
    """QueueDispatcher 설정"""
    database: str = "default"
    poll_interval_seconds: float = 1.0
    max_retries: int = 3
    retry_delay_seconds: float = 5.0

    # Kafka 설정
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "jobu-queue-dispatcher"
    kafka_topic: str = "jobu-events"
    kafka_auto_offset_reset: str = "earliest"
    kafka_max_poll_records: int = 10


@dataclass
class QueueMessage:
    """큐에서 수신한 메시지"""
    handler_name: str
    params: dict[str, Any] = field(default_factory=dict)
    job_id: int | None = None  # cron_jobs와 연결할 경우

    # 원본 메시지 (ack/nack용)
    raw_message: Any = None
