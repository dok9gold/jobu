"""
데이터베이스 패키지

다중 DB 지원을 위한 공통 인터페이스와 유틸리티를 제공합니다.

사용 예시:
    from database import (
        transactional, transactional_readonly, get_connection,
        DatabaseRegistry
    )

    # 초기화
    await DatabaseRegistry.init_from_config(config)

    # 트랜잭션 데코레이터
    @transactional
    async def create_job(job_data):
        ctx = get_connection('default')
        await ctx.execute("INSERT INTO ...")

    # 다중 DB 트랜잭션
    db1 = DatabaseRegistry.get('default')
    db2 = DatabaseRegistry.get('business')

    @transactional(db1, db2)
    async def sync_data():
        ctx1 = get_connection('default')
        ctx2 = get_connection('business')
        ...
"""

from database.base import BaseDatabase
from database.registry import DatabaseRegistry
from database.context import get_connection, set_connection, clear_connection
from database.transaction import transactional, transactional_readonly
from database.exception import (
    DatabaseError,
    ConnectionPoolExhaustedError,
    TransactionError,
    ReadOnlyTransactionError,
    QueryExecutionError,
)

# asyncmy aiosql 어댑터 등록
import database.mysql.aiosql_adapter  # noqa: F401


def get_db(name: str = 'default'):
    """DatabaseRegistry에서 DB 인스턴스 반환 (편의 함수)"""
    return DatabaseRegistry.get(name)


__all__ = [
    'BaseDatabase',
    'DatabaseRegistry',
    'get_connection',
    'set_connection',
    'clear_connection',
    'get_db',
    'transactional',
    'transactional_readonly',
    'DatabaseError',
    'ConnectionPoolExhaustedError',
    'TransactionError',
    'ReadOnlyTransactionError',
    'QueryExecutionError',
]
