"""SQLite 단일 DB CRUD 예제

기본 핸들러 구조와 단일 데이터베이스 트랜잭션 사용법.
Docker 없이 로컬 SQLite 파일로 바로 테스트 가능.
"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, transactional_readonly, get_connection, get_db

logger = logging.getLogger(__name__)

queries = aiosql.from_path(Path(__file__).parent / "sql" / "sqlite_crud.sql", "aiosqlite")


@handler("sqlite_crud")
class SqliteCrudHandler(BaseHandler):
    """SQLite 단일 DB CRUD 예제 - Docker 없이 테스트 가능"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        db = get_db('sqlite_2')

        if params.action == 'write':
            @transactional(db)
            async def write_data():
                ctx = get_connection('sqlite_2')
                await queries.insert_sample_data(
                    ctx.connection,
                    name=params.name or 'test',
                    value=params.value or '',
                    writer_handler='sqlite_crud'
                )
                return await queries.get_last_insert_id(ctx.connection)

            data_id = await write_data()
            logger.info(f"SqliteCrudHandler: wrote data id={data_id}")
            return HandlerResult(action='write', id=data_id)

        else:  # read
            @transactional_readonly(db)
            async def read_data():
                ctx = get_connection('sqlite_2')
                return await queries.get_sample_data(ctx.connection)

            rows = await read_data()
            logger.info(f"SqliteCrudHandler: read {len(rows)} rows")
            return HandlerResult(action='read', count=len(rows), data=[dict(r) for r in rows])
