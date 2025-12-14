"""
QueueDispatcher: 큐 기반 Job 생성 모듈

외부 큐(Kafka, SQS, Service Bus 등)에서 메시지를 수신하여
job_executions 테이블에 PENDING 상태의 Job을 생성합니다.

실행 방법:
    python -m dispatcher.queue.main
    python main.py queue_dispatcher
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosql

from database import (
    transactional,
    transactional_readonly,
    get_connection,
    get_aiosql_adapter_for_db,
    ConnectionPoolExhaustedError,
    TransactionError,
    QueryExecutionError,
)
from database.registry import DatabaseRegistry
from dispatcher.queue.model.queue import QueueDispatcherConfig, QueueMessage
from dispatcher.queue.adapter.base import BaseQueueAdapter
from dispatcher.queue.adapter.kafka import KafkaAdapter
from dispatcher.queue.exception import (
    QueueConnectionError,
    HandlerNotFoundError,
    ExecutionCreationError,
)

logger = logging.getLogger(__name__)


class QueueDispatcher:
    """
    큐 기반 Job Dispatcher

    외부 큐에서 메시지를 수신하여 job_executions 테이블에
    PENDING 상태의 Job을 생성합니다.

    파라미터 머지:
    - cron_jobs.handler_params (base) + event_params (message) 머지
    - 충돌 시 event_params가 우선
    """

    def __init__(self, config: QueueDispatcherConfig, adapter: BaseQueueAdapter | None = None):
        """
        Args:
            config: QueueDispatcher 설정
            adapter: 큐 어댑터 (미지정 시 KafkaAdapter 사용)
        """
        self._config = config
        self._adapter = adapter or KafkaAdapter(config)
        self._running = False
        self._stop_event: asyncio.Event | None = None
        self._queries: Any | None = None

    async def start(self) -> None:
        """QueueDispatcher 메인 루프 시작"""
        if self._running:
            logger.warning("QueueDispatcher is already running")
            return

        self._running = True
        self._stop_event = asyncio.Event()

        # SQL 쿼리 로드 (등록된 DB 타입에 맞는 어댑터 자동 선택)
        sql_path = Path(__file__).parent / "sql" / "queue_dispatcher.sql"
        adapter = get_aiosql_adapter_for_db(self._config.database)
        self._queries = aiosql.from_path(str(sql_path), adapter)

        # 큐 연결
        try:
            await self._adapter.connect()
        except Exception as e:
            self._running = False
            raise QueueConnectionError(f"Failed to connect to queue: {e}")

        logger.info("QueueDispatcher started")

        try:
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("QueueDispatcher cancelled")
        except Exception as e:
            logger.error(f"QueueDispatcher error: {e}", exc_info=True)
            raise
        finally:
            await self._adapter.disconnect()
            self._running = False
            logger.info("QueueDispatcher stopped")

    async def stop(self) -> None:
        """QueueDispatcher graceful shutdown"""
        if not self._running:
            return

        logger.info("Stopping QueueDispatcher...")
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        # Kafka consumer 강제 종료 (async for 루프 탈출)
        await self._adapter.disconnect()

    async def _main_loop(self) -> None:
        """메인 루프: 큐 메시지 수신 및 Job 생성"""
        async for message in self._adapter.receive():
            if not self._running:
                break

            try:
                await self._process_message(message)
                await self._adapter.complete(message)
            except Exception as e:
                logger.error(
                    f"Failed to process message: {e}, handler={message.handler_name}",
                    exc_info=True
                )
                await self._adapter.abandon(message)

    async def _process_message(self, message: QueueMessage) -> None:
        """
        메시지 처리

        1. handler_name으로 cron_jobs 조회 (base params)
        2. base_params + event_params 머지
        3. job_executions 생성
        """
        logger.debug(f"Processing message: handler={message.handler_name}")

        # base params 조회 (optional - cron_jobs에 등록된 경우)
        base_params = {}
        job_id = message.job_id

        if not job_id:
            job = await self._get_job_by_handler(message.handler_name)
            if job:
                job_id = job["id"]
                base_params = job["handler_params"] or {}

        # 파라미터 머지 (base + event, event 우선)
        final_params = {**base_params, **message.params}

        # job_executions 생성
        execution_id = await self._create_event_execution(
            job_id=job_id,
            handler_name=message.handler_name,
            params=final_params,
        )

        logger.info(
            f"Created event execution: id={execution_id}, "
            f"handler={message.handler_name}, job_id={job_id}"
        )

    @transactional_readonly
    async def _get_job_by_handler(self, handler_name: str) -> dict | None:
        """handler_name으로 cron_job 조회"""
        ctx = get_connection()
        row = await self._queries.get_job_by_handler_name(
            ctx.connection,
            handler_name=handler_name,
        )
        if row:
            return dict(row)
        return None

    @transactional
    async def _create_event_execution(
        self,
        job_id: int | None,
        handler_name: str,
        params: dict,
    ) -> int:
        """이벤트 기반 실행 레코드 생성"""
        try:
            ctx = get_connection()
            scheduled_time = datetime.utcnow()
            params_json = json.dumps(params) if params else None

            # aiosql $는 RETURNING으로 스칼라 값 반환
            execution_id = await self._queries.create_event_execution(
                ctx.connection,
                job_id=job_id,
                handler_name=handler_name,
                scheduled_time=scheduled_time,
                params=params_json,
            )
            return execution_id

        except Exception as e:
            raise ExecutionCreationError(handler_name, str(e))

    @property
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._running


if __name__ == "__main__":
    import signal
    import yaml

    async def main():
        # 설정 로드 (프로젝트 루트 기준)
        config_path = Path(__file__).parent.parent.parent / "config"

        # 데이터베이스 설정
        with open(config_path / "database.yaml", encoding="utf-8") as f:
            db_config = yaml.safe_load(f)

        # QueueDispatcher 설정
        queue_config_path = config_path / "queue.yaml"
        if queue_config_path.exists():
            with open(queue_config_path, encoding="utf-8") as f:
                queue_config_data = yaml.safe_load(f)
        else:
            queue_config_data = {}

        # 로깅 설정
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # QueueDispatcher 설정
        config = QueueDispatcherConfig(**queue_config_data.get("queue_dispatcher", {}))

        # 데이터베이스 초기화
        await DatabaseRegistry.init_from_config(db_config, [config.database])

        # QueueDispatcher 인스턴스 생성
        dispatcher = QueueDispatcher(config)

        # Graceful Shutdown 시그널 핸들러
        loop = asyncio.get_running_loop()

        def signal_handler():
            logger.info("Received shutdown signal")
            asyncio.create_task(dispatcher.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            logger.info("Starting QueueDispatcher...")
            await dispatcher.start()
        finally:
            await DatabaseRegistry.close_all()

    asyncio.run(main())
