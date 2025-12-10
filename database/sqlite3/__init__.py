"""
SQLite3 비동기 데이터베이스 패키지

사용 예시:
    from database import transactional, get_connection
    from database.registry import DatabaseRegistry

    # 초기화 (config에서)
    await DatabaseRegistry.init_from_config(config)
    db = DatabaseRegistry.get('default')

    # 트랜잭션 데코레이터
    @transactional(db)
    async def create_job(job_data):
        ctx = get_connection('default')
        await ctx.execute("INSERT INTO ...")

    # 수동 트랜잭션
    async with db.transaction() as ctx:
        await ctx.execute("INSERT INTO ...")
"""

from database.sqlite3.connection import (
    SQLiteDatabase,
    Database,
    AsyncConnectionPool,
    TransactionContext,
    ManagedTransaction,
    PoolConfig,
    SqliteOptions,
    PooledConnection,
)

__all__ = [
    'SQLiteDatabase',
    'Database',
    'AsyncConnectionPool',
    'TransactionContext',
    'ManagedTransaction',
    'PoolConfig',
    'SqliteOptions',
    'PooledConnection',
]
