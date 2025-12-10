"""
MySQL 비동기 커넥션풀 모듈

asyncmy를 사용하여 비동기 MySQL 커넥션풀을 제공합니다.
"""

import logging
from dataclasses import dataclass
from typing import Any

import asyncmy
from asyncmy.cursors import DictCursor

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
    minsize: int = 2
    maxsize: int = 10
    pool_recycle: int = 300


class TransactionContext:
    """MySQL 트랜잭션 컨텍스트 관리 클래스"""

    def __init__(self, connection: asyncmy.Connection, readonly: bool = False):
        self._connection = connection
        self._readonly = readonly
        self._in_transaction = False

    @property
    def connection(self) -> asyncmy.Connection:
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
        await self._connection.begin()
        self._in_transaction = True
        logger.debug("Transaction started (manual mode)")

    async def commit(self) -> None:
        """트랜잭션 커밋"""
        if not self._in_transaction:
            logger.warning("No active transaction to commit")
            return
        await self._connection.commit()
        self._in_transaction = False
        logger.debug("Transaction committed")

    async def rollback(self) -> None:
        """트랜잭션 롤백"""
        if not self._in_transaction:
            logger.warning("No active transaction to rollback")
            return
        await self._connection.rollback()
        self._in_transaction = False
        logger.debug("Transaction rolled back")

    async def execute(self, sql: str, parameters: Any = None) -> int:
        """SQL 실행 (INSERT, UPDATE, DELETE 등) - affected rows 반환"""
        if self._readonly and self._is_write_query(sql):
            raise ReadOnlyTransactionError("Cannot execute write query in readonly transaction")

        _log_query(sql, parameters)
        async with self._connection.cursor(DictCursor) as cursor:
            if parameters:
                await cursor.execute(sql, parameters)
            else:
                await cursor.execute(sql)
            return cursor.rowcount

    async def executemany(self, sql: str, parameters: list) -> int:
        """다중 SQL 실행"""
        if self._readonly and self._is_write_query(sql):
            raise ReadOnlyTransactionError("Cannot execute write query in readonly transaction")

        _log_query(sql, f"[{len(parameters)} rows]")
        async with self._connection.cursor(DictCursor) as cursor:
            await cursor.executemany(sql, parameters)
            return cursor.rowcount

    async def fetch_one(self, sql: str, parameters: Any = None) -> dict | None:
        """단일 행 조회"""
        _log_query(sql, parameters)
        async with self._connection.cursor(DictCursor) as cursor:
            if parameters:
                await cursor.execute(sql, parameters)
            else:
                await cursor.execute(sql)
            row = await cursor.fetchone()
            _log_result(1 if row else 0)
            return row

    async def fetch_all(self, sql: str, parameters: Any = None) -> list[dict]:
        """모든 행 조회"""
        _log_query(sql, parameters)
        async with self._connection.cursor(DictCursor) as cursor:
            if parameters:
                await cursor.execute(sql, parameters)
            else:
                await cursor.execute(sql)
            rows = await cursor.fetchall()
            _log_result(len(rows))
            return list(rows)

    async def fetch_val(self, sql: str, parameters: Any = None) -> Any:
        """단일 값 조회"""
        _log_query(sql, parameters)
        async with self._connection.cursor() as cursor:
            if parameters:
                await cursor.execute(sql, parameters)
            else:
                await cursor.execute(sql)
            row = await cursor.fetchone()
            return row[0] if row else None

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
    """MySQL 트랜잭션 컨텍스트 매니저"""

    def __init__(self, db: 'MySQLDatabase', readonly: bool = False):
        self._db = db
        self._readonly = readonly
        self._connection: asyncmy.Connection | None = None
        self._ctx: TransactionContext | None = None

    async def __aenter__(self) -> TransactionContext:
        try:
            self._connection = await self._db.pool.acquire()
        except Exception as e:
            raise ConnectionPoolExhaustedError(f"Failed to acquire connection: {e}")

        self._ctx = TransactionContext(self._connection, self._readonly)
        await self._connection.begin()
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
            self._db.pool.release(self._connection)


class MySQLDatabase(BaseDatabase):
    """
    MySQL 데이터베이스 구현

    사용 예시:
        db = await MySQLDatabase.create('mysql_main', config)

        @transactional(db)
        async def create_job(job_data):
            ctx = get_connection('mysql_main')
            await ctx.execute("INSERT INTO ... VALUES (%s, %s)", (val1, val2))

        async with db.transaction() as ctx:
            await ctx.execute(...)
    """

    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name)
        self._config = config
        self._pool: asyncmy.Pool | None = None

    @classmethod
    async def create(cls, name: str, config: dict[str, Any]) -> 'MySQLDatabase':
        """MySQLDatabase 인스턴스 생성 및 초기화"""
        instance = cls(name, config)
        await instance._initialize()
        return instance

    async def _initialize(self) -> None:
        """내부 초기화"""
        pool_cfg = self._config.get('pool', {})
        pool_config = PoolConfig(
            minsize=pool_cfg.get('minsize', 2),
            maxsize=pool_cfg.get('maxsize', 10),
            pool_recycle=int(pool_cfg.get('pool_recycle', 300)),
        )

        opts = self._config.get('options', {})

        self._pool = await asyncmy.create_pool(
            host=self._config.get('host', 'localhost'),
            port=self._config.get('port', 3306),
            db=self._config.get('database', 'jobu'),
            user=self._config.get('user', 'jobu'),
            password=self._config.get('password', ''),
            minsize=pool_config.minsize,
            maxsize=pool_config.maxsize,
            pool_recycle=pool_config.pool_recycle,
            charset=opts.get('charset', 'utf8mb4'),
            autocommit=opts.get('autocommit', False),
        )

        logger.info(
            f"MySQLDatabase '{self.name}' initialized "
            f"(pool: {pool_config.minsize}-{pool_config.maxsize})"
        )

    def transaction(self, readonly: bool = False) -> ManagedTransaction:
        """트랜잭션 컨텍스트 매니저 반환"""
        return ManagedTransaction(self, readonly)

    @property
    def pool(self) -> asyncmy.Pool:
        """커넥션풀 반환"""
        if self._pool is None:
            raise RuntimeError(f"Database '{self.name}' not initialized")
        return self._pool

    async def close(self) -> None:
        """데이터베이스 연결 종료"""
        if self._pool:
            self._pool.close()
            await self._pool.wait_closed()
        logger.info(f"MySQLDatabase '{self.name}' closed")
