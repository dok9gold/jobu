"""크론 관련 모델 정의"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CronResponse(BaseModel):
    """크론 응답 모델"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None = None
    cron_expression: str
    handler_name: str
    handler_params: Any | None = None
    is_enabled: bool
    allow_overlap: bool
    max_retry: int
    timeout_seconds: int
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CronCreateRequest(BaseModel):
    """크론 생성 요청"""
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    cron_expression: str = Field(..., min_length=9, max_length=100)
    handler_name: str = Field(..., min_length=1, max_length=100)
    handler_params: Any | None = None
    is_enabled: bool = True
    allow_overlap: bool = True
    max_retry: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=3600, ge=60, le=86400)


class CronUpdateRequest(BaseModel):
    """크론 수정 요청"""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    cron_expression: str | None = Field(default=None, min_length=9, max_length=100)
    handler_name: str | None = Field(default=None, min_length=1, max_length=100)
    handler_params: Any | None = None
    is_enabled: bool | None = None
    allow_overlap: bool | None = None
    max_retry: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: int | None = Field(default=None, ge=60, le=86400)


class CronListResponse(BaseModel):
    """크론 목록 응답"""
    items: list[CronResponse]
    total: int
    page: int
    size: int
    pages: int
