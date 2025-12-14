"""
CRON 작업 및 실행 이력 모델 정의
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """작업 실행 상태"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class CronJob(BaseModel):
    """CRON 작업 엔티티"""
    id: int | None = None
    name: str
    description: str | None = None
    cron_expression: str
    handler_name: str
    handler_params: str | None = None
    is_enabled: bool = True
    allow_overlap: bool = True  # True: 중복 허용, False: 미완료 Job 있으면 생성 안 함
    max_retry: int = 3
    timeout_seconds: int = 3600
    created_at: datetime | None = None
    updated_at: datetime | None = None


class JobExecution(BaseModel):
    """작업 실행 이력 엔티티"""
    id: int | None = None
    job_id: int
    scheduled_time: datetime
    status: ExecutionStatus = ExecutionStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_count: int = 0
    error_message: str | None = None
    result: str | None = None
    created_at: datetime | None = None


class DispatcherConfig(BaseModel):
    """Dispatcher 설정"""
    database: str = Field(default="default", description="database.yaml에 정의된 DB 이름")
    poll_interval_seconds: int = Field(default=60, ge=10, le=600)
    max_sleep_seconds: int = Field(default=300, ge=60, le=600)
    min_cron_interval_seconds: int = Field(default=60, ge=60, le=3600)


class CreateJobRequest(BaseModel):
    """작업 생성 요청"""
    name: str
    description: str | None = None
    cron_expression: str
    handler_name: str
    handler_params: dict | None = None
    is_enabled: bool = True
    max_retry: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class UpdateJobRequest(BaseModel):
    """작업 수정 요청"""
    name: str | None = None
    description: str | None = None
    cron_expression: str | None = None
    handler_name: str | None = None
    handler_params: dict | None = None
    is_enabled: bool | None = None
    max_retry: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: int | None = Field(default=None, ge=60, le=86400)
