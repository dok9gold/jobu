"""
PostgreSQL 비동기 커넥션풀 모듈

asyncpg를 사용하여 비동기 PostgreSQL 커넥션풀을 제공합니다.
"""

import logging
from dataclasses import dataclass
from typing import Any

import asyncpg

from database.base import BaseDatabase
from database.context import set_connection, clear_connection
from database.exception import (
    ConnectionPoolExhaustedError,
    ReadOnlyTransactionError,
)

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """커넥션풀 설정"""
    min_size: int = 2
    max_size: int = 10
    max_inactive_connection_lifetime: float = 300.0
    command_timeout: float = 60.0


class TransactionContext:
    """PostgreSQL 트랜잭션 컨텍스트 관리 클래스"""

    def __init__(self, connection: asyncpg.Connection, readonly: bool = False):
        self._connection = connection
        self._readonly = readonly
        self._in_transaction = False
        self._transaction: asyncpg.connection.transaction.Transaction | None = None

    @property
    def connection(self) -> asyncpg.Connection:
        return self._connection

    @property
    def readonly(self) -> bool:
        return self._readonly

    @property
    def in_transaction(self) -> bool:
        return self._in_transaction

    async def begin(self) -> None:
        """트랜잭션 시작 (수동 모드)"""
        if self._in_transaction:
            logger.warning("Transaction already started")
            return
        if self._readonly:
            self._transaction = self._connection.transaction(readonly=True)
        else:
            self._transaction = self._connection.transaction()
        await self._transaction.start()
        self._in_transaction = True
        logger.debug("Transaction started (manual mode)")

    async def commit(self) -> None:
        """트랜잭션 커밋"""
        if not self._in_transaction:
            logger.warning("No active transaction to commit")
            return
        if self._transaction:
            await self._transaction.commit()
        self._in_transaction = False
        logger.debug("Transaction committed")

    async def rollback(self) -> None:
        """트랜잭션 롤백"""
        if not self._in_transaction:
            logger.warning("No active transaction to rollback")
            return
        if self._transaction:
            await self._transaction.rollback()
        self._in_transaction = False
        logger.debug("Transaction rolled back")

    async def execute(self, sql: str, *args) -> str:
        """SQL 실행 (INSERT, UPDATE, DELETE 등)"""
        if self._readonly and self._is_write_query(sql):
            raise ReadOnlyTransactionError("Cannot execute write query in readonly transaction")

        _log_query(sql, args)
        result = await self._connection.execute(sql, *args)
        return result

    async def executemany(self, sql: str, args: list) -> None:
        """다중 SQL 실행"""
        if self._readonly and self._is_write_query(sql):
            raise ReadOnlyTransactionError("Cannot execute write query in readonly transaction")

        _log_query(sql, f"[{len(args)} rows]")
        await self._connection.executemany(sql, args)

    async def fetch_one(self, sql: str, *args) -> asyncpg.Record | None:
        """단일 행 조회"""
        _log_query(sql, args)
        row = await self._connection.fetchrow(sql, *args)
        _log_result(1 if row else 0)
        return row

    async def fetch_all(self, sql: str, *args) -> list[asyncpg.Record]:
        """모든 행 조회"""
        _log_query(sql, args)
        rows = await self._connection.fetch(sql, *args)
        _log_result(len(rows))
        return rows

    async def fetch_val(self, sql: str, *args) -> Any:
        """단일 값 조회"""
        _log_query(sql, args)
        value = await self._connection.fetchval(sql, *args)
        return value

    def _is_write_query(self, sql: str) -> bool:
        """쓰기 쿼리인지 확인"""
        sql_upper = sql.strip().upper()
        write_keywords = ('INSERT', 'UPDATE', 'DELETE', 'CREATE', 'DROP', 'ALTER', 'TRUNCATE')
        return sql_upper.startswith(write_keywords)


def _log_query(sql: str, parameters: Any = None) -> None:
    """SQL 쿼리 로깅"""
    sql_oneline = ' '.join(sql.split())
    if parameters:
        logger.debug(f"[SQL] {sql_oneline} | params: {parameters}")
    else:
        logger.debug(f"[SQL] {sql_oneline}")


def _log_result(row_count: int) -> None:
    """SQL 결과 로깅"""
    logger.debug(f"[SQL Result] {row_count} row(s)")


