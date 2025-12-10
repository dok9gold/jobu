"""크론 비즈니스 로직 핸들러"""

import json
import logging
from datetime import datetime

from aiosql.queries import Queries
from croniter import croniter

from database import get_db, get_connection, transactional, transactional_readonly
from admin.api.model.cron import CronResponse, CronCreateRequest, CronUpdateRequest
from admin.exception import CronValidationError, CronNotFoundError, CronDuplicateError

logger = logging.getLogger(__name__)


class CronHandler:
    """크론 관리 핸들러"""

    MIN_CRON_INTERVAL_SECONDS = 60  # 최소 1분 간격

    def __init__(self):
        self._queries = None

    def _get_queries(self) -> Queries:
        if self._queries is None:
            db = get_db()
            self._queries = db.get_queries('admin')
            if self._queries is None:
                from pathlib import Path
                sql_path = Path(__file__).parent.parent / 'sql' / 'admin.sql'
                self._queries = db.load_queries('admin', str(sql_path))
        return self._queries

    @staticmethod
    def validate_cron_expression(cron_expr: str) -> None:
        """크론 표현식 유효성 검사"""
        try:
            cron = croniter(cron_expr)
            # 다음 2번 실행 시간 계산해서 간격 확인
            next1 = cron.get_next(datetime)
            next2 = cron.get_next(datetime)
            interval = (next2 - next1).total_seconds()

            if interval < CronHandler.MIN_CRON_INTERVAL_SECONDS:
                raise CronValidationError(
                    f"Cron interval must be at least {CronHandler.MIN_CRON_INTERVAL_SECONDS} seconds. "
                    f"Got {interval} seconds."
                )
        except (KeyError, ValueError) as e:
            raise CronValidationError(f"Invalid cron expression: {cron_expr}. Error: {e}")

    @staticmethod
    def _row_to_response(row) -> CronResponse:
        """DB row를 CronResponse로 변환"""
        handler_params = row['handler_params']
        if handler_params and isinstance(handler_params, str):
            try:
                handler_params = json.loads(handler_params)
            except json.JSONDecodeError:
                pass

        return CronResponse(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            cron_expression=row['cron_expression'],
            handler_name=row['handler_name'],
            handler_params=handler_params,
            is_enabled=bool(row['is_enabled']),
            allow_overlap=bool(row['allow_overlap']),
            max_retry=row['max_retry'],
            timeout_seconds=row['timeout_seconds'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

    @transactional_readonly
    async def get_list(
        self,
        page: int = 1,
        size: int = 20,
        is_enabled: bool | None = None
    ) -> tuple[list[CronResponse], int]:
        """크론 목록 조회"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 전체 개수 조회
        if is_enabled is not None:
            total_row = await queries.count_crons_by_enabled(conn, is_enabled=int(is_enabled))
        else:
            total_row = await queries.count_crons(conn)
        total = total_row['cnt'] if total_row else 0

        # 목록 조회
        offset = (page - 1) * size
        if is_enabled is not None:
            rows = await queries.get_crons_by_enabled(
                conn, is_enabled=int(is_enabled), limit=size, offset=offset
            )
        else:
            rows = await queries.get_crons_paged(conn, limit=size, offset=offset)

        items = [self._row_to_response(row) for row in rows]
        return items, total

    @transactional_readonly
    async def get_by_id(self, cron_id: int) -> CronResponse:
        """ID로 크론 조회"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        row = await queries.get_cron_by_id(conn, cron_id=cron_id)
        if not row:
            raise CronNotFoundError(cron_id)

        return self._row_to_response(row)

    @transactional
    async def create(self, request: CronCreateRequest) -> CronResponse:
        """크론 생성"""
        # 유효성 검사
        self.validate_cron_expression(request.cron_expression)

        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 이름 중복 체크
        existing = await queries.get_cron_by_name(conn, name=request.name)
        if existing:
            raise CronDuplicateError(request.name)

        # handler_params를 JSON 문자열로 변환
        handler_params = None
        if request.handler_params:
            handler_params = json.dumps(request.handler_params)

        # 생성
        cron_id = await queries.insert_cron(
            conn,
            name=request.name,
            description=request.description,
            cron_expression=request.cron_expression,
            handler_name=request.handler_name,
            handler_params=handler_params,
            is_enabled=int(request.is_enabled),
            allow_overlap=int(request.allow_overlap),
            max_retry=request.max_retry,
            timeout_seconds=request.timeout_seconds,
        )

        logger.info(f"Created cron: id={cron_id}, name={request.name}")

        row = await queries.get_cron_by_id(conn, cron_id=cron_id)
        return self._row_to_response(row)

    @transactional
    async def update(self, cron_id: int, request: CronUpdateRequest) -> CronResponse:
        """크론 수정"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 기존 크론 조회
        existing = await queries.get_cron_by_id(conn, cron_id=cron_id)
        if not existing:
            raise CronNotFoundError(cron_id)

        # 크론 표현식 유효성 검사
        if request.cron_expression:
            self.validate_cron_expression(request.cron_expression)

        # 이름 변경 시 중복 체크
        if request.name and request.name != existing['name']:
            dup = await queries.get_cron_by_name(conn, name=request.name)
            if dup:
                raise CronDuplicateError(request.name)

        # 업데이트할 값 준비 (None이면 기존 값 유지)
        name = request.name if request.name is not None else existing['name']
        description = request.description if request.description is not None else existing['description']
        cron_expression = request.cron_expression if request.cron_expression is not None else existing['cron_expression']
        handler_name = request.handler_name if request.handler_name is not None else existing['handler_name']

        handler_params = existing['handler_params']
        if request.handler_params is not None:
            handler_params = json.dumps(request.handler_params)

        is_enabled = int(request.is_enabled) if request.is_enabled is not None else existing['is_enabled']
        allow_overlap = int(request.allow_overlap) if request.allow_overlap is not None else existing['allow_overlap']
        max_retry = request.max_retry if request.max_retry is not None else existing['max_retry']
        timeout_seconds = request.timeout_seconds if request.timeout_seconds is not None else existing['timeout_seconds']

        # 수정
        await queries.update_cron(
            conn,
            cron_id=cron_id,
            name=name,
            description=description,
            cron_expression=cron_expression,
            handler_name=handler_name,
            handler_params=handler_params,
            is_enabled=is_enabled,
            allow_overlap=allow_overlap,
            max_retry=max_retry,
            timeout_seconds=timeout_seconds,
        )

        logger.info(f"Updated cron: id={cron_id}")

        row = await queries.get_cron_by_id(conn, cron_id=cron_id)
        return self._row_to_response(row)

    @transactional
    async def delete(self, cron_id: int) -> None:
        """크론 삭제"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 존재 확인
        existing = await queries.get_cron_by_id(conn, cron_id=cron_id)
        if not existing:
            raise CronNotFoundError(cron_id)

        await queries.delete_cron(conn, cron_id=cron_id)
        logger.info(f"Deleted cron: id={cron_id}")

    @transactional
    async def toggle(self, cron_id: int) -> CronResponse:
        """크론 활성화/비활성화 토글"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 기존 크론 조회
        existing = await queries.get_cron_by_id(conn, cron_id=cron_id)
        if not existing:
            raise CronNotFoundError(cron_id)

        # 토글
        new_status = 0 if existing['is_enabled'] else 1
        await queries.toggle_cron(conn, cron_id=cron_id, is_enabled=new_status)

        logger.info(f"Toggled cron: id={cron_id}, is_enabled={bool(new_status)}")

        row = await queries.get_cron_by_id(conn, cron_id=cron_id)
        return self._row_to_response(row)

    @transactional_readonly
    async def get_all_for_select(self) -> list[CronResponse]:
        """셀렉트박스용 크론 전체 목록 조회"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        rows = await queries.get_all_crons(conn)
        return [self._row_to_response(row) for row in rows]
