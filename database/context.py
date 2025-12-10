"""
트랜잭션 컨텍스트 관리

ContextVar를 사용하여 현재 스레드/태스크의 트랜잭션 컨텍스트를 관리합니다.
DB 종류에 관계없이 공통으로 사용됩니다.
"""

from contextvars import ContextVar
from typing import Any

# 현재 트랜잭션 컨텍스트 (다중 DB 지원 - 이름 기반)
_current_connections: ContextVar[dict[str, Any]] = ContextVar(
    '_current_connections', default={}
)


def set_connection(db_name: str, ctx: Any) -> None:
    """ContextVar에 DB별 컨텍스트 저장"""
    conns = _current_connections.get().copy()
    conns[db_name] = ctx
    _current_connections.set(conns)


def clear_connection(db_name: str) -> None:
    """ContextVar에서 DB별 컨텍스트 제거"""
    conns = _current_connections.get().copy()
    conns.pop(db_name, None)
    _current_connections.set(conns)


def get_connection(db_name: str = 'default') -> Any:
    """
    특정 DB의 현재 트랜잭션 컨텍스트 반환

    Args:
        db_name: DB 이름 (config에서 정의한 이름)

    Returns:
        TransactionContext (DB 구현체별로 다름)

    Raises:
        RuntimeError: 해당 DB의 트랜잭션 컨텍스트가 없는 경우
    """
    conns = _current_connections.get()
    if db_name not in conns:
        raise RuntimeError(
            f"No active transaction for DB '{db_name}'. "
            "Use @transactional decorator or 'async with db.transaction()'"
        )
    return conns[db_name]
