"""Sample7 Handler - 서비스 레이어 분리 패턴 (스프링 스타일)

핸들러는 Controller 역할만 수행.
비즈니스 로직과 트랜잭션은 서비스 레이어에서 처리.
"""

import logging

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from worker.job.group3.service import sample7_service

logger = logging.getLogger(__name__)


@handler("sample7")
class Sample7Handler(BaseHandler):
    """서비스 레이어 분리 예제 (스프링 스타일)

    - 핸들러: 요청 파싱, 서비스 호출, 응답 포맷팅
    - 서비스: 비즈니스 로직, 트랜잭션 관리
    """

    async def execute(self, params: HandlerParams) -> HandlerResult:
        if params.action == 'create':
            data_id = await sample7_service.create_data(
                name=params.name or 'test',
                value=params.value or ''
            )
            logger.info(f"Sample7Handler: created data id={data_id}")
            return HandlerResult(action='create', id=data_id)

        elif params.action == 'read':
            if params.id:
                data = await sample7_service.get_data_by_id(params.id)
                return HandlerResult(action='read', data=data)
            else:
                data_list = await sample7_service.get_data_list()
                logger.info(f"Sample7Handler: read {len(data_list)} rows")
                return HandlerResult(action='read', count=len(data_list), data=data_list)

        elif params.action == 'update':
            success = await sample7_service.update_data(
                data_id=params.id,
                name=params.name or '',
                value=params.value or ''
            )
            logger.info(f"Sample7Handler: updated data success={success}")
            return HandlerResult(action='update', success=success)

        elif params.action == 'delete':
            success = await sample7_service.delete_data(data_id=params.id)
            logger.info(f"Sample7Handler: deleted data success={success}")
            return HandlerResult(action='delete', success=success)

        else:
            return HandlerResult(action=params.action, success=False, error=f"Unknown action: {params.action}")
