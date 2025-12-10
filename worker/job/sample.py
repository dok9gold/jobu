"""
Sample Handler - for testing

params example:
{
    "sleep_seconds": 1,
    "should_fail": false,
    "message": "hello"
}
"""

import asyncio
import logging

from worker.base import BaseHandler, handler
from worker.model.handler import HandlerParams, HandlerResult

logger = logging.getLogger(__name__)


@handler("sample")
class SampleHandler(BaseHandler):
    """Test sample handler"""

    async def execute(self, params: HandlerParams) -> HandlerResult:
        sleep_seconds = getattr(params, 'sleep_seconds', 0)
        should_fail = getattr(params, 'should_fail', False)
        message = getattr(params, 'message', 'sample job executed')

        logger.info(f"SampleHandler executing: sleep={sleep_seconds}s, should_fail={should_fail}")

        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

        if should_fail:
            raise RuntimeError(f"Simulated failure: {message}")

        return HandlerResult(action='execute', data={"message": message})