class ManagedTransaction:
    """PostgreSQL 트랜잭션 컨텍스트 매니저"""

    def __init__(self, db: 'PostgresDatabase', readonly: bool = False):
        self._db = db
        self._readonly = readonly
        self._connection: asyncpg.Connection | None = None
        self._ctx: TransactionContext | None = None

    async def __aenter__(self) -> TransactionContext:
        try:
            self._connection = await self._db.pool.acquire()
        except Exception as e:
            raise ConnectionPoolExhaustedError(f"Failed to acquire connection: {e}")

        self._ctx = TransactionContext(self._connection, self._readonly)

        if self._readonly:
            self._ctx._transaction = self._connection.transaction(readonly=True)
        else:
            self._ctx._transaction = self._connection.transaction()
        await self._ctx._transaction.start()
        self._ctx._in_transaction = True

        set_connection(self._db.name, self._ctx)
        return self._ctx

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        try:
            if exc_type:
                await self._ctx.rollback()
            else:
                await self._ctx.commit()
        finally:
            clear_connection(self._db.name)
            await self._db.pool.release(self._connection)


class PostgresDatabase(BaseDatabase):
    """
    PostgreSQL 데이터베이스 구현

    사용 예시:
        db = await PostgresDatabase.create('postgres_main', config)

        @transactional(db)
        async def create_job(job_data):
            ctx = get_connection('postgres_main')
            await ctx.execute("INSERT INTO ... VALUES ($1, $2)", val1, val2)

        async with db.transaction() as ctx:
            await ctx.execute(...)
    """

    db_type: str = "postgres"

    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name)
        self._config = config
        self._pool: asyncpg.Pool | None = None
        self._queries: dict[str, Any] = {}

    @classmethod
    async def create(cls, name: str, config: dict[str, Any]) -> 'PostgresDatabase':
        """PostgresDatabase 인스턴스 생성 및 초기화"""
        instance = cls(name, config)
        await instance._initialize()
        return instance

    async def _initialize(self) -> None:
        """내부 초기화"""
        pool_cfg = self._config.get('pool', {})
        pool_config = PoolConfig(
            min_size=pool_cfg.get('min_size', 2),
            max_size=pool_cfg.get('max_size', 10),
            max_inactive_connection_lifetime=pool_cfg.get('max_inactive_connection_lifetime', 300.0),
            command_timeout=pool_cfg.get('command_timeout', 60.0),
        )

        opts = self._config.get('options', {})

        # DSN 또는 개별 파라미터로 연결
        dsn = self._config.get('dsn')
        if dsn:
            self._pool = await asyncpg.create_pool(
                dsn,
                min_size=pool_config.min_size,
                max_size=pool_config.max_size,
                max_inactive_connection_lifetime=pool_config.max_inactive_connection_lifetime,
                command_timeout=pool_config.command_timeout,
            )
        else:
            self._pool = await asyncpg.create_pool(
                host=self._config.get('host', 'localhost'),
                port=self._config.get('port', 5432),
                database=self._config.get('database', 'jobu'),
                user=self._config.get('user', 'jobu'),
                password=self._config.get('password', ''),
                min_size=pool_config.min_size,
                max_size=pool_config.max_size,
                max_inactive_connection_lifetime=pool_config.max_inactive_connection_lifetime,
                command_timeout=pool_config.command_timeout,
                ssl=opts.get('ssl', False),
                server_settings={
                    'timezone': opts.get('timezone', 'UTC'),
                },
            )

        logger.info(
            f"PostgresDatabase '{self.name}' initialized "
            f"(pool: {pool_config.min_size}-{pool_config.max_size})"
        )

    def transaction(self, readonly: bool = False) -> ManagedTransaction:
        """트랜잭션 컨텍스트 매니저 반환"""
        return ManagedTransaction(self, readonly)

    @property
    def pool(self) -> asyncpg.Pool:
        """커넥션풀 반환"""
        if self._pool is None:
            raise RuntimeError(f"Database '{self.name}' not initialized")
        return self._pool

    def load_queries(self, name: str, sql_path: str) -> Any:
        """aiosql로 SQL 파일 로드"""
        import aiosql
        from database import get_aiosql_adapter
        queries = aiosql.from_path(sql_path, get_aiosql_adapter(self.db_type))
        self._queries[name] = queries
        return queries

    def get_queries(self, name: str) -> Any | None:
        """로드된 쿼리 세트 반환"""
        return self._queries.get(name)

    async def close(self) -> None:
        """데이터베이스 연결 종료"""
        if self._pool:
            await self._pool.close()
        logger.info(f"PostgresDatabase '{self.name}' closed")
