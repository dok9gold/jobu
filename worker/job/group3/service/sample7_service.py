"""Sample7 Service - 스프링 스타일 서비스 레이어

트랜잭션 경계가 서비스 메서드 단위로 정의됨.
핸들러(Controller)는 서비스만 호출.
"""

import logging
from pathlib import Path

import aiosql

from database import transactional, transactional_readonly, get_connection, get_db

logger = logging.getLogger(__name__)

queries = aiosql.from_path(Path(__file__).parent.parent / "sql" / "sqlite.sql", "aiosqlite")


def _get_sqlite2():
    """DB 인스턴스 반환 (lazy loading)"""
    return get_db('sqlite_2')


@transactional(_get_sqlite2())
async def create_data(name: str, value: str) -> int:
    """데이터 생성"""
    ctx = get_connection('sqlite_2')
    await queries.insert_sample_data(
        ctx.connection,
        name=name,
        value=value,
        writer_handler='sample7'
    )
    return await queries.get_last_insert_id(ctx.connection)


@transactional_readonly(_get_sqlite2())
async def get_data_list() -> list[dict]:
    """데이터 목록 조회"""
    ctx = get_connection('sqlite_2')
    rows = await queries.get_sample_data(ctx.connection)
    return [dict(r) for r in rows]


@transactional_readonly(_get_sqlite2())
async def get_data_by_id(data_id: int) -> dict | None:
    """ID로 데이터 조회"""
    ctx = get_connection('sqlite_2')
    row = await queries.get_sample_by_id(ctx.connection, id=data_id)
    return dict(row) if row else None


@transactional(_get_sqlite2())
async def update_data(data_id: int, name: str, value: str) -> bool:
    """데이터 수정"""
    ctx = get_connection('sqlite_2')
    affected = await queries.update_sample_data(
        ctx.connection,
        id=data_id,
        name=name,
        value=value
    )
    return affected > 0


@transactional(_get_sqlite2())
async def delete_data(data_id: int) -> bool:
    """데이터 삭제"""
    ctx = get_connection('sqlite_2')
    affected = await queries.delete_sample_data(ctx.connection, id=data_id)
    return affected > 0
