"""
잡 실행기 모듈

개별 잡의 실행을 담당합니다.
"""

import asyncio
import json
import logging

from database import (
    get_connection,
    transactional,
    ConnectionPoolExhaustedError,
    TransactionError,
    QueryExecutionError,
)
from worker.base import get_handler, HandlerNotFoundError
from worker.model import JobInfo
from worker.model.handler import HandlerParams

logger = logging.getLogger(__name__)


class Executor:
    """잡 실행기"""

    def __init__(self, queries):
        self._queries = queries

    async def execute(self, job_info: JobInfo) -> bool:
        """
        잡 실행

        Args:
            job_info: 실행할 잡 정보

        Returns:
            bool: 실행 성공 여부
        """
        execution_id = job_info.id
        logger.info(f"Starting job execution: id={execution_id}, handler={job_info.handler_name}")

        # 1. RUNNING으로 상태 변경 (claim)
        claimed = await self._claim_execution(execution_id)
        if not claimed:
            logger.warning(f"Failed to claim execution: id={execution_id}")
            return False

        # 2. 핸들러 조회
        try:
            handler = get_handler(job_info.handler_name)
        except HandlerNotFoundError as e:
            logger.error(f"Handler not found: {job_info.handler_name}")
            await self._fail_execution(execution_id, str(e), job_info.max_retry, job_info.retry_count)
            return False

        # 3. params 파싱 (dict -> HandlerParams)
        try:
            params_dict = json.loads(job_info.handler_params or '{}')
            params = HandlerParams(**params_dict)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse handler_params: {e}")
            await self._fail_execution(execution_id, f"Invalid handler_params: {e}", job_info.max_retry, job_info.retry_count)
            return False
        except Exception as e:
            logger.error(f"Failed to create HandlerParams: {e}")
            await self._fail_execution(execution_id, f"Invalid handler_params: {e}", job_info.max_retry, job_info.retry_count)
            return False

        # 4. 핸들러 실행 (타임아웃 적용)
        try:
            result = await asyncio.wait_for(
                handler.execute(params),
                timeout=job_info.timeout_seconds
            )
            # 성공 (HandlerResult -> JSON)
            result_str = result.model_dump_json() if result is not None else None
            await self._complete_execution(execution_id, result_str)
            logger.info(f"Job execution completed: id={execution_id}")
            return True

        except asyncio.TimeoutError:
            logger.error(f"Job execution timed out: id={execution_id}")
            await self._timeout_execution(execution_id, job_info.max_retry, job_info.retry_count)
            return False

        except ConnectionPoolExhaustedError as e:
            logger.warning(f"Connection pool exhausted during job execution: id={execution_id}, error={e}")
            await self._fail_execution(execution_id, f"Connection pool exhausted: {e}", job_info.max_retry, job_info.retry_count)
            return False

        except (TransactionError, QueryExecutionError) as e:
            logger.error(f"Database error during job execution: id={execution_id}, error={e}")
            await self._fail_execution(execution_id, f"Database error: {e}", job_info.max_retry, job_info.retry_count)
            return False

        except Exception as e:
            logger.error(f"Job execution failed: id={execution_id}, error={e}")
            await self._fail_execution(execution_id, str(e), job_info.max_retry, job_info.retry_count)
            return False

    @transactional
    async def _claim_execution(self, execution_id: int) -> bool:
        """PENDING -> RUNNING 상태 변경"""
        ctx = get_connection()
        # aiosql의 ! 연산자는 affected rows (int)를 직접 반환
        affected_rows = await self._queries.claim_execution(ctx.connection, execution_id=execution_id)
        return affected_rows > 0

    @transactional
    async def _complete_execution(self, execution_id: int, result: str | None) -> None:
        """실행 완료 (SUCCESS)"""
        ctx = get_connection()
        await self._queries.complete_execution(ctx.connection, execution_id=execution_id, result=result)

    @transactional
    async def _fail_execution(self, execution_id: int, error_message: str, max_retry: int, current_retry: int) -> None:
        """실행 실패 (FAILED)"""
        ctx = get_connection()
        await self._queries.fail_execution(ctx.connection, execution_id=execution_id, error_message=error_message)

        # 재시도 판단: fail_execution에서 retry_count가 증가하므로 current_retry + 1과 비교
        if current_retry + 1 < max_retry:
            logger.info(f"Scheduling retry: id={execution_id}, retry={current_retry + 1}/{max_retry}")
            await self._queries.reset_to_pending(ctx.connection, execution_id=execution_id)

    @transactional
    async def _timeout_execution(self, execution_id: int, max_retry: int, current_retry: int) -> None:
        """실행 타임아웃 (TIMEOUT)"""
        ctx = get_connection()
        await self._queries.timeout_execution(ctx.connection, execution_id=execution_id)

        # 재시도 판단: timeout_execution에서 retry_count가 증가하므로 current_retry + 1과 비교
        if current_retry + 1 < max_retry:
            logger.info(f"Scheduling retry after timeout: id={execution_id}, retry={current_retry + 1}/{max_retry}")
            await self._queries.reset_to_pending(ctx.connection, execution_id=execution_id)
