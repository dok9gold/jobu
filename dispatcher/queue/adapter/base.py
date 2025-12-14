"""Queue Adapter 기본 인터페이스"""
from abc import ABC, abstractmethod
from typing import AsyncIterator, Any

from dispatcher.queue.model.queue import QueueMessage


class BaseQueueAdapter(ABC):
    """
    큐 어댑터 기본 클래스

    Kafka, SQS, Service Bus 등 다양한 큐 시스템을 지원하기 위한
    공통 인터페이스를 정의합니다.
    """

    @abstractmethod
    async def connect(self) -> None:
        """큐 연결"""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """큐 연결 해제"""
        ...

    @abstractmethod
    async def receive(self) -> AsyncIterator[QueueMessage]:
        """
        메시지 수신 (async generator)

        Yields:
            QueueMessage: 수신된 메시지
        """
        ...

    @abstractmethod
    async def complete(self, message: QueueMessage) -> None:
        """
        메시지 처리 완료 (ack)

        Args:
            message: 처리 완료된 메시지
        """
        ...

    @abstractmethod
    async def abandon(self, message: QueueMessage) -> None:
        """
        메시지 처리 실패 (nack, 재시도 대기열로)

        Args:
            message: 처리 실패한 메시지
        """
        ...
