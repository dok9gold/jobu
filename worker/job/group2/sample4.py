"""Sample4 Handler - MySQL 단일 DB CRUD"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, transactional_readonly, get_connection, get_db

logger = logging.getLogger(__name__)

queries = aiosql.from_path(Path(__file__).parent / "sql" / "mysql.sql", "asyncmy")


@handler("sample4")
class Sample4Handler(BaseHandler):
    """MySQL 단일 DB CRUD 예제"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        db = get_db('mysql_1')

        if params.action == 'write':
            @transactional(db)
            async def write_data():
                ctx = get_connection('mysql_1')
                await queries.insert_sample_data(
                    ctx.connection,
                    name=params.name or 'test',
                    value=params.value or '',
                    writer_handler='sample4'
                )
                return await queries.get_last_insert_id(ctx.connection)

            data_id = await write_data()
            logger.info(f"Sample4Handler: wrote data id={data_id}")
            return HandlerResult(action='write', id=data_id, data={"db": "mysql"})

        else:  # read
            @transactional_readonly(db)
            async def read_data():
                ctx = get_connection('mysql_1')
                return await queries.get_sample_data(ctx.connection)

            rows = await read_data()
            logger.info(f"Sample4Handler: read {len(rows)} rows")
            return HandlerResult(action='read', count=len(rows), data={"db": "mysql", "rows": rows})
