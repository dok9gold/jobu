"""do_work 패턴 예제 (심플)

하나의 함수에 @transactional 붙이고, execute는 그 함수만 호출.
가장 단순한 트랜잭션 분리 패턴.

핵심:
- 트랜잭션 경계가 do_work 함수에 있음
- 모든 비즈니스 로직을 do_work 안에서 처리
- 성공하면 커밋, 예외 발생하면 롤백
"""

import logging
from pathlib import Path

import aiosql

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from database import transactional, get_connection, get_db

logger = logging.getLogger(__name__)

queries = aiosql.from_path(Path(__file__).parent / "sql" / "do_work_pattern.sql", "aiosqlite")


async def do_work(params: HandlerParams) -> HandlerResult:
    """트랜잭션 경계가 여기

    모든 비즈니스 로직을 이 함수 안에서 처리.
    성공하면 커밋, 예외 발생하면 롤백.
    """
    db = get_db('sqlite_2')

    @transactional(db)
    async def _execute():
        ctx = get_connection('sqlite_2')

        if params.action == 'write':
            await queries.insert_sample_data(
                ctx.connection,
                name=params.name or 'test',
                value=params.value or '',
                writer_handler='do_work_pattern'
            )
            data_id = await queries.get_last_insert_id(ctx.connection)
            return HandlerResult(action='write', id=data_id)

        else:  # read
            rows = await queries.get_sample_data(ctx.connection)
            return HandlerResult(action='read', count=len(rows), data=[dict(r) for r in rows])

    return await _execute()


@handler("do_work_pattern")
class DoWorkPatternHandler(BaseHandler):
    """do_work 패턴 예제 (심플)

    execute는 do_work만 호출.
    트랜잭션 관리는 do_work 내부에서 담당.
    """

    async def execute(self, params: HandlerParams) -> HandlerResult:
        result = await do_work(params)
        logger.info(f"DoWorkPatternHandler: {result.action} completed")
        return result
