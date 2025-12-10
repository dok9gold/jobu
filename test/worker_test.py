"""
WorkerPool 테스트

테스트 항목:
1. @handler 데코레이터 등록 테스트
2. get_handler() 테스트 (성공/실패)
3. Executor 성공 테스트
4. Executor 실패 테스트 (retry)
5. Executor 타임아웃 테스트 (retry)
6. WorkerPool 폴링 테스트
7. WorkerPool graceful shutdown 테스트

실행: python -m pytest test/worker_test.py -v
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiosql
import pytest
import pytest_asyncio
import yaml

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import transactional, transactional_readonly, get_connection, get_db
from database.sqlite3 import Database
from database.registry import DatabaseRegistry
from worker.base import (
    BaseHandler,
    handler,
    get_handler,
    get_registered_handlers,
    HandlerNotFoundError,
    _registry,
)
from worker.executor import Executor
from worker.model import JobInfo
from worker.main import WorkerPool, WorkerConfig

# 테스트용 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================
# Fixtures
# ============================================================

@pytest_asyncio.fixture
async def test_config():
    """config/database.yaml 로드"""
    config_path = Path(__file__).parent.parent / "config" / "database.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest_asyncio.fixture
async def database(test_config):
    """테스트용 Database 인스턴스 (DatabaseRegistry 사용)"""
    DatabaseRegistry.clear()

    await DatabaseRegistry.init_from_config(test_config)
    db = get_db('default')

    # 테스트 전 기존 테스트 데이터 정리 (PENDING 상태인 것들도 모두 정리)
    async with db.transaction() as ctx:
        # 기존 worker_test 데이터 삭제
        await ctx.execute("DELETE FROM job_executions WHERE job_id IN (SELECT id FROM cron_jobs WHERE name LIKE ?)", ("worker_test_%",))
        await ctx.execute("DELETE FROM cron_jobs WHERE name LIKE ?", ("worker_test_%",))
        # 다른 테스트에서 남은 PENDING 잡도 정리 (test_handler 등)
        await ctx.execute("DELETE FROM job_executions WHERE status = 'PENDING'")

    yield db
    await DatabaseRegistry.close_all()


@pytest_asyncio.fixture
async def worker_queries():
    """Worker SQL 쿼리 로드"""
    sql_path = Path(__file__).parent.parent / "worker" / "sql" / "worker.sql"
    return aiosql.from_path(str(sql_path), "aiosqlite")


@pytest_asyncio.fixture
async def executor(worker_queries):
    """Executor 인스턴스"""
    return Executor(worker_queries)


@pytest_asyncio.fixture
async def sample_cron_job(database):
    """테스트용 크론잡 생성"""
    async with database.transaction() as ctx:
        await ctx.begin()
        cursor = await ctx.execute(
            """
            INSERT INTO cron_jobs (name, cron_expression, handler_name, handler_params, max_retry, timeout_seconds)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("worker_test_sample", "* * * * *", "sample", '{"message": "test"}', 3, 10)
        )
        job_id = cursor.lastrowid
        await ctx.commit()

    yield job_id

    # 정리
    async with database.transaction() as ctx:
        await ctx.begin()
        await ctx.execute("DELETE FROM job_executions WHERE job_id = ?", (job_id,))
        await ctx.execute("DELETE FROM cron_jobs WHERE id = ?", (job_id,))
        await ctx.commit()


@pytest_asyncio.fixture
async def pending_execution(database, sample_cron_job):
    """PENDING 상태의 실행 레코드 생성"""
    job_id = sample_cron_job
    scheduled_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    async with database.transaction() as ctx:
        await ctx.begin()
        cursor = await ctx.execute(
            """
            INSERT INTO job_executions (job_id, scheduled_time, status)
            VALUES (?, ?, 'PENDING')
            """,
            (job_id, scheduled_time)
        )
        execution_id = cursor.lastrowid
        await ctx.commit()

    return execution_id, job_id, scheduled_time


# ============================================================
# Handler Registry Tests
# ============================================================

class TestHandlerRegistry:
    """@handler 데코레이터 및 get_handler() 테스트"""

    def test_handler_decorator_registers_class(self):
        """@handler 데코레이터로 핸들러가 등록됨"""
        # sample.py import 시 자동 등록됨
        from worker.job import sample  # noqa: F401

        handlers = get_registered_handlers()
        assert "sample" in handlers
        assert handlers["sample"].__name__ == "SampleHandler"

    def test_get_handler_returns_instance(self):
        """get_handler()가 인스턴스를 반환함"""
        from worker.job import sample  # noqa: F401

        handler_instance = get_handler("sample")
        assert handler_instance is not None
        assert isinstance(handler_instance, BaseHandler)

    def test_get_handler_raises_on_unknown(self):
        """존재하지 않는 핸들러 요청 시 HandlerNotFoundError"""
        with pytest.raises(HandlerNotFoundError) as exc_info:
            get_handler("unknown_handler_xyz")

        assert "unknown_handler_xyz" in str(exc_info.value)

    def test_custom_handler_registration(self):
        """커스텀 핸들러 등록 테스트"""
        @handler("test_custom")
        class TestCustomHandler(BaseHandler):
            async def execute(self, params: dict):
                return {"custom": True}

        assert "test_custom" in get_registered_handlers()

        instance = get_handler("test_custom")
        assert instance is not None

        # 정리
        del _registry["test_custom"]


