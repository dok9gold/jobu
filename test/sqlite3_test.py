"""
SQLite3 데이터베이스 테스트

테스트 항목:
1. 커넥션 풀 테스트
2. 트랜잭션 테스트 (데코레이터)
3. 수동 트랜잭션 (begin, commit, rollback)
4. 커넥션 풀 소진 테스트 (타임아웃)
5. readOnly 모드 테스트
6. 로깅 테스트
7. 다중 DB 트랜잭션 테스트

실행: python -m pytest test/sqlite3_test.py -v
"""

import asyncio
import logging
import sys
from pathlib import Path

import pytest
import pytest_asyncio
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import (
    transactional,
    transactional_readonly,
    get_connection,
    get_db,
    ConnectionPoolExhaustedError,
    ReadOnlyTransactionError,
)
from database.sqlite3 import (
    SQLiteDatabase,
    AsyncConnectionPool,
    PoolConfig,
    SqliteOptions,
    Database,  # 하위 호환 별칭
)
from database.registry import DatabaseRegistry

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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

    async with db.transaction() as ctx:
        await ctx.execute(
            "DELETE FROM cron_jobs WHERE name LIKE ? OR name LIKE ? OR name LIKE ? OR name LIKE ?",
            ("test_%", "manual_%", "concurrent_%", "rollback_%")
        )

    yield db
    await DatabaseRegistry.close_all()


class TestConnectionPool:
    """커넥션 풀 관련 테스트"""

    @pytest.mark.asyncio
    async def test_pool_initialization(self, database):
        """커넥션 풀 초기화 테스트"""
        pool = database.pool
        assert pool.size == 5
        assert pool.available == 5
        logger.info(f"Pool initialized: size={pool.size}, available={pool.available}")

    @pytest.mark.asyncio
    async def test_connection_acquire_release(self, database):
        """커넥션 획득/반환 테스트"""
        pool = database.pool

        conn1 = await pool.acquire()
        assert pool.available == 4
        assert conn1.in_use is True

        await pool.release(conn1)
        assert pool.available == 5
        assert conn1.in_use is False

        logger.info("Connection acquire/release test passed")

    @pytest.mark.asyncio
    async def test_multiple_connections(self, database):
        """다중 커넥션 획득 테스트"""
        pool = database.pool
        connections = []

        for i in range(5):
            conn = await pool.acquire()
            connections.append(conn)
            logger.info(f"Acquired connection {i+1}, available: {pool.available}")

        assert pool.available == 0

        for conn in connections:
            await pool.release(conn)

        assert pool.available == 5
        logger.info("Multiple connections test passed")

    @pytest.mark.asyncio
    async def test_get_db_function(self, database):
        """get_db() 함수 테스트"""
        db = get_db('default')
        assert db is database
        logger.info("get_db() function test passed")


class TestTransaction:
    """트랜잭션 테스트"""

    @pytest.mark.asyncio
    async def test_transactional_decorator_commit(self, database):
        """트랜잭션 데코레이터 커밋 테스트"""
        @transactional(database)
        async def insert_test_data():
            ctx = get_connection('default')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
                ("test_job", "* * * * *", "test_handler")
            )
            return True

        result = await insert_test_data()
        assert result is True

        @transactional_readonly(database)
        async def check_data():
            ctx = get_connection('default')
            row = await ctx.fetch_one("SELECT * FROM cron_jobs WHERE name = ?", ("test_job",))
            return row

        row = await check_data()
        assert row is not None
        assert row['name'] == "test_job"
        logger.info("Transactional decorator commit test passed")

    @pytest.mark.asyncio
    async def test_transactional_decorator_rollback(self, database):
        """트랜잭션 데코레이터 롤백 테스트"""
        @transactional(database)
        async def insert_and_fail():
            ctx = get_connection('default')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
                ("rollback_job", "* * * * *", "test_handler")
            )
            raise ValueError("Intentional error for rollback test")

        with pytest.raises(ValueError):
            await insert_and_fail()

        @transactional_readonly(database)
        async def check_rollback():
            ctx = get_connection('default')
            row = await ctx.fetch_one("SELECT * FROM cron_jobs WHERE name = ?", ("rollback_job",))
            return row

        row = await check_rollback()
        assert row is None
        logger.info("Transactional decorator rollback test passed")

    @pytest.mark.asyncio
    async def test_manual_transaction(self, database):
        """수동 트랜잭션 테스트"""
        async with database.transaction() as ctx:
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
                ("manual_job", "* * * * *", "test_handler")
            )

        @transactional_readonly(database)
        async def check_data():
            ctx = get_connection('default')
            row = await ctx.fetch_one("SELECT * FROM cron_jobs WHERE name = ?", ("manual_job",))
            return row

        row = await check_data()
        assert row is not None
        assert row['name'] == "manual_job"
        logger.info("Manual transaction test passed")

    @pytest.mark.asyncio
    async def test_manual_transaction_rollback(self, database):
        """수동 트랜잭션 롤백 테스트 (예외로 롤백)"""
        try:
            async with database.transaction() as ctx:
                await ctx.execute(
                    "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
                    ("manual_rollback_job", "* * * * *", "test_handler")
                )
                raise ValueError("Force rollback")
        except ValueError:
            pass

        @transactional_readonly(database)
        async def check_data():
            ctx = get_connection('default')
            row = await ctx.fetch_one("SELECT * FROM cron_jobs WHERE name = ?", ("manual_rollback_job",))
            return row

        row = await check_data()
        assert row is None
        logger.info("Manual transaction rollback test passed")


