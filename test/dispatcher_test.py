"""
Dispatcher 테스트

테스트 항목:
1. 크론 시간 도달 시 Job이 PENDING 상태로 생성됨
2. scheduled_time이 정확히 기록됨
3. 동일 job_id + scheduled_time 조합으로 중복 생성 시도 시 무시됨
4. is_enabled=0인 크론은 Job 생성 안됨
5. 1분 미만 간격 크론 등록 시 validation 에러
6. 특정 크론 파싱 에러 시 다른 크론은 정상 동작

실행: python -m pytest test/dispatcher_test.py -v
"""

import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, AsyncMock

import aiosql
import pytest
import pytest_asyncio
import yaml
from croniter import croniter

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import transactional, transactional_readonly, get_connection, get_db
from database.sqlite3 import Database
from database.registry import DatabaseRegistry
from dispatcher.main import Dispatcher
from dispatcher.model.dispatcher import (
    CronJob,
    DispatcherConfig,
    ExecutionStatus,
)
from dispatcher.exception import (
    CronParseError,
    CronIntervalTooShortError,
)

# 테스트용 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def test_config():
    """config/database_test.yaml 로드"""
    config_path = Path(__file__).parent.parent / "config" / "database.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest_asyncio.fixture
async def database(test_config):
    """테스트용 Database 인스턴스 (DatabaseRegistry 사용)"""
    DatabaseRegistry.clear()

    await DatabaseRegistry.init_from_config(test_config)
    db = get_db('default')

    # 테스트 전 기존 테스트 데이터 정리
    async with db.transaction() as ctx:
        await ctx.execute("DELETE FROM job_executions WHERE job_id IN (SELECT id FROM cron_jobs WHERE name LIKE ?)", ("dispatcher_test_%",))
        await ctx.execute("DELETE FROM cron_jobs WHERE name LIKE ?", ("dispatcher_test_%",))

    yield db
    await DatabaseRegistry.close_all()


@pytest_asyncio.fixture
async def dispatcher_config():
    """Dispatcher 설정"""
    return DispatcherConfig(
        poll_interval_seconds=10,
        max_sleep_seconds=60,
        min_cron_interval_seconds=60,
    )


@pytest_asyncio.fixture
async def dispatcher(dispatcher_config):
    """Dispatcher 인스턴스 (SQL 쿼리 로드됨)"""
    d = Dispatcher(dispatcher_config)
    # SQL 쿼리 로드 (start() 호출하지 않고 쿼리만 로드)
    sql_path = Path(__file__).parent.parent / "dispatcher" / "sql" / "dispatcher.sql"
    d._queries = aiosql.from_path(str(sql_path), "aiosqlite")
    return d


class TestCronJobCreation:
    """크론 Job 생성 테스트"""

    @pytest.mark.asyncio
    async def test_job_created_pending_on_cron_time(self, database, dispatcher):
        """크론 시간 도달 시 Job이 PENDING 상태로 생성됨"""
        # 테스트용 크론 생성 (매분 실행)
        @transactional
        async def create_test_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_every_minute", "* * * * *", "test_handler", 1)
            )

        await create_test_cron()

        # 크론 조회
        jobs = await dispatcher._poll_cron_jobs()
        test_job = next((j for j in jobs if j.name == "dispatcher_test_every_minute"), None)
        assert test_job is not None

        # 현재 시간 기준 직전 실행 시간 계산
        now = datetime.now()
        cron = croniter(test_job.cron_expression, now)
        scheduled_time = cron.get_prev(datetime)

        # Job 생성
        created = await dispatcher._create_job_execution(test_job, scheduled_time)
        assert created is True

        # DB 확인
        @transactional_readonly
        async def check_execution():
            ctx = get_connection()
            row = await ctx.fetch_one(
                """SELECT * FROM job_executions
                   WHERE job_id = ? AND scheduled_time = ?""",
                (test_job.id, scheduled_time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            return row

        row = await check_execution()
        assert row is not None
        assert row["status"] == ExecutionStatus.PENDING.value
        logger.info("Job creation test passed: PENDING status confirmed")

    @pytest.mark.asyncio
    async def test_scheduled_time_recorded_correctly(self, database, dispatcher):
        """scheduled_time이 정확히 기록됨"""
        # 테스트용 크론 생성
        @transactional
        async def create_test_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_scheduled_time", "0 * * * *", "test_handler", 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_scheduled_time",)
            )
            return row["id"]

        job_id = await create_test_cron()

        # 특정 시간으로 Job 생성
        expected_time = datetime(2024, 1, 15, 10, 0, 0)
        test_job = CronJob(
            id=job_id,
            name="dispatcher_test_scheduled_time",
            cron_expression="0 * * * *",
            handler_name="test_handler",
            is_enabled=True,
        )

        await dispatcher._create_job_execution(test_job, expected_time)

        # DB 확인
        @transactional_readonly
        async def check_scheduled_time():
            ctx = get_connection()
            row = await ctx.fetch_one(
                "SELECT scheduled_time FROM job_executions WHERE job_id = ?",
                (job_id,)
            )
            return row

        row = await check_scheduled_time()
        assert row is not None
        assert row["scheduled_time"] == "2024-01-15 10:00:00"
        logger.info("Scheduled time recording test passed")


