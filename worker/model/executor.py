"""
Worker 모델 - Executor 관련 구조체
"""

from dataclasses import dataclass


@dataclass
class JobInfo:
    """실행할 잡 정보"""
    id: int
    job_id: int
    scheduled_time: str
    retry_count: int
    job_name: str
    handler_name: str
    params: str | None  # job_executions.params
    max_retry: int
    timeout_seconds: int
