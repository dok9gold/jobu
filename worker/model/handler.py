"""
핸들러 입출력 모델

모든 핸들러가 공통으로 사용하는 파라미터 및 결과 모델.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict


class HandlerParams(BaseModel):
    """핸들러 입력 파라미터 (공통)"""
    model_config = ConfigDict(extra='allow')  # 정의 안 된 필드도 허용

    action: str = 'read'
    id: int | None = None
    name: str | None = None
    value: str | None = None


class HandlerResult(BaseModel):
    """핸들러 실행 결과 (공통)"""
    model_config = ConfigDict(extra='allow')

    action: str
    success: bool = True
    id: int | None = None
    count: int | None = None
    data: Any = None
    error: str | None = None
