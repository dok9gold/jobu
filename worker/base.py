from abc import ABC, abstractmethod

from worker.exception import HandlerNotFoundError
from worker.model.handler import HandlerParams, HandlerResult

__all__ = ['handler', 'get_handler', 'get_registered_handlers', 'BaseHandler', 'HandlerNotFoundError']

# 핸들러 레지스트리 (모듈 레벨)
_registry: dict[str, type["BaseHandler"]] = {}


def handler(name: str):
    """핸들러 등록 데코레이터"""
    def decorator(cls):
        _registry[name] = cls
        return cls
    return decorator


def get_handler(name: str) -> "BaseHandler":
    """핸들러 인스턴스 반환"""
    if name not in _registry:
        raise HandlerNotFoundError(name)
    return _registry[name]()


def get_registered_handlers() -> dict[str, type["BaseHandler"]]:
    """등록된 핸들러 목록 반환 (테스트용)"""
    return _registry.copy()


class BaseHandler(ABC):
    """배치 핸들러 기본 클래스"""

    @abstractmethod
    async def execute(self, params: HandlerParams) -> HandlerResult:
        """
        잡 실행 로직

        Args:
            params: 핸들러 입력 파라미터 (HandlerParams)

        Returns:
            실행 결과 (HandlerResult, job_executions.result에 JSON으로 저장)

        Raises:
            Exception: 실행 실패 시 예외 발생
        """
        pass
