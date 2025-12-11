"""
SQLite3 비동기 커넥션풀 모듈

aiosqlite를 사용하여 비동기 SQLite3 커넥션풀을 제공합니다.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite
import aiosql
from aiosql.queries import Queries

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
    pool_size: int = 5
    pool_timeout: float = 30.0
    max_idle_time: float = 300.0


@dataclass
class SqliteOptions:
    """SQLite 연결 옵션"""
    busy_timeout: int = 5000
    journal_mode: str = 'WAL'
    synchronous: str = 'NORMAL'
    cache_size: int = -2000
    foreign_keys: bool = True


@dataclass
class PooledConnection:
    """풀에서 관리되는 연결"""
    connection: aiosqlite.Connection
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: datetime = field(default_factory=datetime.now)
    in_use: bool = False


class TransactionContext:
    """SQLite 트랜잭션 컨텍스트 관리 클래스"""

    def __init__(self, connection: aiosqlite.Connection, readonly: bool = False):
        self._connection = connection
        self._readonly = readonly
        self._in_transaction = False
        self._manual_mode = False

    @property
    def connection(self) -> aiosqlite.Connection:
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
        self._manual_mode = True
        self._in_transaction = True
        if self._readonly:
            await self._connection.execute("BEGIN DEFERRED")
        else:
            await self._connection.execute("BEGIN IMMEDIATE")
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

    async def execute(self, sql: str, parameters: Any = None) -> aiosqlite.Cursor:
        """SQL 실행"""
        if self._readonly and self._is_write_query(sql):
            raise ReadOnlyTransactionError("Cannot execute write query in readonly transaction")

        _log_query(sql, parameters)
        if parameters:
            cursor = await self._connection.execute(sql, parameters)
        else:
            cursor = await self._connection.execute(sql)
        return cursor

    async def executemany(self, sql: str, parameters: list) -> aiosqlite.Cursor:
        """다중 SQL 실행"""
        if self._readonly and self._is_write_query(sql):
            raise ReadOnlyTransactionError("Cannot execute write query in readonly transaction")

        _log_query(sql, f"[{len(parameters)} rows]")
        cursor = await self._connection.executemany(sql, parameters)
        return cursor

    async def fetch_one(self, sql: str, parameters: Any = None) -> aiosqlite.Row | None:
        """단일 행 조회"""
        cursor = await self.execute(sql, parameters)
        row = await cursor.fetchone()
        _log_result(1 if row else 0)
        return row

    async def fetch_all(self, sql: str, parameters: Any = None) -> list[aiosqlite.Row]:
        """모든 행 조회"""
        cursor = await self.execute(sql, parameters)
        rows = await cursor.fetchall()
        _log_result(len(rows))
        return rows

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


class AsyncConnectionPool:
    """비동기 SQLite 커넥션풀 클래스"""

    def __init__(
        self,
        db_path: str,
        pool_config: PoolConfig | None = None,
        sqlite_options: SqliteOptions | None = None
    ):
        self._db_path = Path(db_path)
        self._pool_config = pool_config or PoolConfig()
        self._sqlite_options = sqlite_options or SqliteOptions()

        self._pool: list[PooledConnection] = []
        self._lock = asyncio.Lock()
        self._semaphore: asyncio.Semaphore | None = None
        self._initialized = False
        self._closed = False

        self._cleanup_task: asyncio.Task | None = None

    async def initialize(self) -> None:
        """커넥션풀 초기화"""
        if self._initialized:
            logger.warning("Connection pool already initialized")
            return

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._semaphore = asyncio.Semaphore(self._pool_config.pool_size)

        for _ in range(self._pool_config.pool_size):
            conn = await self._create_connection()
            self._pool.append(PooledConnection(connection=conn))

        self._initialized = True
        self._cleanup_task = asyncio.create_task(self._cleanup_idle_connections())

        logger.info(
            f"Connection pool initialized: {self._db_path} "
            f"(size={self._pool_config.pool_size}, timeout={self._pool_config.pool_timeout}s)"
        )

    async def _create_connection(self) -> aiosqlite.Connection:
        """새로운 SQLite 연결 생성"""
        conn = await aiosqlite.connect(
            self._db_path,
            timeout=self._sqlite_options.busy_timeout / 1000.0
        )

        conn.row_factory = aiosqlite.Row

        await conn.execute(f"PRAGMA busy_timeout={self._sqlite_options.busy_timeout}")
        await conn.execute(f"PRAGMA journal_mode={self._sqlite_options.journal_mode}")
        await conn.execute(f"PRAGMA synchronous={self._sqlite_options.synchronous}")
        await conn.execute(f"PRAGMA cache_size={self._sqlite_options.cache_size}")
        await conn.execute(f"PRAGMA foreign_keys={'ON' if self._sqlite_options.foreign_keys else 'OFF'}")

        logger.debug("New connection created with PRAGMA settings applied")
        return conn

    async def acquire(self, timeout: float | None = None) -> PooledConnection:
        """커넥션풀에서 연결 획득"""
        if not self._initialized:
            raise RuntimeError("Connection pool not initialized. Call initialize() first.")

        if self._closed:
            raise RuntimeError("Connection pool is closed.")

        timeout = timeout or self._pool_config.pool_timeout

        try:
            acquired = await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=timeout
            )
            if not acquired:
                raise ConnectionPoolExhaustedError(
                    f"Failed to acquire connection within {timeout}s"
                )
        except asyncio.TimeoutError:
            raise ConnectionPoolExhaustedError(
                f"Connection pool exhausted. Timeout after {timeout}s"
            )

        async with self._lock:
            for pooled_conn in self._pool:
                if not pooled_conn.in_use:
                    pooled_conn.in_use = True
                    pooled_conn.last_used_at = datetime.now()
                    return pooled_conn

        self._semaphore.release()
        raise ConnectionPoolExhaustedError("No available connection in pool")

    async def release(self, pooled_conn: PooledConnection) -> None:
        """연결을 풀에 반환"""
        async with self._lock:
            pooled_conn.in_use = False
            pooled_conn.last_used_at = datetime.now()
        self._semaphore.release()
        logger.debug(f"Connection released. Available: {self.available}/{self.size}")

    async def _cleanup_idle_connections(self) -> None:
        """유휴 연결 정리 (백그라운드 태스크)"""
        while not self._closed:
            await asyncio.sleep(60)

            async with self._lock:
                now = datetime.now()
                for pooled_conn in self._pool:
                    if not pooled_conn.in_use:
                        idle_time = (now - pooled_conn.last_used_at).total_seconds()
                        if idle_time > self._pool_config.max_idle_time:
                            try:
                                await pooled_conn.connection.close()
                                pooled_conn.connection = await self._create_connection()
                                pooled_conn.created_at = datetime.now()
                                pooled_conn.last_used_at = datetime.now()
                                logger.debug("Refreshed idle connection")
                            except Exception as e:
                                logger.error(f"Failed to refresh connection: {e}")

    async def close(self) -> None:
        """모든 연결을 닫고 풀 종료"""
        self._closed = True

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            for pooled_conn in self._pool:
                try:
                    await pooled_conn.connection.close()
                except Exception as e:
                    logger.error(f"Error closing connection: {e}")
            self._pool.clear()

        logger.info("Connection pool closed")

    @property
    def size(self) -> int:
        """현재 풀의 연결 수"""
        return len(self._pool)

    @property
    def available(self) -> int:
        """사용 가능한 연결 수"""
        return sum(1 for pc in self._pool if not pc.in_use)


class ManagedTransaction:
    """SQLite 트랜잭션 컨텍스트 매니저"""

    def __init__(self, db: 'SQLiteDatabase', readonly: bool = False):
        self._db = db
        self._readonly = readonly
        self._pooled_conn: PooledConnection | None = None
        self._ctx: TransactionContext | None = None

    async def __aenter__(self) -> TransactionContext:
        self._pooled_conn = await self._db.pool.acquire()
        self._ctx = TransactionContext(self._pooled_conn.connection, self._readonly)

        if self._readonly:
            await self._pooled_conn.connection.execute("BEGIN DEFERRED")
        else:
            await self._pooled_conn.connection.execute("BEGIN IMMEDIATE")
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
            await self._db.pool.release(self._pooled_conn)


class SQLiteDatabase(BaseDatabase):
    """
    SQLite 데이터베이스 구현

    사용 예시:
        db = await SQLiteDatabase.create('default', config)

        @transactional(db)
        async def create_job(job_data):
            ctx = get_connection('default')
            await ctx.execute(...)

        async with db.transaction() as ctx:
            await ctx.execute(...)
    """

    def __init__(self, name: str, config: dict[str, Any]):
        super().__init__(name)
        self._config = config
        self._pool: AsyncConnectionPool | None = None
        self._queries: dict[str, Any] = {}

    @classmethod
    async def create(cls, name: str, config: dict[str, Any]) -> 'SQLiteDatabase':
        """SQLiteDatabase 인스턴스 생성 및 초기화"""
        instance = cls(name, config)
        await instance._initialize()
        return instance

    async def _initialize(self) -> None:
        """내부 초기화"""
        pool_cfg = self._config.get('pool', {})
        pool_config = PoolConfig(
            pool_size=pool_cfg.get('pool_size', 5),
            pool_timeout=pool_cfg.get('pool_timeout', 30.0),
            max_idle_time=pool_cfg.get('max_idle_time', 300.0)
        )

        opts = self._config.get('options', {})
        sqlite_options = SqliteOptions(
            busy_timeout=opts.get('busy_timeout', 5000),
            journal_mode=opts.get('journal_mode', 'WAL'),
            synchronous=opts.get('synchronous', 'NORMAL'),
            cache_size=opts.get('cache_size', -2000),
            foreign_keys=opts.get('foreign_keys', True)
        )

        self._pool = AsyncConnectionPool(
            db_path=self._config.get('path', f'./data/{self.name}.db'),
            pool_config=pool_config,
            sqlite_options=sqlite_options
        )
        await self._pool.initialize()

        await self._run_init_sql()

        logger.info(f"SQLiteDatabase '{self.name}' initialized successfully")

    async def _run_init_sql(self) -> None:
        """초기 테이블 생성 SQL 실행"""
        init_sql_path = Path(__file__).parent / 'sql' / 'init.sql'
        if init_sql_path.exists():
            queries = aiosql.from_path(str(init_sql_path), "aiosqlite")
            pooled_conn = await self._pool.acquire()
            try:
                if hasattr(queries, 'create_cron_jobs_table'):
                    await queries.create_cron_jobs_table(pooled_conn.connection)
                if hasattr(queries, 'create_job_executions_table'):
                    await queries.create_job_executions_table(pooled_conn.connection)
                if hasattr(queries, 'create_indexes'):
                    await queries.create_indexes(pooled_conn.connection)
                if hasattr(queries, 'create_sample_data_table'):
                    await queries.create_sample_data_table(pooled_conn.connection)
                if hasattr(queries, 'create_sample_data_indexes'):
                    await queries.create_sample_data_indexes(pooled_conn.connection)
                await pooled_conn.connection.commit()
                logger.info("Initial tables created from init.sql")
            finally:
                await self._pool.release(pooled_conn)
        else:
            logger.warning(f"init.sql not found: {init_sql_path}")

    def transaction(self, readonly: bool = False) -> ManagedTransaction:
        """트랜잭션 컨텍스트 매니저 반환"""
        return ManagedTransaction(self, readonly)

    @property
    def pool(self) -> AsyncConnectionPool:
        """커넥션풀 반환"""
        if self._pool is None:
            raise RuntimeError(f"Database '{self.name}' not initialized")
        return self._pool

    def load_queries(self, name: str, sql_path: str) -> Queries:
        """aiosql로 SQL 파일 로드"""
        queries = aiosql.from_path(sql_path, "aiosqlite")
        self._queries[name] = queries
        return queries

    def get_queries(self, name: str) -> Queries | None:
        """로드된 쿼리 세트 반환"""
        return self._queries.get(name)

    async def close(self) -> None:
        """데이터베이스 연결 종료"""
        if self._pool:
            await self._pool.close()
        logger.info(f"SQLiteDatabase '{self.name}' closed")


# 하위 호환성을 위한 별칭
Database = SQLiteDatabase
