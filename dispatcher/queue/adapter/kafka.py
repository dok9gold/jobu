"""Kafka Queue Adapter"""
import json
import logging
from typing import AsyncIterator

from dispatcher.queue.adapter.base import BaseQueueAdapter
from dispatcher.queue.model.queue import QueueMessage, QueueDispatcherConfig

logger = logging.getLogger(__name__)


class KafkaAdapter(BaseQueueAdapter):
    """
    Kafka 큐 어댑터

    aiokafka를 사용하여 비동기 Kafka consumer를 제공합니다.
    """

    def __init__(self, config: QueueDispatcherConfig):
        self._config = config
        self._consumer = None

    async def connect(self) -> None:
        """Kafka consumer 연결"""
        try:
            from aiokafka import AIOKafkaConsumer
        except ImportError:
            raise ImportError(
                "aiokafka is required for Kafka support. "
                "Install it with: pip install aiokafka"
            )

        self._consumer = AIOKafkaConsumer(
            self._config.kafka_topic,
            bootstrap_servers=self._config.kafka_bootstrap_servers,
            group_id=self._config.kafka_group_id,
            auto_offset_reset=self._config.kafka_auto_offset_reset,
            enable_auto_commit=False,
            max_poll_records=self._config.kafka_max_poll_records,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        )
        await self._consumer.start()
        logger.info(
            f"Kafka consumer connected: topic={self._config.kafka_topic}, "
            f"group_id={self._config.kafka_group_id}"
        )

    async def disconnect(self) -> None:
        """Kafka consumer 연결 해제"""
        if self._consumer:
            await self._consumer.stop()
            logger.info("Kafka consumer disconnected")

    async def receive(self) -> AsyncIterator[QueueMessage]:
        """
        메시지 수신

        메시지 포맷 (JSON):
        {
            "handler_name": "my_handler",
            "params": {"key": "value"},
            "job_id": 123  // optional
        }
        """
        if not self._consumer:
            raise RuntimeError("Kafka consumer not connected")

        async for msg in self._consumer:
            try:
                data = msg.value
                queue_message = QueueMessage(
                    handler_name=data.get("handler_name") or data.get("handler"),
                    params=data.get("params", {}),
                    job_id=data.get("job_id"),
                    raw_message=msg,
                )
                logger.debug(
                    f"Received message: handler={queue_message.handler_name}, "
                    f"partition={msg.partition}, offset={msg.offset}"
                )
                yield queue_message
            except Exception as e:
                logger.error(f"Failed to parse message: {e}, raw={msg.value}")
                # 파싱 실패한 메시지는 커밋하고 넘어감
                await self._consumer.commit()

    async def complete(self, message: QueueMessage) -> None:
        """메시지 처리 완료 (커밋)"""
        if self._consumer and message.raw_message:
            await self._consumer.commit()
            logger.debug(
                f"Message committed: offset={message.raw_message.offset}"
            )

    async def abandon(self, message: QueueMessage) -> None:
        """
        메시지 처리 실패

        Kafka는 기본적으로 재시도를 위한 별도 메커니즘이 없으므로
        로그만 남기고 커밋함. DLQ가 필요하면 별도 토픽으로 전송 필요.
        """
        logger.warning(
            f"Message abandoned: handler={message.handler_name}, "
            f"offset={message.raw_message.offset if message.raw_message else 'N/A'}"
        )
        if self._consumer:
            await self._consumer.commit()