class TestReadOnlyTransaction:
    """읽기 전용 트랜잭션 테스트"""

    @pytest.mark.asyncio
    async def test_readonly_select(self, database):
        """읽기 전용 SELECT 테스트"""
        @transactional_readonly(database)
        async def select_data():
            ctx = get_connection('default')
            rows = await ctx.fetch_all("SELECT * FROM cron_jobs")
            return rows

        rows = await select_data()
        assert isinstance(rows, list)
        logger.info("ReadOnly SELECT test passed")

    @pytest.mark.asyncio
    async def test_readonly_write_blocked(self, database):
        """읽기 전용 모드에서 쓰기 차단 테스트"""
        @transactional_readonly(database)
        async def try_write():
            ctx = get_connection('default')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
                ("readonly_fail", "0 * * * *", "test_handler")
            )

        with pytest.raises(ReadOnlyTransactionError):
            await try_write()

        logger.info("ReadOnly write blocked test passed")


class TestConnectionPoolExhaustion:
    """커넥션 풀 소진 테스트"""

    @pytest.mark.asyncio
    async def test_pool_exhaustion_timeout(self, database):
        """커넥션 풀 소진 시 타임아웃 테스트"""
        pool = database.pool
        connections = []

        for _ in range(5):
            conn = await pool.acquire()
            connections.append(conn)

        assert pool.available == 0

        with pytest.raises(ConnectionPoolExhaustedError):
            await pool.acquire(timeout=1.0)

        for conn in connections:
            await pool.release(conn)

        logger.info("Pool exhaustion timeout test passed")

    @pytest.mark.asyncio
    async def test_pool_wait_and_acquire(self, database):
        """커넥션 반환 대기 후 획득 테스트"""
        pool = database.pool
        connections = []

        for _ in range(5):
            conn = await pool.acquire()
            connections.append(conn)

        async def release_after_delay():
            await asyncio.sleep(0.5)
            await pool.release(connections[0])

        release_task = asyncio.create_task(release_after_delay())

        new_conn = await pool.acquire(timeout=2.0)
        assert new_conn is not None

        await release_task
        await pool.release(new_conn)

        for conn in connections[1:]:
            await pool.release(conn)

        logger.info("Pool wait and acquire test passed")


class TestLogging:
    """SQL 로깅 테스트"""

    @pytest.mark.asyncio
    async def test_query_logging(self, database, caplog):
        """쿼리 로깅 테스트"""
        with caplog.at_level(logging.DEBUG):
            @transactional_readonly(database)
            async def execute_query():
                ctx = get_connection('default')
                await ctx.fetch_all("SELECT * FROM cron_jobs WHERE is_enabled = ?", (1,))

            await execute_query()

        log_messages = [record.message for record in caplog.records]
        sql_logged = any("[SQL]" in msg and "SELECT" in msg for msg in log_messages)
        assert sql_logged, "SQL query should be logged"
        logger.info("Query logging test passed")


