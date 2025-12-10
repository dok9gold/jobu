"""
데이터베이스 레지스트리

다중 DB 인스턴스를 이름 기반으로 관리합니다.
"""

import logging
from collections.abc import Sequence

from database.base import BaseDatabase

logger = logging.getLogger(__name__)


class DatabaseRegistry:
    """다중 DB 인스턴스 관리 (이름 기반)"""
    _databases: dict[str, BaseDatabase] = {}

    @classmethod
    def register(cls, name: str, db: BaseDatabase) -> None:
        cls._databases[name] = db
        logger.info(f"Database '{name}' registered")

    @classmethod
    def get(cls, name: str) -> BaseDatabase:
        if name not in cls._databases:
            raise KeyError(f"Database '{name}' not registered")
        return cls._databases[name]

    @classmethod
    def get_all(cls) -> dict[str, BaseDatabase]:
        return cls._databases.copy()

    @classmethod
    async def init_from_config(
        cls,
        config: dict,
        db_names: Sequence[str] | None = None
    ) -> None:
        """
        config/database.yaml에서 DB 초기화

        Args:
            config: database.yaml 설정
            db_names: 초기화할 DB 이름 목록 (None이면 전체 초기화)

        databases:
          default:
            type: sqlite
            path: data/jobu.db
          business:
            type: sqlite
            path: data/business.db
        """
        # 순환 참조 방지를 위해 함수 내에서 import
        from database.sqlite3.connection import SQLiteDatabase

        all_databases = config.get('databases', {})

        # db_names가 지정되면 해당 DB만, 아니면 전체
        target_names = db_names if db_names else list(all_databases.keys())

        for name in target_names:
            # 이미 등록된 DB는 스킵
            if name in cls._databases:
                logger.debug(f"Database '{name}' already registered, skipping")
                continue

            if name not in all_databases:
                raise KeyError(f"Database '{name}' not found in config")

            db_config = all_databases[name]
            db_type = db_config.get('type', 'sqlite')

            if db_type == 'sqlite':
                db = await SQLiteDatabase.create(name, db_config)
            elif db_type == 'postgres':
                from database.postgres.connection import PostgresDatabase
                db = await PostgresDatabase.create(name, db_config)
            elif db_type == 'mysql':
                from database.mysql.connection import MySQLDatabase
                db = await MySQLDatabase.create(name, db_config)
            else:
                raise ValueError(f"Unsupported database type: {db_type}")

            cls.register(name, db)

        logger.info(f"Initialized {len(target_names)} database(s): {target_names}")

    @classmethod
    async def close_all(cls) -> None:
        for name, db in cls._databases.items():
            await db.close()
            logger.info(f"Database '{name}' closed")
        cls._databases.clear()

    @classmethod
    def clear(cls) -> None:
        """레지스트리 초기화 (테스트용)"""
        cls._databases.clear()
