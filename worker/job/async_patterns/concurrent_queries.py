"""비동기 DB 동시 쿼리 패턴

asyncio.gather를 사용하여 여러 DB에 동시 쿼리 실행.
비동기 DB 커넥션풀의 실질적 활용 예제.

특징:
- 독립적인 쿼리 여러 개를 동시 실행
- 커넥션 풀에서 여러 커넥션을 사용해 병렬 처리
- 순차 실행 대비 성능 향상 (독립적인 쿼리일 경우)
"""

import asyncio
import logging
import time
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional_readonly, get_connection, get_db

logger = logging.getLogger(__name__)

sqlite_queries = aiosql.from_path(Path(__file__).parent / "sql" / "concurrent_queries_sqlite.sql", "aiosqlite")
pg_queries = aiosql.from_path(Path(__file__).parent / "sql" / "concurrent_queries_postgres.sql", "asyncpg")
mysql_queries = aiosql.from_path(Path(__file__).parent / "sql" / "concurrent_queries_mysql.sql", "asyncmy")


async def fetch_sqlite_stats() -> dict:
    """SQLite에서 통계 조회"""
    db = get_db('sqlite_2')

    @transactional_readonly(db)
    async def query():
        ctx = get_connection('sqlite_2')
        count = await sqlite_queries.count_sample_data(ctx.connection)
        rows = await sqlite_queries.get_sample_data(ctx.connection)
        return {"count": count, "recent": [dict(r) for r in rows]}

    return await query()


async def fetch_postgres_stats() -> dict:
    """PostgreSQL에서 통계 조회"""
    db = get_db('postgres_1')

    @transactional_readonly(db)
    async def query():
        ctx = get_connection('postgres_1')
        count = await pg_queries.count_sample_data(ctx.connection)
        by_handler = await pg_queries.count_by_handler(ctx.connection)
        return {"count": count, "by_handler": [dict(r) for r in by_handler]}

    return await query()


async def fetch_mysql_stats() -> dict:
    """MySQL에서 통계 조회"""
    db = get_db('mysql_1')

    @transactional_readonly(db)
    async def query():
        ctx = get_connection('mysql_1')
        count = await mysql_queries.count_sample_data(ctx.connection)
        by_handler = await mysql_queries.count_by_handler(ctx.connection)
        return {"count": count, "by_handler": [dict(r) for r in by_handler]}

    return await query()


@handler("concurrent_queries")
class ConcurrentQueriesHandler(BaseHandler):
    """비동기 DB 동시 쿼리 예제

    3개 DB(SQLite, PostgreSQL, MySQL)에서 동시에 통계를 조회.
    asyncio.gather로 병렬 실행하여 총 소요시간 단축.
    """

    async def execute(self, params: HandlerParams) -> HandlerResult:
        start_time = time.perf_counter()

        if params.action == 'sequential':
            # 순차 실행 (비교용)
            sqlite_stats = await fetch_sqlite_stats()
            pg_stats = await fetch_postgres_stats()
            mysql_stats = await fetch_mysql_stats()
        else:
            # 동시 실행 (기본)
            sqlite_stats, pg_stats, mysql_stats = await asyncio.gather(
                fetch_sqlite_stats(),
                fetch_postgres_stats(),
                fetch_mysql_stats(),
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"ConcurrentQueriesHandler: fetched stats from 3 DBs "
            f"(mode={params.action}, elapsed={elapsed_ms:.2f}ms)"
        )

        return HandlerResult(
            action=params.action,
            data={
                "sqlite": sqlite_stats,
                "postgres": pg_stats,
                "mysql": mysql_stats,
                "elapsed_ms": round(elapsed_ms, 2),
                "mode": "sequential" if params.action == 'sequential' else "concurrent",
            }
        )