class TestConcurrency:
    """동시성 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_transactions(self, database):
        """동시 트랜잭션 테스트"""
        results = []

        @transactional(database)
        async def concurrent_insert(job_name: str):
            ctx = get_connection('default')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (?, ?, ?)",
                (job_name, "* * * * *", "test_handler")
            )
            results.append(job_name)
            return job_name

        tasks = [
            concurrent_insert(f"concurrent_job_{i}")
            for i in range(3)
        ]
        await asyncio.gather(*tasks)

        assert len(results) == 3

        @transactional_readonly(database)
        async def check_all():
            ctx = get_connection('default')
            rows = await ctx.fetch_all("SELECT * FROM cron_jobs WHERE name LIKE ?", ("concurrent_job_%",))
            return rows

        rows = await check_all()
        assert len(rows) == 3
        logger.info("Concurrent transactions test passed")


class TestMultiDatabase:
    """다중 DB 트랜잭션 테스트"""

    @pytest_asyncio.fixture
    async def multi_db_setup(self):
        """다중 DB 설정"""
        DatabaseRegistry.clear()

        config = {
            'databases': {
                'default': {
                    'type': 'sqlite',
                    'path': 'data/test_default.db',
                    'pool': {'pool_size': 3}
                },
                'secondary': {
                    'type': 'sqlite',
                    'path': 'data/test_secondary.db',
                    'pool': {'pool_size': 3}
                }
            }
        }

        await DatabaseRegistry.init_from_config(config)
        default_db = get_db('default')
        secondary_db = get_db('secondary')

        async with default_db.transaction() as ctx:
            await ctx.execute("""
                CREATE TABLE IF NOT EXISTS test_items (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            await ctx.execute("DELETE FROM test_items")

        async with secondary_db.transaction() as ctx:
            await ctx.execute("""
                CREATE TABLE IF NOT EXISTS test_items (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """)
            await ctx.execute("DELETE FROM test_items")

        yield default_db, secondary_db

        await DatabaseRegistry.close_all()

        Path('data/test_default.db').unlink(missing_ok=True)
        Path('data/test_secondary.db').unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_multi_db_commit(self, multi_db_setup):
        """다중 DB 커밋 테스트"""
        default_db, secondary_db = multi_db_setup

        @transactional(default_db, secondary_db)
        async def insert_both():
            default_ctx = get_connection('default')
            secondary_ctx = get_connection('secondary')

            await default_ctx.execute("INSERT INTO test_items (name) VALUES (?)", ("item_default",))
            await secondary_ctx.execute("INSERT INTO test_items (name) VALUES (?)", ("item_secondary",))

        await insert_both()

        async with default_db.transaction(readonly=True) as ctx:
            row = await ctx.fetch_one("SELECT * FROM test_items WHERE name = ?", ("item_default",))
            assert row is not None

        async with secondary_db.transaction(readonly=True) as ctx:
            row = await ctx.fetch_one("SELECT * FROM test_items WHERE name = ?", ("item_secondary",))
            assert row is not None

        logger.info("Multi DB commit test passed")

    @pytest.mark.asyncio
    async def test_multi_db_rollback_on_first_db_error(self, multi_db_setup):
        """첫 번째 DB에서 에러 발생 시 모두 롤백"""
        default_db, secondary_db = multi_db_setup

        @transactional(default_db, secondary_db)
        async def insert_and_fail_first():
            default_ctx = get_connection('default')
            secondary_ctx = get_connection('secondary')

            await default_ctx.execute("INSERT INTO test_items (name) VALUES (?)", ("rollback_default",))
            raise ValueError("Error in first DB operation")

        with pytest.raises(ValueError):
            await insert_and_fail_first()

        async with default_db.transaction(readonly=True) as ctx:
            row = await ctx.fetch_one("SELECT * FROM test_items WHERE name = ?", ("rollback_default",))
            assert row is None

        logger.info("Multi DB rollback on first DB error test passed")

    @pytest.mark.asyncio
    async def test_multi_db_rollback_on_second_db_error(self, multi_db_setup):
        """두 번째 DB에서 에러 발생 시 모두 롤백"""
        default_db, secondary_db = multi_db_setup

        @transactional(default_db, secondary_db)
        async def insert_and_fail_second():
            default_ctx = get_connection('default')
            secondary_ctx = get_connection('secondary')

            await default_ctx.execute("INSERT INTO test_items (name) VALUES (?)", ("rollback_default2",))
            await secondary_ctx.execute("INSERT INTO test_items (name) VALUES (?)", ("rollback_secondary2",))
            raise ValueError("Error after both inserts")

        with pytest.raises(ValueError):
            await insert_and_fail_second()

        async with default_db.transaction(readonly=True) as ctx:
            row = await ctx.fetch_one("SELECT * FROM test_items WHERE name = ?", ("rollback_default2",))
            assert row is None

        async with secondary_db.transaction(readonly=True) as ctx:
            row = await ctx.fetch_one("SELECT * FROM test_items WHERE name = ?", ("rollback_secondary2",))
            assert row is None

        logger.info("Multi DB rollback on second DB error test passed")

    @pytest.mark.asyncio
    async def test_database_registry(self, multi_db_setup):
        """DatabaseRegistry 테스트"""
        default_db, secondary_db = multi_db_setup

        assert get_db('default') is default_db
        assert get_db('secondary') is secondary_db

        all_dbs = DatabaseRegistry.get_all()
        assert 'default' in all_dbs
        assert 'secondary' in all_dbs

        with pytest.raises(KeyError):
            get_db('nonexistent')

        logger.info("DatabaseRegistry test passed")

    @pytest.mark.asyncio
    async def test_get_connection_error(self, multi_db_setup):
        """트랜잭션 외부에서 get_connection 호출 시 에러"""
        with pytest.raises(RuntimeError, match="No active transaction"):
            get_connection('default')

        logger.info("get_connection error test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
