"""잡 실행 이력 관련 모델 정의"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class JobStatus(str, Enum):
    """잡 실행 상태"""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class JobResponse(BaseModel):
    """잡 실행 이력 응답 모델"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_id: int
    cron_name: str | None = None
    scheduled_time: datetime | None = None
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    retry_count: int = 0
    error_message: str | None = None
    result: str | None = None
    created_at: datetime | None = None


class JobListResponse(BaseModel):
    """잡 목록 응답"""
    items: list[JobResponse]
    total: int
    page: int
    size: int
    pages: int