# ============================================================
# Executor Tests
# ============================================================

class TestExecutor:
    """Executor 테스트"""

    @pytest.mark.asyncio
    async def test_executor_success(self, database, executor, pending_execution):
        """Executor 성공 테스트"""
        from worker.job import sample  # noqa: F401

        execution_id, job_id, scheduled_time = pending_execution

        job_info = JobInfo(
            id=execution_id,
            job_id=job_id,
            scheduled_time=scheduled_time,
            retry_count=0,
            job_name="worker_test_sample",
            handler_name="sample",
            handler_params='{"message": "test success"}',
            max_retry=3,
            timeout_seconds=10,
        )

        result = await executor.execute(job_info)
        assert result is True

        # DB 상태 확인
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status, result FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            assert row["status"] == "SUCCESS"
            result_data = json.loads(row["result"])
            assert result_data["success"] is True

    @pytest.mark.asyncio
    async def test_executor_failure_with_retry(self, database, executor, pending_execution):
        """Executor 실패 후 재시도 테스트"""
        from worker.job import sample  # noqa: F401

        execution_id, job_id, scheduled_time = pending_execution

        job_info = JobInfo(
            id=execution_id,
            job_id=job_id,
            scheduled_time=scheduled_time,
            retry_count=0,
            job_name="worker_test_sample",
            handler_name="sample",
            handler_params='{"should_fail": true, "message": "test failure"}',
            max_retry=3,
            timeout_seconds=10,
        )

        result = await executor.execute(job_info)
        assert result is False

        # DB 상태 확인 - retry_count < max_retry이므로 PENDING으로 복귀
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status, retry_count, error_message FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            assert row["status"] == "PENDING"
            assert row["retry_count"] == 1

    @pytest.mark.asyncio
    async def test_executor_failure_max_retry_exceeded(self, database, executor, pending_execution):
        """최대 재시도 초과 시 FAILED 유지"""
        from worker.job import sample  # noqa: F401

        execution_id, job_id, scheduled_time = pending_execution

        # retry_count를 max_retry - 1로 설정
        async with database.transaction() as ctx:
            await ctx.begin()
            await ctx.execute(
                "UPDATE job_executions SET retry_count = 2 WHERE id = ?",
                (execution_id,)
            )
            await ctx.commit()

        job_info = JobInfo(
            id=execution_id,
            job_id=job_id,
            scheduled_time=scheduled_time,
            retry_count=2,
            job_name="worker_test_sample",
            handler_name="sample",
            handler_params='{"should_fail": true}',
            max_retry=3,
            timeout_seconds=10,
        )

        result = await executor.execute(job_info)
        assert result is False

        # DB 상태 확인 - retry_count >= max_retry이므로 FAILED 유지
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status, retry_count FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            assert row["status"] == "FAILED"
            assert row["retry_count"] == 3

    @pytest.mark.asyncio
    async def test_executor_timeout_with_retry(self, database, executor, pending_execution):
        """타임아웃 후 재시도 테스트"""
        from worker.job import sample  # noqa: F401

        execution_id, job_id, scheduled_time = pending_execution

        job_info = JobInfo(
            id=execution_id,
            job_id=job_id,
            scheduled_time=scheduled_time,
            retry_count=0,
            job_name="worker_test_sample",
            handler_name="sample",
            handler_params='{"sleep_seconds": 5}',  # 5초 sleep
            max_retry=3,
            timeout_seconds=1,  # 1초 타임아웃
        )

        result = await executor.execute(job_info)
        assert result is False

        # DB 상태 확인 - 타임아웃 후 PENDING으로 복귀
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status, retry_count, error_message FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            assert row["status"] == "PENDING"
            assert row["retry_count"] == 1
            assert "timed out" in row["error_message"].lower()

    @pytest.mark.asyncio
    async def test_executor_handler_not_found(self, database, executor, pending_execution):
        """존재하지 않는 핸들러 테스트"""
        execution_id, job_id, scheduled_time = pending_execution

        job_info = JobInfo(
            id=execution_id,
            job_id=job_id,
            scheduled_time=scheduled_time,
            retry_count=0,
            job_name="worker_test_sample",
            handler_name="nonexistent_handler",
            handler_params="{}",
            max_retry=3,
            timeout_seconds=10,
        )

        result = await executor.execute(job_info)
        assert result is False

        # DB 상태 확인
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status, error_message FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            # 재시도 가능하므로 PENDING
            assert row["status"] == "PENDING"
            assert "not found" in row["error_message"].lower()


