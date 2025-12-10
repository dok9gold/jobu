"""Sample5 Handler - PostgreSQL -> MySQL 데이터 동기화 (2개 DB 트랜잭션)"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, get_connection, get_db

logger = logging.getLogger(__name__)

pg_queries = aiosql.from_path(
    Path(__file__).parent.parent / "group1" / "sql" / "postgres.sql", "asyncpg"
)
mysql_queries = aiosql.from_path(Path(__file__).parent / "sql" / "mysql.sql", "asyncmy")


@handler("sample5")
class Sample5Handler(BaseHandler):
    """PostgreSQL -> MySQL 데이터 동기화 예제 (2개 DB 트랜잭션)"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        pg_db = get_db('postgres_1')
        mysql_db = get_db('mysql_1')

        @transactional(pg_db, mysql_db)
        async def sync_data():
            pg_ctx = get_connection('postgres_1')
            mysql_ctx = get_connection('mysql_1')

            pg_rows = await pg_queries.get_all_sample_data(pg_ctx.connection)

            synced_count = 0
            for row in pg_rows:
                await mysql_queries.upsert_sample_data(
                    mysql_ctx.connection,
                    id=row['id'],
                    name=row['name'],
                    value=row['value'],
                    writer_handler='sample5_sync'
                )
                synced_count += 1

            return synced_count

        count = await sync_data()
        logger.info(f"Sample5Handler: synced {count} rows from PostgreSQL to MySQL")
        return HandlerResult(action='sync', count=count, data={"from": "postgres", "to": "mysql"})
