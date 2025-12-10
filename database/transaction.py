"""
트랜잭션 데코레이터

다중 DB 트랜잭션을 위한 데코레이터를 제공합니다.
DB 종류(SQLite, PostgreSQL 등)에 관계없이 동작합니다.
"""

import functools
from collections.abc import Callable
from contextlib import AsyncExitStack

from database.base import BaseDatabase


def transactional(*dbs: BaseDatabase, readonly: bool = False) -> Callable:
    """
    다중 DB 트랜잭션 데코레이터

    사용 예시:
        @transactional(jobu_db)
        async def create_job(...):
            ctx = get_connection('jobu')
            ...

        @transactional(jobu_db, biz_db)
        async def sync_data(...):
            jobu_ctx = get_connection('jobu')
            biz_ctx = get_connection('biz')
            ...

        # 하위 호환: 인자 없이 사용 시 default DB 사용
        @transactional
        async def create_job(...):
            ctx = get_connection()  # default
            ...
    """
    # @transactional (인자 없이) 호환성 - default DB 사용
    # lazy evaluation으로 모듈 로드 시점이 아닌 실행 시점에 DB 조회
    if len(dbs) == 1 and callable(dbs[0]) and not isinstance(dbs[0], BaseDatabase):
        func = dbs[0]

        @functools.wraps(func)
        async def wrapper_default(*args, **kwargs):
            from database.registry import DatabaseRegistry
            db = DatabaseRegistry.get('default')
            async with db.transaction(readonly=readonly):
                return await func(*args, **kwargs)
        return wrapper_default

    # 명시적 DB 지정
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            async with AsyncExitStack() as stack:
                for db in dbs:
                    await stack.enter_async_context(
                        db.transaction(readonly=readonly)
                    )
                return await func(*args, **kwargs)
        return wrapper

    return decorator


def transactional_readonly(*dbs: BaseDatabase) -> Callable:
    """
    읽기 전용 다중 DB 트랜잭션 데코레이터

    쓰기 쿼리 실행 시 ReadOnlyTransactionError를 발생시킵니다.
    """
    # @transactional_readonly (인자 없이) 호환성
    if len(dbs) == 1 and callable(dbs[0]) and not isinstance(dbs[0], BaseDatabase):
        func = dbs[0]

        @functools.wraps(func)
        async def wrapper_default(*args, **kwargs):
            from database.registry import DatabaseRegistry
            db = DatabaseRegistry.get('default')
            async with db.transaction(readonly=True):
                return await func(*args, **kwargs)
        return wrapper_default

    return transactional(*dbs, readonly=True)
