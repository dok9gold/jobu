"""Queue Dispatcher 예외"""


class QueueDispatcherError(Exception):
    """QueueDispatcher 기본 예외"""
    pass


class QueueConnectionError(QueueDispatcherError):
    """큐 연결 실패"""
    pass


class MessageParseError(QueueDispatcherError):
    """메시지 파싱 실패"""
    def __init__(self, message: str, raw_data: str):
        super().__init__(f"{message}: {raw_data}")
        self.raw_data = raw_data


class HandlerNotFoundError(QueueDispatcherError):
    """핸들러를 찾을 수 없음"""
    def __init__(self, handler_name: str):
        super().__init__(f"Handler not found: {handler_name}")
        self.handler_name = handler_name


class ExecutionCreationError(QueueDispatcherError):
    """실행 레코드 생성 실패"""
    def __init__(self, handler_name: str, reason: str):
        super().__init__(f"Failed to create execution for {handler_name}: {reason}")
        self.handler_name = handler_name
        self.reason = reason
