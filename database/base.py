"""
데이터베이스 추상 클래스

SQLite, PostgreSQL 등 다양한 DB 구현체의 공통 인터페이스를 정의합니다.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class BaseDatabase(ABC):
    """DB 추상 클래스 - SQLite, PostgreSQL 등 공통 인터페이스"""

    db_type: str = "sqlite"  # 서브클래스에서 오버라이드

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    @asynccontextmanager
    async def transaction(self, readonly: bool = False) -> AsyncIterator[Any]:
        """트랜잭션 컨텍스트 매니저 반환"""
        yield

    @abstractmethod
    async def close(self) -> None:
        """DB 연결 종료"""
        pass
