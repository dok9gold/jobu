"""Sample3 Handler - SQLite(default) -> PostgreSQL 동기화"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, get_connection, get_db

logger = logging.getLogger(__name__)

sqlite_queries = aiosql.from_path(Path(__file__).parent / "sql" / "sqlite.sql", "aiosqlite")
pg_queries = aiosql.from_path(Path(__file__).parent / "sql" / "postgres.sql", "asyncpg")


@handler("sample3")
class Sample3Handler(BaseHandler):
    """SQLite(default) -> PostgreSQL 2개 DB 동기화 예제"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        sqlite_db = get_db('default')
        pg_db = get_db('postgres_1')

        @transactional(sqlite_db, pg_db)
        async def sync_sqlite_to_pg():
            sqlite_ctx = get_connection('default')
            pg_ctx = get_connection('postgres_1')

            rows = await sqlite_queries.get_all_sample_data(sqlite_ctx.connection)

            synced = 0
            for row in rows:
                await pg_queries.upsert_sample_data(
                    pg_ctx.connection,
                    id=row['id'],
                    name=row['name'],
                    value=row['value'],
                    writer_handler='sample3'
                )
                synced += 1

            return synced

        count = await sync_sqlite_to_pg()
        logger.info(f"Sample3Handler: synced {count} rows from sqlite to postgres")
        return HandlerResult(action='sync', count=count, data={"from": "sqlite", "to": "postgres"})
