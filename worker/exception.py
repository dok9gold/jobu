"""
Worker 관련 예외 클래스 정의
"""


class WorkerError(Exception):
    """Worker 기본 예외"""
    pass


class HandlerNotFoundError(WorkerError):
    """핸들러를 찾을 수 없음"""
    def __init__(self, name: str):
        self.name = name
        self.message = f"Handler not found: {name}"
        super().__init__(self.message)
