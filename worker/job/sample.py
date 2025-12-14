"""샘플 핸들러 - 테스트용"""

import logging

from worker.base import BaseHandler, handler, HandlerParams, HandlerResult

logger = logging.getLogger(__name__)


@handler("sample_handler")
class SampleHandler(BaseHandler):
    """테스트용 샘플 핸들러"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        logger.info(f"SampleHandler executed with params: {params.handler_params}")

        return HandlerResult(
            action="sample",
            success=True,
            data={
                "message": "Hello from SampleHandler!",
                "received_params": params.handler_params,
            }
        )
