"""Admin API 라우터 (모든 API 통합)"""

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response

from admin.api.model.common import ErrorResponse, ErrorDetail
from admin.api.model.cron import (
    CronResponse,
    CronCreateRequest,
    CronUpdateRequest,
    CronListResponse,
)
from admin.api.model.job import JobResponse, JobListResponse
from admin.api.handler.cron import (
    CronHandler,
    CronValidationError,
    CronNotFoundError,
    CronDuplicateError,
)
from admin.api.handler.job import (
    JobHandler,
    JobNotFoundError,
    JobStatusError,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# 핸들러 인스턴스
cron_handler = CronHandler()
job_handler = JobHandler()


# ============================================
# CRON API
# ============================================

@router.get("/api/crons", response_model=CronListResponse, tags=["Cron"])
async def get_crons(
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    size: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    is_enabled: bool | None = Query(default=None, description="활성화 필터"),
):
    """크론 목록 조회"""
    items, total = await cron_handler.get_list(page=page, size=size, is_enabled=is_enabled)
    pages = (total + size - 1) // size if size > 0 else 0
    return CronListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/api/crons/{cron_id}", response_model=CronResponse, tags=["Cron"])
async def get_cron(cron_id: int):
    """크론 상세 조회"""
    try:
        return await cron_handler.get_by_id(cron_id)
    except CronNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/crons", response_model=CronResponse, status_code=201, tags=["Cron"])
async def create_cron(request: CronCreateRequest):
    """크론 생성"""
    try:
        return await cron_handler.create(request)
    except CronValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CronDuplicateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.put("/api/crons/{cron_id}", response_model=CronResponse, tags=["Cron"])
async def update_cron(cron_id: int, request: CronUpdateRequest):
    """크론 수정"""
    try:
        return await cron_handler.update(cron_id, request)
    except CronNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except CronValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except CronDuplicateError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/api/crons/{cron_id}", status_code=204, tags=["Cron"])
async def delete_cron(cron_id: int):
    """크론 삭제"""
    try:
        await cron_handler.delete(cron_id)
        return Response(status_code=204)
    except CronNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/crons/{cron_id}/toggle", response_model=CronResponse, tags=["Cron"])
async def toggle_cron(cron_id: int):
    """크론 활성화/비활성화 토글"""
    try:
        return await cron_handler.toggle(cron_id)
    except CronNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================
# JOB API
# ============================================

@router.get("/api/jobs", response_model=JobListResponse, tags=["Job"])
async def get_jobs(
    page: int = Query(default=1, ge=1, description="페이지 번호"),
    size: int = Query(default=20, ge=1, le=100, description="페이지 크기"),
    cron_id: int | None = Query(default=None, description="크론 ID 필터"),
    status: str | None = Query(default=None, description="상태 필터"),
    from_date: datetime | None = Query(default=None, description="시작일"),
    to_date: datetime | None = Query(default=None, description="종료일"),
):
    """잡 실행 이력 목록 조회"""
    items, total = await job_handler.get_list(
        page=page,
        size=size,
        cron_id=cron_id,
        status=status,
        from_date=from_date,
        to_date=to_date,
    )
    pages = (total + size - 1) // size if size > 0 else 0
    return JobListResponse(
        items=items,
        total=total,
        page=page,
        size=size,
        pages=pages,
    )


@router.get("/api/jobs/{job_id}", response_model=JobResponse, tags=["Job"])
async def get_job(job_id: int):
    """잡 실행 이력 상세 조회"""
    try:
        return await job_handler.get_by_id(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/jobs/{job_id}/retry", response_model=JobResponse, tags=["Job"])
async def retry_job(job_id: int):
    """실패한 잡 재시도"""
    try:
        return await job_handler.retry(job_id)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except JobStatusError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/api/jobs/{job_id}", status_code=204, tags=["Job"])
async def delete_job(job_id: int):
    """잡 실행 이력 삭제"""
    try:
        await job_handler.delete(job_id)
        return Response(status_code=204)
    except JobNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================
# Health Check
# ============================================

@router.get("/health", tags=["Health"])
async def health_check():
    """서버 상태 확인 (liveness probe)"""
    from database import get_db
    try:
        db = get_db()
        db_status = "connected" if db.pool.available > 0 else "busy"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "healthy",
        "database": db_status,
        "version": "1.0.0",
    }


@router.get("/ready", tags=["Health"])
async def ready_check():
    """DB 연결 상태 확인 (readiness probe)"""
    from database import get_db
    from fastapi.responses import JSONResponse

    try:
        db = get_db()
        async with db.transaction(readonly=True) as ctx:
            await ctx.fetch_val("SELECT 1")
        return {"status": "ready", "database": "ok"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "error": str(e)}
        )
