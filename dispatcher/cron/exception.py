"""
Dispatcher 관련 예외 클래스 정의
"""


class DispatcherError(Exception):
    """Dispatcher 기본 예외"""
    pass


class CronParseError(DispatcherError):
    """크론 표현식 파싱 실패"""
    def __init__(self, cron_expression: str, message: str = None):
        self.cron_expression = cron_expression
        self.message = message or f"Invalid cron expression: {cron_expression}"
        super().__init__(self.message)


class CronIntervalTooShortError(DispatcherError):
    """크론 간격이 너무 짧음 (초단위 크론 차단)"""
    def __init__(self, cron_expression: str, interval_seconds: float, min_interval: int):
        self.cron_expression = cron_expression
        self.interval_seconds = interval_seconds
        self.min_interval = min_interval
        self.message = (
            f"Cron interval too short: {interval_seconds:.1f}s "
            f"(minimum: {min_interval}s) for expression '{cron_expression}'"
        )
        super().__init__(self.message)


class JobCreationError(DispatcherError):
    """Job 생성 실패"""
    def __init__(self, job_id: int, scheduled_time: str, message: str = None):
        self.job_id = job_id
        self.scheduled_time = scheduled_time
        self.message = message or f"Failed to create job execution: job_id={job_id}, scheduled_time={scheduled_time}"
        super().__init__(self.message)