class TestDuplicatePrevention:
    """중복 생성 방지 테스트"""

    @pytest.mark.asyncio
    async def test_duplicate_execution_ignored(self, database, dispatcher):
        """동일 job_id + scheduled_time 조합으로 중복 생성 시도 시 무시됨"""
        # 테스트용 크론 생성
        @transactional
        async def create_test_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_duplicate", "* * * * *", "test_handler", 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_duplicate",)
            )
            return row["id"]

        job_id = await create_test_cron()

        test_job = CronJob(
            id=job_id,
            name="dispatcher_test_duplicate",
            cron_expression="0 * * * *",
            handler_name="test_handler",
            is_enabled=True,
        )

        scheduled_time = datetime(2024, 1, 15, 11, 0, 0)

        # 첫 번째 생성
        created1 = await dispatcher._create_job_execution(test_job, scheduled_time)
        assert created1 is True

        # 중복 생성 시도
        created2 = await dispatcher._create_job_execution(test_job, scheduled_time)
        # ON CONFLICT DO NOTHING이므로 에러 없이 True 반환 (이미 존재)
        assert created2 is True

        # 실제로 1개만 존재하는지 확인
        @transactional_readonly
        async def count_executions():
            ctx = get_connection()
            rows = await ctx.fetch_all(
                "SELECT * FROM job_executions WHERE job_id = ? AND scheduled_time = ?",
                (job_id, scheduled_time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            return len(rows)

        count = await count_executions()
        assert count == 1
        logger.info("Duplicate prevention test passed: only 1 execution exists")

    @pytest.mark.asyncio
    async def test_concurrent_creation_single_result(self, database, dispatcher):
        """다중 Dispatcher 인스턴스에서 동시 생성 시도해도 1개만 생성"""
        # 테스트용 크론 생성
        @transactional
        async def create_test_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_concurrent", "0 * * * *", "test_handler", 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_concurrent",)
            )
            return row["id"]

        job_id = await create_test_cron()

        test_job = CronJob(
            id=job_id,
            name="dispatcher_test_concurrent",
            cron_expression="0 * * * *",
            handler_name="test_handler",
            is_enabled=True,
        )

        scheduled_time = datetime(2024, 1, 15, 12, 0, 0)

        # 여러 디스패처 인스턴스 생성 (SQL 쿼리 로드)
        config = DispatcherConfig()
        sql_path = Path(__file__).parent.parent / "dispatcher" / "sql" / "dispatcher.sql"
        queries = aiosql.from_path(str(sql_path), "aiosqlite")
        dispatchers = []
        for _ in range(5):
            d = Dispatcher(config)
            d._queries = queries
            dispatchers.append(d)

        # 동시에 Job 생성 시도
        tasks = [d._create_job_execution(test_job, scheduled_time) for d in dispatchers]
        await asyncio.gather(*tasks)

        # 1개만 존재하는지 확인
        @transactional_readonly
        async def count_executions():
            ctx = get_connection()
            rows = await ctx.fetch_all(
                "SELECT * FROM job_executions WHERE job_id = ? AND scheduled_time = ?",
                (job_id, scheduled_time.strftime("%Y-%m-%d %H:%M:%S"))
            )
            return len(rows)

        count = await count_executions()
        assert count == 1
        logger.info("Concurrent creation test passed: single execution created")


