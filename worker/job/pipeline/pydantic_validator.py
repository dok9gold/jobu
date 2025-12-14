"""
Pydantic 검증 핸들러 템플릿

입력 데이터를 Pydantic 모델로 검증하는 예시입니다.

params 예시:
{
    "data": [
        {"id": 1, "name": "test", "value": 100},
        {"id": 2, "name": "invalid", "value": -1}
    ],
    "strict": false
}
"""

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from worker.base import BaseHandler, handler, HandlerParams, HandlerResult

logger = logging.getLogger(__name__)


class SampleRecord(BaseModel):
    """샘플 데이터 검증 모델"""
    id: int
    name: str = Field(min_length=1, max_length=100)
    value: float = Field(ge=0)  # 0 이상


@handler("pydantic_validator")
class PydanticValidatorHandler(BaseHandler):
    """
    Pydantic 검증 핸들러

    기능:
    - 입력 데이터를 Pydantic 모델로 검증
    - 유효/무효 데이터 분리
    - 검증 결과 리포트
    """

    async def execute(self, params: HandlerParams) -> HandlerResult:
        data = params.handler_params.get("data", [])
        strict = params.handler_params.get("strict", False)

        if not data:
            return HandlerResult(
                action="validate",
                success=False,
                error="data is required"
            )

        valid_records = []
        invalid_records = []

        for i, record in enumerate(data):
            try:
                validated = SampleRecord(**record)
                valid_records.append(validated.model_dump())
            except ValidationError as e:
                invalid_records.append({
                    "index": i,
                    "data": record,
                    "errors": e.errors(),
                })

        logger.info(
            f"Validation complete: {len(valid_records)} valid, "
            f"{len(invalid_records)} invalid"
        )

        # strict 모드면 무효 데이터가 있으면 실패
        if strict and invalid_records:
            return HandlerResult(
                action="validate",
                success=False,
                error=f"Validation failed: {len(invalid_records)} invalid records",
                data={
                    "valid_count": len(valid_records),
                    "invalid_count": len(invalid_records),
                    "invalid_records": invalid_records,
                }
            )

        return HandlerResult(
            action="validate",
            success=True,
            data={
                "valid_count": len(valid_records),
                "invalid_count": len(invalid_records),
                "valid_records": valid_records,
                "invalid_records": invalid_records,
            }
        )
