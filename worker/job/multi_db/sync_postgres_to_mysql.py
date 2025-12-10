"""PostgreSQL -> MySQL 동기화 예제

멀티 DB 트랜잭션 예제: PostgreSQL에서 MySQL로 데이터 동기화.
@transactional 데코레이터에 여러 DB를 넘기면 모두 커밋 또는 모두 롤백.
"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, get_connection, get_db

logger = logging.getLogger(__name__)

pg_queries = aiosql.from_path(Path(__file__).parent / "sql" / "sync_postgres_to_mysql_postgres.sql", "asyncpg")
mysql_queries = aiosql.from_path(Path(__file__).parent / "sql" / "sync_postgres_to_mysql_mysql.sql", "asyncmy")


@handler("sync_postgres_to_mysql")
class SyncPostgresToMysqlHandler(BaseHandler):
    """PostgreSQL -> MySQL 2개 DB 동기화 예제"""

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
                    writer_handler='sync_postgres_to_mysql'
                )
                synced_count += 1

            return synced_count

        count = await sync_data()
        logger.info(f"SyncPostgresToMysqlHandler: synced {count} rows from PostgreSQL to MySQL")
        return HandlerResult(action='sync', count=count, data={"from": "postgres", "to": "mysql"})