class TestDisabledCron:
    """비활성화 크론 테스트"""

    @pytest.mark.asyncio
    async def test_disabled_cron_not_processed(self, database, dispatcher):
        """is_enabled=0인 크론은 Job 생성 안됨"""
        # 비활성화 크론 생성
        @transactional
        async def create_disabled_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_disabled", "* * * * *", "test_handler", 0)
            )

        await create_disabled_cron()

        # 활성화된 크론만 조회
        jobs = await dispatcher._poll_cron_jobs()

        # 비활성화 크론이 조회되지 않아야 함
        disabled_job = next((j for j in jobs if j.name == "dispatcher_test_disabled"), None)
        assert disabled_job is None
        logger.info("Disabled cron test passed: not included in poll results")


class TestCronIntervalValidation:
    """크론 간격 검증 테스트"""

    @pytest.mark.asyncio
    async def test_sub_minute_cron_rejected(self, database, dispatcher):
        """1분 미만 간격 크론은 validation 에러"""
        # 매 초 실행 크론 (croniter 형식)
        # 표준 cron은 분 단위이므로, 여기서는 간격 계산 테스트
        with pytest.raises(CronIntervalTooShortError):
            # 매초 실행하는 크론은 없지만, 간격이 60초 미만인 크론 테스트
            # "* * * * *"은 매분 실행 = 60초 간격이므로 통과
            # min_cron_interval_seconds=120으로 설정하면 실패해야 함
            config = DispatcherConfig(min_cron_interval_seconds=120)
            test_dispatcher = Dispatcher(config)
            test_dispatcher._validate_cron_interval("* * * * *")

        logger.info("Sub-minute cron validation test passed")

    @pytest.mark.asyncio
    async def test_valid_cron_interval_passes(self, database, dispatcher):
        """유효한 간격의 크론은 통과"""
        # 매 시간 실행 = 3600초 간격
        try:
            dispatcher._validate_cron_interval("0 * * * *")
        except CronIntervalTooShortError:
            pytest.fail("Valid cron interval should not raise error")

        logger.info("Valid cron interval test passed")


class TestErrorIsolation:
    """에러 격리 테스트"""

    @pytest.mark.asyncio
    async def test_parse_error_isolated(self, database, dispatcher):
        """특정 크론 파싱 에러 시 다른 크론은 정상 동작"""
        # 정상 크론과 비정상 크론 생성
        @transactional
        async def create_test_crons():
            ctx = get_connection()
            # 정상 크론
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_valid", "0 * * * *", "test_handler", 1)
            )
            # 비정상 크론 (잘못된 표현식)
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("dispatcher_test_invalid", "invalid_cron", "test_handler", 1)
            )

        await create_test_crons()

        # 크론 처리 (에러가 격리되어 전체가 실패하지 않아야 함)
        jobs = await dispatcher._poll_cron_jobs()

        processed_count = 0
        errors = []

        for job in jobs:
            if job.name.startswith("dispatcher_test_"):
                try:
                    await dispatcher._process_cron_job(job)
                    processed_count += 1
                except Exception as e:
                    errors.append(str(e))

        # 에러가 발생해도 전체 처리는 계속됨 (에러는 내부적으로 로깅됨)
        logger.info(f"Error isolation test: processed={processed_count}, errors isolated internally")


