"""서비스 레이어 분리 패턴 (Spring MVC 스타일)

핸들러는 Controller 역할만 수행.
비즈니스 로직과 트랜잭션은 서비스 레이어에서 처리.

구조:
- 핸들러: 요청 파싱, 서비스 호출, 응답 포맷팅
- 서비스: 비즈니스 로직, 트랜잭션 관리
"""

import logging

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult
from worker.job.patterns.service import service_layer_service

logger = logging.getLogger(__name__)


@handler("service_layer")
class ServiceLayerHandler(BaseHandler):
    """서비스 레이어 분리 예제 (Spring MVC 스타일)"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        if params.action == 'create':
            data_id = await service_layer_service.create_data(
                name=params.name or 'test',
                value=params.value or ''
            )
            logger.info(f"ServiceLayerHandler: created data id={data_id}")
            return HandlerResult(action='create', id=data_id)

        elif params.action == 'read':
            if params.id:
                data = await service_layer_service.get_data_by_id(params.id)
                return HandlerResult(action='read', data=data)
            else:
                data_list = await service_layer_service.get_data_list()
                logger.info(f"ServiceLayerHandler: read {len(data_list)} rows")
                return HandlerResult(action='read', count=len(data_list), data=data_list)

        elif params.action == 'update':
            success = await service_layer_service.update_data(
                data_id=params.id,
                name=params.name or '',
                value=params.value or ''
            )
            logger.info(f"ServiceLayerHandler: updated data success={success}")
            return HandlerResult(action='update', success=success)

        elif params.action == 'delete':
            success = await service_layer_service.delete_data(data_id=params.id)
            logger.info(f"ServiceLayerHandler: deleted data success={success}")
            return HandlerResult(action='delete', success=success)

        else:
            return HandlerResult(action=params.action, success=False, error=f"Unknown action: {params.action}")
