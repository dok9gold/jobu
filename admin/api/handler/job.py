"""잡 실행 이력 비즈니스 로직 핸들러"""

import logging
from datetime import datetime

from aiosql.queries import Queries

from database import get_db, get_connection, transactional, transactional_readonly
from admin.api.model.job import JobResponse, JobStatus
from admin.exception import JobNotFoundError, JobStatusError

logger = logging.getLogger(__name__)


class JobHandler:
    """잡 실행 이력 핸들러"""

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
    def _row_to_response(row) -> JobResponse:
        """DB row를 JobResponse로 변환"""
        # sqlite3.Row는 .get() 메서드가 없으므로 dict 변환
        row_dict = dict(row)
        return JobResponse(
            id=row_dict['id'],
            job_id=row_dict['job_id'],
            cron_name=row_dict.get('cron_name'),
            scheduled_time=row_dict.get('scheduled_time'),
            status=row_dict['status'],
            started_at=row_dict.get('started_at'),
            finished_at=row_dict.get('finished_at'),
            retry_count=row_dict.get('retry_count', 0),
            error_message=row_dict.get('error_message'),
            result=row_dict.get('result'),
            created_at=row_dict.get('created_at'),
        )

    @transactional_readonly
    async def get_list(
        self,
        page: int = 1,
        size: int = 20,
        cron_id: int | None = None,
        status: str | None = None,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> tuple[list[JobResponse], int]:
        """잡 실행 이력 목록 조회"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        offset = (page - 1) * size

        # 필터 조건에 따라 쿼리 선택
        if cron_id and status:
            total_row = await queries.count_jobs_by_cron_and_status(
                conn, cron_id=cron_id, status=status
            )
            rows = await queries.get_jobs_by_cron_and_status(
                conn, cron_id=cron_id, status=status, limit=size, offset=offset
            )
        elif cron_id:
            total_row = await queries.count_jobs_by_cron(conn, cron_id=cron_id)
            rows = await queries.get_jobs_by_cron(
                conn, cron_id=cron_id, limit=size, offset=offset
            )
        elif status:
            total_row = await queries.count_jobs_by_status(conn, status=status)
            rows = await queries.get_jobs_by_status(
                conn, status=status, limit=size, offset=offset
            )
        else:
            total_row = await queries.count_jobs(conn)
            rows = await queries.get_jobs_paged(conn, limit=size, offset=offset)

        total = total_row['cnt'] if total_row else 0
        items = [self._row_to_response(row) for row in rows]

        return items, total

    @transactional_readonly
    async def get_by_id(self, job_id: int) -> JobResponse:
        """ID로 잡 실행 이력 조회"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        row = await queries.get_job_by_id(conn, execution_id=job_id)
        if not row:
            raise JobNotFoundError(job_id)

        return self._row_to_response(row)

    @transactional
    async def retry(self, job_id: int) -> JobResponse:
        """실패한 잡 재시도 (FAILED/TIMEOUT -> PENDING)"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 기존 잡 조회
        row = await queries.get_job_by_id(conn, execution_id=job_id)
        if not row:
            raise JobNotFoundError(job_id)

        # 상태 확인 (FAILED, TIMEOUT만 재시도 가능)
        current_status = row['status']
        if current_status not in (JobStatus.FAILED.value, JobStatus.TIMEOUT.value):
            raise JobStatusError(job_id, current_status)

        # PENDING으로 상태 변경
        await queries.retry_job(conn, execution_id=job_id)

        logger.info(f"Retried job: id={job_id}, previous_status={current_status}")

        updated_row = await queries.get_job_by_id(conn, execution_id=job_id)
        return self._row_to_response(updated_row)

    @transactional
    async def delete(self, job_id: int) -> None:
        """잡 실행 이력 삭제"""
        queries = self._get_queries()
        ctx = get_connection()
        conn = ctx.connection

        # 존재 확인
        row = await queries.get_job_by_id(conn, execution_id=job_id)
        if not row:
            raise JobNotFoundError(job_id)

        await queries.delete_job(conn, execution_id=job_id)
        logger.info(f"Deleted job execution: id={job_id}")
