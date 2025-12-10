"""Sample6 Handler - 3개 DB 리포트 (SQLite, PostgreSQL, MySQL)"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional_readonly, get_connection, get_db

logger = logging.getLogger(__name__)

sqlite_queries = aiosql.from_path(
    Path(__file__).parent.parent / "group1" / "sql" / "sqlite.sql", "aiosqlite"
)
pg_queries = aiosql.from_path(
    Path(__file__).parent.parent / "group1" / "sql" / "postgres.sql", "asyncpg"
)
mysql_queries = aiosql.from_path(Path(__file__).parent / "sql" / "mysql.sql", "asyncmy")


@handler("sample6")
class Sample6Handler(BaseHandler):
    """3개 DB에서 데이터 집계 리포트 예제"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        sqlite_db = get_db('sqlite_2')
        pg_db = get_db('postgres_1')
        mysql_db = get_db('mysql_1')

        @transactional_readonly(sqlite_db, pg_db, mysql_db)
        async def gather_report():
            sqlite_ctx = get_connection('sqlite_2')
            pg_ctx = get_connection('postgres_1')
            mysql_ctx = get_connection('mysql_1')

            sqlite_count = await sqlite_queries.count_sample_data(sqlite_ctx.connection)
            pg_count = await pg_queries.count_sample_data(pg_ctx.connection)
            mysql_count = await mysql_queries.count_sample_data(mysql_ctx.connection)

            sqlite_by_handler = await sqlite_queries.count_by_handler(sqlite_ctx.connection)
            pg_by_handler = await pg_queries.count_by_handler(pg_ctx.connection)
            mysql_by_handler = await mysql_queries.count_by_handler(mysql_ctx.connection)

            return {
                "counts": {
                    "sqlite": sqlite_count,
                    "postgres": pg_count,
                    "mysql": mysql_count,
                    "total": sqlite_count + pg_count + mysql_count
                },
                "by_handler": {
                    "sqlite": [dict(r) for r in sqlite_by_handler],
                    "postgres": [dict(r) for r in pg_by_handler],
                    "mysql": [dict(r) for r in mysql_by_handler]
                }
            }

        report = await gather_report()
        logger.info(f"Sample6Handler: report generated, total={report['counts']['total']}")
        return HandlerResult(action='report', data=report)
