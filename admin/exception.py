"""
Admin 관련 예외 클래스 정의
"""


class AdminError(Exception):
    """Admin 기본 예외"""
    pass


class CronNotFoundError(AdminError):
    """크론을 찾을 수 없음"""
    def __init__(self, cron_id: int):
        self.cron_id = cron_id
        self.message = f"Cron with id {cron_id} not found"
        super().__init__(self.message)


class CronValidationError(AdminError):
    """크론 유효성 검사 실패"""
    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class CronDuplicateError(AdminError):
    """크론 이름 중복"""
    def __init__(self, name: str):
        self.name = name
        self.message = f"Cron with name '{name}' already exists"
        super().__init__(self.message)


class JobNotFoundError(AdminError):
    """잡 실행 이력을 찾을 수 없음"""
    def __init__(self, execution_id: int):
        self.execution_id = execution_id
        self.message = f"Job execution with id {execution_id} not found"
        super().__init__(self.message)


class JobStatusError(AdminError):
    """잡 상태 에러 (재시도 불가 등)"""
    def __init__(self, execution_id: int, current_status: str):
        self.execution_id = execution_id
        self.current_status = current_status
        self.message = (
            f"Cannot retry job with status '{current_status}'. "
            f"Only FAILED or TIMEOUT jobs can be retried."
        )
        super().__init__(self.message)
