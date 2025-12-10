"""
Dispatcher: 크론 기반 Job 생성 모듈

cron_jobs 테이블을 주기적으로 폴링하여 실행 시점에 도달한 크론에 대해
job_executions 테이블에 PENDING 상태의 Job을 생성합니다.

실행 방법:
    python -m dispatcher.main
    python main.py dispatcher
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosql
from croniter import croniter

from database import (
    transactional,
    transactional_readonly,
    get_connection,
    ConnectionPoolExhaustedError,
    TransactionError,
    QueryExecutionError,
)
from database.registry import DatabaseRegistry
from dispatcher.model.dispatcher import CronJob, DispatcherConfig
from dispatcher.exception import (
    CronParseError,
    CronIntervalTooShortError,
    JobCreationError,
)

logger = logging.getLogger(__name__)


class Dispatcher:
    """
    크론 기반 Job Dispatcher

    활성화된 크론을 주기적으로 폴링하여 실행 시점에 도달하면
    job_executions 테이블에 PENDING 상태의 Job을 생성합니다.

    HA 구성 시 중복 생성 방지:
    - UNIQUE(job_id, scheduled_time) 제약
    - ON CONFLICT DO NOTHING 패턴 사용
    """

    def __init__(self, config: DispatcherConfig):
        """
        Args:
            config: Dispatcher 설정
        """
        self._config = config
        self._running = False
        self._stop_event: asyncio.Event | None = None
        self._queries: Any | None = None
        self._last_poll_time: datetime | None = None

    async def start(self) -> None:
        """Dispatcher 메인 루프 시작"""
        if self._running:
            logger.warning("Dispatcher is already running")
            return

        self._running = True
        self._stop_event = asyncio.Event()

        # SQL 쿼리 로드
        sql_path = Path(__file__).parent / "sql" / "dispatcher.sql"
        self._queries = aiosql.from_path(str(sql_path), "aiosqlite")

        logger.info(
            f"Dispatcher started (poll_interval={self._config.poll_interval_seconds}s, "
            f"max_sleep={self._config.max_sleep_seconds}s)"
        )

        try:
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("Dispatcher cancelled")
        except Exception as e:
            logger.error(f"Dispatcher error: {e}", exc_info=True)
            raise
        finally:
            self._running = False
            logger.info("Dispatcher stopped")

    async def stop(self) -> None:
        """Dispatcher graceful shutdown"""
        if not self._running:
            return

        logger.info("Stopping dispatcher...")
        self._running = False
        if self._stop_event:
            self._stop_event.set()

    async def _main_loop(self) -> None:
        """메인 루프: 크론 폴링 및 Job 생성"""
        while self._running:
            try:
                # 활성화된 크론 목록 조회
                jobs = await self._poll_cron_jobs()
                logger.debug(f"Polled {len(jobs)} jobs")

                if jobs:
                    # 각 크론 처리
                    for job in jobs:
                        await self._process_cron_job(job)

                    # 다음 실행까지 대기 시간 계산
                    sleep_seconds = self._calculate_next_sleep(jobs)
                else:
                    # 크론이 없으면 poll_interval만큼 대기
                    sleep_seconds = self._config.poll_interval_seconds

                # 대기
                await self._sleep(sleep_seconds)

            except ConnectionPoolExhaustedError as e:
                logger.warning(f"Connection pool exhausted: {e}. Retrying in 10s...")
                await self._sleep(10)

            except (TransactionError, QueryExecutionError) as e:
                logger.error(f"Database error: {e}. Continuing...")
                await self._sleep(self._config.poll_interval_seconds)

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                await self._sleep(self._config.poll_interval_seconds)

    async def _sleep(self, seconds: float) -> None:
        """인터럽트 가능한 sleep"""
        if self._stop_event:
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=seconds
                )
            except asyncio.TimeoutError:
                pass

    @transactional_readonly
    async def _poll_cron_jobs(self) -> list[CronJob]:
        """활성화된 크론 목록 조회"""
        ctx = get_connection()
        rows = await self._queries.get_enabled_jobs(ctx.connection)

        jobs = []
        for row in rows:
            try:
                job = CronJob(
                    id=row["id"],
                    name=row["name"],
                    description=row["description"],
                    cron_expression=row["cron_expression"],
                    handler_name=row["handler_name"],
                    handler_params=row["handler_params"],
                    is_enabled=bool(row["is_enabled"]),
                    allow_overlap=bool(row["allow_overlap"]),
                    max_retry=row["max_retry"],
                    timeout_seconds=row["timeout_seconds"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to parse cron job row: {e}")
                continue

        self._last_poll_time = datetime.now(timezone.utc)
        logger.debug(f"Polled {len(jobs)} enabled cron jobs")
        return jobs

    async def _process_cron_job(self, job: CronJob) -> None:
        """
        개별 크론 처리

        실행 시점에 도달했는지 확인하고, 도달했다면 Job 생성
        """
        try:
            # 크론 간격 검증
            self._validate_cron_interval(job.cron_expression)

            # 실행 여부 및 예정 시간 확인
            should_run, scheduled_time = self._should_run(job, datetime.now(timezone.utc))

            if should_run and scheduled_time:
                # allow_overlap=False인 경우 미완료 Job 체크
                if not job.allow_overlap:
                    has_incomplete = await self._has_incomplete_execution(job.id)
                    if has_incomplete:
                        logger.debug(
                            f"Skipping job creation (allow_overlap=False, incomplete job exists): "
                            f"job_id={job.id}, name={job.name}"
                        )
                        return

                # Job 생성
                created = await self._create_job_execution(job, scheduled_time)
                if created:
                    logger.info(
                        f"Created job execution: job_id={job.id}, "
                        f"name={job.name}, scheduled_time={scheduled_time.isoformat()}"
                    )
                else:
                    logger.debug(
                        f"Job execution already exists: job_id={job.id}, "
                        f"scheduled_time={scheduled_time.isoformat()}"
                    )

        except CronParseError as e:
            logger.error(f"Cron parse error for job '{job.name}': {e}")

        except CronIntervalTooShortError as e:
            logger.warning(f"Cron interval too short for job '{job.name}': {e}")

        except JobCreationError as e:
            logger.error(f"Job creation error for job '{job.name}': {e}")

        except Exception as e:
            # 개별 크론 에러는 격리하여 다른 크론 처리에 영향을 주지 않음
            logger.error(f"Error processing job '{job.name}': {e}", exc_info=True)

    def _should_run(self, job: CronJob, now: datetime) -> tuple[bool, datetime | None]:
        """
        크론 실행 여부 판단

        Returns:
            (실행 여부, 예정 실행 시간)
        """
        try:
            cron = croniter(job.cron_expression, now)

            # 직전 실행 시점 계산
            prev_time = cron.get_prev(datetime)

            # 직전 실행 시점이 poll_interval 이내인지 확인
            diff_seconds = (now - prev_time).total_seconds()

            logger.debug(
                f"_should_run: job={job.name}, now={now}, prev_time={prev_time}, "
                f"diff_seconds={diff_seconds}, poll_interval={self._config.poll_interval_seconds}"
            )

            if diff_seconds <= self._config.poll_interval_seconds:
                return True, prev_time

            return False, None

        except Exception as e:
            raise CronParseError(job.cron_expression, str(e))

    def _validate_cron_interval(self, cron_expression: str) -> None:
        """
        크론 간격 검증 (초단위 크론 차단)

        Raises:
            CronIntervalTooShortError: 간격이 min_cron_interval_seconds 미만인 경우
        """
        try:
            now = datetime.now(timezone.utc)
            cron = croniter(cron_expression, now)

            # 다음 두 실행 시점의 간격 계산
            next1 = cron.get_next(datetime)
            next2 = cron.get_next(datetime)

            interval_seconds = (next2 - next1).total_seconds()

            if interval_seconds < self._config.min_cron_interval_seconds:
                raise CronIntervalTooShortError(
                    cron_expression,
                    interval_seconds,
                    self._config.min_cron_interval_seconds
                )

        except CronIntervalTooShortError:
            raise
        except Exception as e:
            raise CronParseError(cron_expression, str(e))

    @transactional
    async def _create_job_execution(self, job: CronJob, scheduled_time: datetime) -> bool:
        """
        Job 실행 레코드 생성 (중복 방지)

        Returns:
            True: 새로 생성됨
            False: 이미 존재하여 생성하지 않음
        """
        try:
            ctx = get_connection()
            scheduled_time_str = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")

            # ON CONFLICT DO NOTHING으로 중복 방지
            await self._queries.create_execution_if_not_exists(
                ctx.connection,
                job_id=job.id,
                scheduled_time=scheduled_time_str,
            )

            # 생성 여부 확인 (changes() 대신 조회로 확인)
            result = await self._queries.check_execution_exists(
                ctx.connection,
                job_id=job.id,
                scheduled_time=scheduled_time_str,
            )

            # 존재하면 생성되었거나 이미 있었던 것
            # 여기서는 단순히 True 반환 (중복이면 DO NOTHING이므로)
            return result is not None

        except Exception as e:
            raise JobCreationError(job.id, str(scheduled_time), str(e))

    @transactional_readonly
    async def _has_incomplete_execution(self, job_id: int) -> bool:
        """
        미완료(PENDING, RUNNING) 상태의 실행이 있는지 확인

        Args:
            job_id: 크론 Job ID

        Returns:
            True: 미완료 실행이 존재
            False: 미완료 실행이 없음
        """
        ctx = get_connection()
        result = await self._queries.has_incomplete_execution(
            ctx.connection,
            job_id=job_id,
        )
        return result is not None

    def _calculate_next_sleep(self, jobs: list[CronJob]) -> float:
        """
        다음 실행까지의 대기 시간 계산

        모든 크론 중 가장 빨리 실행될 시간까지의 간격을 계산하되,
        max_sleep_seconds를 초과하지 않음
        """
        if not jobs:
            return self._config.poll_interval_seconds

        now = datetime.now(timezone.utc)
        min_wait = float(self._config.max_sleep_seconds)

        for job in jobs:
            try:
                cron = croniter(job.cron_expression, now)
                next_time = cron.get_next(datetime)
                wait_seconds = (next_time - now).total_seconds()

                if wait_seconds > 0:
                    min_wait = min(min_wait, wait_seconds)

            except Exception as e:
                logger.debug(f"Error calculating next run for '{job.name}': {e}")
                continue

        # poll_interval_seconds ~ max_sleep_seconds 범위로 제한
        sleep_time = max(
            self._config.poll_interval_seconds,
            min(min_wait, self._config.max_sleep_seconds)
        )

        logger.debug(f"Next sleep: {sleep_time:.1f}s")
        return sleep_time

    @property
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._running


if __name__ == "__main__":
    import signal
    import yaml
    from database.registry import DatabaseRegistry

    async def main():
        # 설정 로드 (프로젝트 루트 기준)
        config_path = Path(__file__).parent.parent / "config"

        # 데이터베이스 설정
        with open(config_path / "database.yaml", encoding="utf-8") as f:
            db_config = yaml.safe_load(f)

        # Dispatcher 설정
        with open(config_path / "dispatcher.yaml", encoding="utf-8") as f:
            dispatcher_config = yaml.safe_load(f)

        # 로깅 설정
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Dispatcher 설정
        config = DispatcherConfig(**dispatcher_config.get("dispatcher", {}))

        # 데이터베이스 초기화 (지정된 DB만)
        await DatabaseRegistry.init_from_config(db_config, [config.database])

        # Dispatcher 인스턴스 생성
        dispatcher = Dispatcher(config)

        # Graceful Shutdown 시그널 핸들러
        loop = asyncio.get_running_loop()

        def signal_handler():
            logger.info("Received shutdown signal")
            asyncio.create_task(dispatcher.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            # Dispatcher 시작
            logger.info("Starting dispatcher...")
            await dispatcher.start()
        finally:
            await DatabaseRegistry.close_all()

    asyncio.run(main())
