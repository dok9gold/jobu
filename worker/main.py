"""
WorkerPool: 잡 실행 워커풀 모듈

job_executions 테이블에서 PENDING 상태의 잡을 폴링하여 실행합니다.

실행 방법:
    python -m worker.main
    python main.py worker
"""

import asyncio
import logging
import signal
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosql

from database import get_connection, transactional_readonly
from worker.executor import Executor, JobInfo

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    """워커풀 설정"""
    database: str = "default"  # job 관리용 DB (database.yaml에 정의된 이름)
    databases: list[str] = field(default_factory=list)  # 핸들러에서 사용할 추가 DB들
    pool_size: int = 5
    poll_interval_seconds: int = 5
    claim_batch_size: int = 10
    shutdown_timeout_seconds: int = 30


class WorkerPool:
    """
    잡 실행 워커풀

    PENDING 상태의 잡을 폴링하여 워커에 할당하고 실행합니다.
    """

    def __init__(self, config: WorkerConfig):
        self._config = config
        self._running = False
        self._stop_event: asyncio.Event | None = None
        self._queries: Any | None = None
        self._executor: Executor | None = None
        self._running_tasks: set[asyncio.Task] = set()
        self._semaphore: asyncio.Semaphore | None = None

    async def start(self) -> None:
        """워커풀 메인 루프 시작"""
        if self._running:
            logger.warning("WorkerPool is already running")
            return

        self._running = True
        self._stop_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(self._config.pool_size)

        # SQL 쿼리 로드
        sql_path = Path(__file__).parent / "sql" / "worker.sql"
        self._queries = aiosql.from_path(str(sql_path), "aiosqlite")
        self._executor = Executor(self._queries)

        logger.info(
            f"WorkerPool started (pool_size={self._config.pool_size}, "
            f"poll_interval={self._config.poll_interval_seconds}s)"
        )

        try:
            await self._main_loop()
        except asyncio.CancelledError:
            logger.info("WorkerPool cancelled")
        except Exception as e:
            logger.error(f"WorkerPool error: {e}", exc_info=True)
            raise
        finally:
            await self._wait_running_tasks()
            self._running = False
            logger.info("WorkerPool stopped")

    async def stop(self) -> None:
        """WorkerPool graceful shutdown"""
        if not self._running:
            return

        logger.info("Stopping WorkerPool...")
        self._running = False
        if self._stop_event:
            self._stop_event.set()

    async def _main_loop(self) -> None:
        """메인 폴링 루프"""
        while self._running:
            try:
                await self._poll_and_assign()
            except Exception as e:
                logger.error(f"Error in poll_and_assign: {e}", exc_info=True)

            # 다음 폴링까지 대기 (stop 시 즉시 종료)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._config.poll_interval_seconds
                )
                break  # stop_event가 set되면 루프 종료
            except asyncio.TimeoutError:
                pass  # 타임아웃이면 계속 폴링

    async def _poll_and_assign(self) -> None:
        """PENDING 잡 조회 후 워커에 할당"""
        # 가용 워커 수만큼만 가져오기
        available_workers = self._config.pool_size - len(self._running_tasks)
        if available_workers <= 0:
            logger.debug("No available workers, skipping poll")
            return

        batch_size = min(available_workers, self._config.claim_batch_size)
        jobs = await self._get_pending_jobs(batch_size)

        if not jobs:
            logger.debug("No pending jobs found")
            return

        logger.debug(f"Found {len(jobs)} pending jobs")

        for job in jobs:
            job_info = JobInfo(
                id=job["id"],
                job_id=job["job_id"],
                scheduled_time=job["scheduled_time"],
                retry_count=job["retry_count"],
                job_name=job["job_name"],
                handler_name=job["handler_name"],
                handler_params=job["handler_params"],
                max_retry=job["max_retry"],
                timeout_seconds=job["timeout_seconds"],
            )

            # 세마포어로 동시 실행 수 제한
            await self._semaphore.acquire()
            task = asyncio.create_task(self._execute_job(job_info))
            self._running_tasks.add(task)
            task.add_done_callback(self._on_task_done)

    async def _execute_job(self, job_info: JobInfo) -> None:
        """잡 실행 (워커 태스크)"""
        try:
            await self._executor.execute(job_info)
        except Exception as e:
            logger.error(f"Unexpected error executing job {job_info.id}: {e}", exc_info=True)
        finally:
            self._semaphore.release()

    def _on_task_done(self, task: asyncio.Task) -> None:
        """태스크 완료 콜백"""
        self._running_tasks.discard(task)
        if task.exception():
            logger.error(f"Task exception: {task.exception()}")

    @transactional_readonly
    async def _get_pending_jobs(self, limit: int) -> list[dict]:
        """PENDING 상태의 잡 목록 조회"""
        ctx = get_connection()
        rows = await self._queries.get_pending_executions(ctx.connection, limit=limit)
        return [dict(row) for row in rows] if rows else []

    async def _wait_running_tasks(self) -> None:
        """실행 중인 태스크 완료 대기 (graceful shutdown)"""
        if not self._running_tasks:
            return

        logger.info(f"Waiting for {len(self._running_tasks)} running tasks...")

        try:
            await asyncio.wait_for(
                asyncio.gather(*self._running_tasks, return_exceptions=True),
                timeout=self._config.shutdown_timeout_seconds
            )
            logger.info("All tasks completed")
        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown timeout ({self._config.shutdown_timeout_seconds}s), "
                f"{len(self._running_tasks)} tasks still running"
            )
            # 강제 취소
            for task in self._running_tasks:
                task.cancel()

    @property
    def is_running(self) -> bool:
        """실행 중 여부"""
        return self._running

    @property
    def running_task_count(self) -> int:
        """실행 중인 태스크 수"""
        return len(self._running_tasks)


def _load_handlers() -> None:
    """핸들러 모듈 로드 (데코레이터 등록을 위해, 하위 폴더 재귀 탐색)"""
    import importlib
    import pkgutil
    from worker import job as job_pkg

    def load_recursive(package, prefix: str):
        for _, module_name, is_pkg in pkgutil.iter_modules(package.__path__):
            full_name = f"{prefix}.{module_name}"
            module = importlib.import_module(full_name)
            logger.debug(f"Loaded handler module: {full_name}")
            if is_pkg:
                load_recursive(module, full_name)

    load_recursive(job_pkg, "worker.job")


if __name__ == "__main__":
    import yaml
    from database.registry import DatabaseRegistry

    async def main():
        # 설정 로드 (프로젝트 루트 기준)
        config_path = Path(__file__).parent.parent / "config"

        # 데이터베이스 설정
        with open(config_path / "database.yaml", encoding="utf-8") as f:
            db_config = yaml.safe_load(f)

        # Worker 설정
        with open(config_path / "worker.yaml", encoding="utf-8") as f:
            worker_config = yaml.safe_load(f)

        # 로깅 설정
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 핸들러 로드
        _load_handlers()

        # WorkerPool 설정
        config = WorkerConfig(**worker_config.get("worker", {}))

        # 데이터베이스 초기화 (database + databases에 지정된 DB만)
        db_names = [config.database] + config.databases
        await DatabaseRegistry.init_from_config(db_config, db_names)

        # WorkerPool 생성
        worker_pool = WorkerPool(config)

        # 시그널 핸들러 등록
        loop = asyncio.get_event_loop()

        def signal_handler():
            logger.info("Received shutdown signal")
            asyncio.create_task(worker_pool.stop())

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

        try:
            logger.info("Starting WorkerPool...")
            await worker_pool.start()
        finally:
            await DatabaseRegistry.close_all()

    asyncio.run(main())