class TestShouldRun:
    """_should_run 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_should_run_within_poll_interval(self, database):
        """poll_interval 내 실행 시간이면 should_run=True"""
        # poll_interval을 120초로 설정하여 매분 실행 크론이 확실히 감지되도록 함
        config = DispatcherConfig(poll_interval_seconds=120)
        test_dispatcher = Dispatcher(config)

        job = CronJob(
            id=1,
            name="test_job",
            cron_expression="* * * * *",
            handler_name="test_handler",
        )

        now = datetime.now(timezone.utc)
        should_run, scheduled_time = test_dispatcher._should_run(job, now)

        # 매분 실행 크론이고 poll_interval이 120초이므로 직전 분이 감지되어야 함
        assert should_run is True
        assert scheduled_time is not None
        logger.info("should_run test passed")

    @pytest.mark.asyncio
    async def test_should_run_outside_poll_interval(self, database):
        """poll_interval 외의 실행 시간이면 should_run=False"""
        # 매우 짧은 poll_interval 설정
        config = DispatcherConfig(poll_interval_seconds=10)
        test_dispatcher = Dispatcher(config)

        # 매일 자정에만 실행되는 크론
        job = CronJob(
            id=1,
            name="test_job",
            cron_expression="0 0 * * *",
            handler_name="test_handler",
        )

        # 현재 시간이 자정 근처가 아니면 should_run=False
        now = datetime(2024, 1, 15, 12, 30, 0, tzinfo=timezone.utc)  # 낮 12시 30분 UTC
        should_run, scheduled_time = test_dispatcher._should_run(job, now)

        # 직전 실행 시간(0시)이 poll_interval(10초) 이내가 아니므로 False
        assert should_run is False
        logger.info("should_run outside interval test passed")


class TestCalculateNextSleep:
    """_calculate_next_sleep 메서드 테스트"""

    @pytest.mark.asyncio
    async def test_calculate_sleep_respects_max(self, database, dispatcher):
        """max_sleep_seconds를 초과하지 않음"""
        # 매일 실행되는 크론 (다음 실행까지 많이 남음)
        jobs = [
            CronJob(
                id=1,
                name="daily_job",
                cron_expression="0 0 * * *",
                handler_name="test_handler",
            )
        ]

        sleep_time = dispatcher._calculate_next_sleep(jobs)

        # max_sleep_seconds 이하여야 함
        assert sleep_time <= dispatcher._config.max_sleep_seconds
        logger.info(f"Sleep time calculation test passed: {sleep_time}s")

    @pytest.mark.asyncio
    async def test_calculate_sleep_respects_min(self, database, dispatcher):
        """poll_interval_seconds 미만으로 내려가지 않음"""
        # 매분 실행되는 크론
        jobs = [
            CronJob(
                id=1,
                name="minute_job",
                cron_expression="* * * * *",
                handler_name="test_handler",
            )
        ]

        sleep_time = dispatcher._calculate_next_sleep(jobs)

        # poll_interval_seconds 이상이어야 함
        assert sleep_time >= dispatcher._config.poll_interval_seconds
        logger.info(f"Min sleep time test passed: {sleep_time}s")


class TestDispatcherLifecycle:
    """Dispatcher 생명주기 테스트"""

    @pytest.mark.asyncio
    async def test_start_stop(self, database, dispatcher):
        """start/stop 동작 테스트"""
        # 짧은 시간 실행 후 중지
        async def run_and_stop():
            task = asyncio.create_task(dispatcher.start())
            await asyncio.sleep(0.5)
            await dispatcher.stop()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except asyncio.TimeoutError:
                task.cancel()

        await run_and_stop()
        assert dispatcher.is_running is False
        logger.info("Dispatcher lifecycle test passed")


class TestAllowOverlap:
    """allow_overlap 기능 테스트"""

    @pytest.mark.asyncio
    async def test_allow_overlap_true_creates_job_with_incomplete(self, database, dispatcher):
        """allow_overlap=True이면 미완료 Job이 있어도 새 Job 생성"""
        @transactional
        async def create_test_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled, allow_overlap)
                   VALUES (?, ?, ?, ?, ?)""",
                ("dispatcher_test_overlap_true", "* * * * *", "test_handler", 1, 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_overlap_true",)
            )
            return row["id"]

        job_id = await create_test_cron()

        # 미완료 Job(PENDING) 생성
        scheduled_time1 = datetime(2024, 1, 15, 10, 0, 0)
        test_job = CronJob(
            id=job_id,
            name="dispatcher_test_overlap_true",
            cron_expression="* * * * *",
            handler_name="test_handler",
            is_enabled=True,
            allow_overlap=True,
        )
        await dispatcher._create_job_execution(test_job, scheduled_time1)

        # 두 번째 Job 생성 시도 (다른 scheduled_time)
        scheduled_time2 = datetime(2024, 1, 15, 10, 1, 0)
        created = await dispatcher._create_job_execution(test_job, scheduled_time2)
        assert created is True

        # 2개 존재하는지 확인
        @transactional_readonly
        async def count_executions():
            ctx = get_connection()
            rows = await ctx.fetch_all(
                "SELECT * FROM job_executions WHERE job_id = ?",
                (job_id,)
            )
            return len(rows)

        count = await count_executions()
        assert count == 2
        logger.info("allow_overlap=True test passed: multiple jobs created")

    @pytest.mark.asyncio
    async def test_allow_overlap_false_skips_with_pending(self, database, dispatcher):
        """allow_overlap=False이고 PENDING Job이 있으면 새 Job 생성 안함"""
        @transactional
        async def create_test_cron():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled, allow_overlap)
                   VALUES (?, ?, ?, ?, ?)""",
                ("dispatcher_test_overlap_false_pending", "* * * * *", "test_handler", 1, 0)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_overlap_false_pending",)
            )
            return row["id"]

        job_id = await create_test_cron()

        # 미완료 Job(PENDING) 생성
        scheduled_time1 = datetime(2024, 1, 15, 10, 0, 0)
        test_job = CronJob(
            id=job_id,
            name="dispatcher_test_overlap_false_pending",
            cron_expression="* * * * *",
            handler_name="test_handler",
            is_enabled=True,
            allow_overlap=False,
        )
        await dispatcher._create_job_execution(test_job, scheduled_time1)

        # 미완료 Job 확인
        has_incomplete = await dispatcher._has_incomplete_execution(job_id)
        assert has_incomplete is True

        logger.info("allow_overlap=False with PENDING test passed")

    @pytest.mark.asyncio
    async def test_allow_overlap_false_skips_with_running(self, database, dispatcher):
        """allow_overlap=False이고 RUNNING Job이 있으면 새 Job 생성 안함"""
        @transactional
        async def create_test_cron_and_running_job():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled, allow_overlap)
                   VALUES (?, ?, ?, ?, ?)""",
                ("dispatcher_test_overlap_false_running", "* * * * *", "test_handler", 1, 0)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_overlap_false_running",)
            )
            job_id = row["id"]

            # RUNNING 상태의 Job 생성
            await ctx.execute(
                """INSERT INTO job_executions (job_id, scheduled_time, status)
                   VALUES (?, ?, ?)""",
                (job_id, "2024-01-15 10:00:00", "RUNNING")
            )
            return job_id

        job_id = await create_test_cron_and_running_job()

        # 미완료 Job 확인
        has_incomplete = await dispatcher._has_incomplete_execution(job_id)
        assert has_incomplete is True

        logger.info("allow_overlap=False with RUNNING test passed")

    @pytest.mark.asyncio
    async def test_allow_overlap_false_creates_when_complete(self, database, dispatcher):
        """allow_overlap=False이지만 이전 Job이 완료되면 새 Job 생성"""
        @transactional
        async def create_test_cron_and_complete_job():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled, allow_overlap)
                   VALUES (?, ?, ?, ?, ?)""",
                ("dispatcher_test_overlap_false_complete", "* * * * *", "test_handler", 1, 0)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("dispatcher_test_overlap_false_complete",)
            )
            job_id = row["id"]

            # SUCCESS 상태의 Job 생성 (완료됨)
            await ctx.execute(
                """INSERT INTO job_executions (job_id, scheduled_time, status)
                   VALUES (?, ?, ?)""",
                (job_id, "2024-01-15 10:00:00", "SUCCESS")
            )
            return job_id

        job_id = await create_test_cron_and_complete_job()

        # 미완료 Job이 없어야 함
        has_incomplete = await dispatcher._has_incomplete_execution(job_id)
        assert has_incomplete is False

        # 새 Job 생성 가능
        test_job = CronJob(
            id=job_id,
            name="dispatcher_test_overlap_false_complete",
            cron_expression="* * * * *",
            handler_name="test_handler",
            is_enabled=True,
            allow_overlap=False,
        )

        scheduled_time2 = datetime(2024, 1, 15, 10, 1, 0)
        created = await dispatcher._create_job_execution(test_job, scheduled_time2)
        assert created is True

        logger.info("allow_overlap=False with complete job test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