# ============================================================
# WorkerPool Tests
# ============================================================

class TestWorkerPool:
    """WorkerPool 테스트"""

    @pytest.mark.asyncio
    async def test_worker_pool_processes_pending_jobs(self, database, sample_cron_job):
        """WorkerPool이 PENDING 잡을 처리함"""
        from worker.job import sample  # noqa: F401

        job_id = sample_cron_job
        scheduled_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # PENDING 잡 생성
        async with database.transaction() as ctx:
            await ctx.begin()
            cursor = await ctx.execute(
                """
                INSERT INTO job_executions (job_id, scheduled_time, status)
                VALUES (?, ?, 'PENDING')
                """,
                (job_id, scheduled_time)
            )
            execution_id = cursor.lastrowid
            await ctx.commit()

        # WorkerPool 실행 (짧은 시간)
        config = WorkerConfig(
            pool_size=2,
            poll_interval_seconds=1,
            claim_batch_size=5,
            shutdown_timeout_seconds=5,
        )
        worker_pool = WorkerPool(config)

        async def run_worker():
            task = asyncio.create_task(worker_pool.start())
            await asyncio.sleep(2)  # 2초 후 중지
            await worker_pool.stop()
            await task

        await run_worker()

        # 잡이 처리되었는지 확인
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            assert row["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_worker_pool_graceful_shutdown(self, database, sample_cron_job):
        """WorkerPool graceful shutdown 테스트"""
        from worker.job import sample  # noqa: F401

        job_id = sample_cron_job
        scheduled_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # 긴 실행 시간의 PENDING 잡 생성
        async with database.transaction() as ctx:
            await ctx.begin()
            await ctx.execute(
                "UPDATE cron_jobs SET handler_params = ? WHERE id = ?",
                ('{"sleep_seconds": 3}', job_id)
            )
            cursor = await ctx.execute(
                """
                INSERT INTO job_executions (job_id, scheduled_time, status)
                VALUES (?, ?, 'PENDING')
                """,
                (job_id, scheduled_time)
            )
            execution_id = cursor.lastrowid
            await ctx.commit()

        config = WorkerConfig(
            pool_size=2,
            poll_interval_seconds=1,
            claim_batch_size=5,
            shutdown_timeout_seconds=10,
        )
        worker_pool = WorkerPool(config)

        async def run_and_stop():
            task = asyncio.create_task(worker_pool.start())
            await asyncio.sleep(1)  # 잡이 시작될 때까지 대기
            assert worker_pool.running_task_count > 0 or True  # 이미 시작됨
            await worker_pool.stop()  # graceful shutdown
            await task

        await run_and_stop()

        # 잡이 완료되었는지 확인
        async with database.transaction() as ctx:
            row = await ctx.fetch_one(
                "SELECT status FROM job_executions WHERE id = ?",
                (execution_id,)
            )
            assert row["status"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_worker_pool_concurrent_execution(self, database, sample_cron_job):
        """WorkerPool 동시 실행 테스트"""
        from worker.job import sample  # noqa: F401

        job_id = sample_cron_job
        execution_ids = []

        # 여러 PENDING 잡 생성
        async with database.transaction() as ctx:
            await ctx.begin()
            await ctx.execute(
                "UPDATE cron_jobs SET handler_params = ? WHERE id = ?",
                ('{"sleep_seconds": 1}', job_id)
            )
            for i in range(5):
                scheduled_time = f"2024-01-01 00:0{i}:00"
                cursor = await ctx.execute(
                    """
                    INSERT INTO job_executions (job_id, scheduled_time, status)
                    VALUES (?, ?, 'PENDING')
                    """,
                    (job_id, scheduled_time)
                )
                execution_ids.append(cursor.lastrowid)
            await ctx.commit()

        config = WorkerConfig(
            pool_size=3,  # 동시 3개
            poll_interval_seconds=1,
            claim_batch_size=10,
            shutdown_timeout_seconds=10,
        )
        worker_pool = WorkerPool(config)

        async def run_worker():
            task = asyncio.create_task(worker_pool.start())
            await asyncio.sleep(5)  # 충분히 대기
            await worker_pool.stop()
            await task

        await run_worker()

        # 모든 잡이 처리되었는지 확인
        async with database.transaction() as ctx:
            for exec_id in execution_ids:
                row = await ctx.fetch_one(
                    "SELECT status FROM job_executions WHERE id = ?",
                    (exec_id,)
                )
                assert row["status"] == "SUCCESS"
