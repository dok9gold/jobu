"""
MySQL 데이터베이스 테스트

Docker 환경에서 실행:
    cd docker && docker-compose up -d mysql
    python -m pytest test/database/test_mysql.py -v

테스트 항목:
1. 커넥션 풀 테스트
2. 트랜잭션 테스트 (데코레이터)
3. 수동 트랜잭션 (begin, commit, rollback)
4. readOnly 모드 테스트
5. CRUD 테스트
"""

import asyncio
import logging
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from database import (
    transactional,
    transactional_readonly,
    get_connection,
    get_db,
    ReadOnlyTransactionError,
)
from database.mysql import MySQLDatabase
from database.registry import DatabaseRegistry

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Docker mysql 실행 여부 확인
def is_mysql_available():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', 3306))
    sock.close()
    return result == 0


pytestmark = pytest.mark.skipif(
    not is_mysql_available(),
    reason="MySQL not available (run: cd docker && docker-compose up -d mysql)"
)


@pytest_asyncio.fixture
async def mysql_config():
    """MySQL 테스트 설정"""
    return {
        'databases': {
            'mysql_test': {
                'type': 'mysql',
                'host': 'localhost',
                'port': 3306,
                'database': 'jobu',
                'user': 'jobu',
                'password': 'jobu_dev',
                'pool': {
                    'minsize': 2,
                    'maxsize': 5,
                },
                'options': {
                    'charset': 'utf8mb4',
                    'autocommit': False,
                }
            }
        }
    }


@pytest_asyncio.fixture
async def database(mysql_config):
    """테스트용 MySQLDatabase 인스턴스"""
    DatabaseRegistry.clear()
    await DatabaseRegistry.init_from_config(mysql_config)
    db = get_db('mysql_test')

    # 테스트 테이블 정리
    async with db.transaction() as ctx:
        await ctx.execute("DELETE FROM cron_jobs WHERE name LIKE %s", ('test_%',))

    yield db
    await DatabaseRegistry.close_all()


class TestMySQLConnectionPool:
    """MySQL 커넥션 풀 테스트"""

    @pytest.mark.asyncio
    async def test_pool_initialization(self, database):
        """커넥션 풀 초기화 테스트"""
        pool = database.pool
        assert pool is not None
        logger.info("MySQL pool initialized")

    @pytest.mark.asyncio
    async def test_connection_acquire_release(self, database):
        """커넥션 획득/반환 테스트"""
        pool = database.pool
        conn = await pool.acquire()
        assert conn is not None
        pool.release(conn)
        logger.info("Connection acquire/release test passed")


class TestMySQLTransaction:
    """MySQL 트랜잭션 테스트"""

    @pytest.mark.asyncio
    async def test_transactional_decorator_commit(self, database):
        """트랜잭션 데코레이터 커밋 테스트"""
        @transactional(database)
        async def insert_test_data():
            ctx = get_connection('mysql_test')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                ('test_mysql_job', '* * * * *', 'test_handler')
            )
            return True

        result = await insert_test_data()
        assert result is True

        @transactional_readonly(database)
        async def check_data():
            ctx = get_connection('mysql_test')
            row = await ctx.fetch_one(
                "SELECT * FROM cron_jobs WHERE name = %s",
                ('test_mysql_job',)
            )
            return row

        row = await check_data()
        assert row is not None
        assert row['name'] == 'test_mysql_job'
        logger.info("Transactional decorator commit test passed")

    @pytest.mark.asyncio
    async def test_transactional_decorator_rollback(self, database):
        """트랜잭션 데코레이터 롤백 테스트"""
        @transactional(database)
        async def insert_and_fail():
            ctx = get_connection('mysql_test')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                ('test_rollback_job', '* * * * *', 'test_handler')
            )
            raise ValueError("Intentional error for rollback test")

        with pytest.raises(ValueError):
            await insert_and_fail()

        @transactional_readonly(database)
        async def check_rollback():
            ctx = get_connection('mysql_test')
            row = await ctx.fetch_one(
                "SELECT * FROM cron_jobs WHERE name = %s",
                ('test_rollback_job',)
            )
            return row

        row = await check_rollback()
        assert row is None
        logger.info("Transactional decorator rollback test passed")

    @pytest.mark.asyncio
    async def test_manual_transaction(self, database):
        """수동 트랜잭션 테스트"""
        async with database.transaction() as ctx:
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                ('test_manual_job', '* * * * *', 'test_handler')
            )

        async with database.transaction(readonly=True) as ctx:
            row = await ctx.fetch_one(
                "SELECT * FROM cron_jobs WHERE name = %s",
                ('test_manual_job',)
            )
            assert row is not None

        logger.info("Manual transaction test passed")


class TestMySQLReadOnly:
    """MySQL 읽기 전용 트랜잭션 테스트"""

    @pytest.mark.asyncio
    async def test_readonly_select(self, database):
        """읽기 전용 SELECT 테스트"""
        @transactional_readonly(database)
        async def select_data():
            ctx = get_connection('mysql_test')
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
            ctx = get_connection('mysql_test')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                ('test_readonly_fail', '0 * * * *', 'test_handler')
            )

        with pytest.raises(ReadOnlyTransactionError):
            await try_write()

        logger.info("ReadOnly write blocked test passed")


class TestMySQLCRUD:
    """MySQL CRUD 테스트"""

    @pytest.mark.asyncio
    async def test_insert_and_fetch(self, database):
        """INSERT, fetch_one, fetch_all 테스트"""
        async with database.transaction() as ctx:
            # INSERT
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                ('test_crud_job', '*/5 * * * *', 'crud_handler')
            )

            # fetch_one
            row = await ctx.fetch_one(
                "SELECT * FROM cron_jobs WHERE name = %s",
                ('test_crud_job',)
            )
            assert row['name'] == 'test_crud_job'
            assert row['cron_expression'] == '*/5 * * * *'

            # fetch_all
            rows = await ctx.fetch_all(
                "SELECT * FROM cron_jobs WHERE name LIKE %s",
                ('test_%',)
            )
            assert len(rows) >= 1

        logger.info("CRUD test passed")

    @pytest.mark.asyncio
    async def test_fetch_val(self, database):
        """fetch_val 단일 값 조회 테스트"""
        async with database.transaction() as ctx:
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                ('test_fetchval_job', '0 0 * * *', 'val_handler')
            )

            count = await ctx.fetch_val(
                "SELECT COUNT(*) FROM cron_jobs WHERE name = %s",
                ('test_fetchval_job',)
            )
            assert count == 1

        logger.info("fetch_val test passed")


class TestMySQLConcurrency:
    """MySQL 동시성 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_transactions(self, database):
        """동시 트랜잭션 테스트"""
        results = []

        @transactional(database)
        async def concurrent_insert(job_name: str):
            ctx = get_connection('mysql_test')
            await ctx.execute(
                "INSERT INTO cron_jobs (name, cron_expression, handler_name) VALUES (%s, %s, %s)",
                (job_name, '* * * * *', 'test_handler')
            )
            results.append(job_name)
            return job_name

        tasks = [
            concurrent_insert(f"test_concurrent_{i}")
            for i in range(3)
        ]
        await asyncio.gather(*tasks)

        assert len(results) == 3

        @transactional_readonly(database)
        async def check_all():
            ctx = get_connection('mysql_test')
            rows = await ctx.fetch_all(
                "SELECT * FROM cron_jobs WHERE name LIKE %s",
                ('test_concurrent_%',)
            )
            return rows

        rows = await check_all()
        assert len(rows) == 3
        logger.info("Concurrent transactions test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
