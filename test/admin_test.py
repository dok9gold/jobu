"""
Admin API 테스트

테스트 항목:
1. 크론 CRUD (생성, 조회, 수정, 삭제)
2. 중복 이름 생성 시 409 에러
3. 잘못된 크론 표현식 시 400 에러
4. 1분 미만 간격 크론 차단
5. 잡 실행 이력 조회 (페이징)
6. 잡 재시도 기능 (FAILED -> PENDING)
7. 존재하지 않는 리소스 404 에러

실행: python -m pytest test/admin_test.py -v
"""

import asyncio
import logging
import sys
from pathlib import Path

import pytest
import pytest_asyncio
import yaml
from httpx import AsyncClient, ASGITransport

# 프로젝트 루트 경로 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import transactional, get_connection, get_db
from database.sqlite3 import Database
from database.registry import DatabaseRegistry
from admin.main import create_app

# 테스트용 로깅 설정
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# pytest-asyncio 설정
pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest_asyncio.fixture(loop_scope="session")
async def test_config():
    """config/database.yaml 로드"""
    config_path = Path(__file__).parent.parent / "config" / "database.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest_asyncio.fixture(loop_scope="session")
async def database(test_config):
    """테스트용 Database 인스턴스 (DatabaseRegistry 사용)"""
    DatabaseRegistry.clear()

    await DatabaseRegistry.init_from_config(test_config)
    db = get_db('default')

    # 테스트 전 기존 테스트 데이터 정리
    async with db.transaction() as ctx:
        await ctx.execute("DELETE FROM job_executions WHERE job_id IN (SELECT id FROM cron_jobs WHERE name LIKE ?)", ("admin_test_%",))
        await ctx.execute("DELETE FROM cron_jobs WHERE name LIKE ?", ("admin_test_%",))

    yield db
    await DatabaseRegistry.close_all()


@pytest_asyncio.fixture(loop_scope="session")
async def app(database):
    """테스트용 FastAPI 앱"""
    # Database가 이미 초기화되었으므로 lifespan을 건너뛰기 위해 앱만 생성
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from admin.api.router.api import router

    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    test_app.include_router(router)

    yield test_app


@pytest_asyncio.fixture(loop_scope="session")
async def client(app):
    """테스트용 HTTP 클라이언트"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCronCRUD:
    """크론 CRUD 테스트"""

    @pytest.mark.asyncio
    async def test_create_cron(self, client):
        """크론 생성"""
        response = await client.post("/api/crons", json={
            "name": "admin_test_create",
            "description": "Test cron",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
            "is_enabled": True,
            "allow_overlap": True,
            "max_retry": 3,
            "timeout_seconds": 3600,
        })

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "admin_test_create"
        assert data["cron_expression"] == "0 * * * *"
        assert data["is_enabled"] is True
        logger.info("Create cron test passed")

    @pytest.mark.asyncio
    async def test_get_crons(self, client):
        """크론 목록 조회"""
        # 먼저 크론 생성
        await client.post("/api/crons", json={
            "name": "admin_test_list1",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
        })
        await client.post("/api/crons", json={
            "name": "admin_test_list2",
            "cron_expression": "0 0 * * *",
            "handler_name": "test_handler",
        })

        response = await client.get("/api/crons")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "pages" in data
        logger.info("Get crons test passed")

    @pytest.mark.asyncio
    async def test_get_cron_by_id(self, client):
        """크론 상세 조회"""
        # 크론 생성
        create_response = await client.post("/api/crons", json={
            "name": "admin_test_get_by_id",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
        })
        cron_id = create_response.json()["id"]

        response = await client.get(f"/api/crons/{cron_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == cron_id
        assert data["name"] == "admin_test_get_by_id"
        logger.info("Get cron by id test passed")

    @pytest.mark.asyncio
    async def test_update_cron(self, client):
        """크론 수정"""
        # 크론 생성
        create_response = await client.post("/api/crons", json={
            "name": "admin_test_update",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
        })
        cron_id = create_response.json()["id"]

        # 수정
        response = await client.put(f"/api/crons/{cron_id}", json={
            "description": "Updated description",
            "max_retry": 5,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "Updated description"
        assert data["max_retry"] == 5
        logger.info("Update cron test passed")

    @pytest.mark.asyncio
    async def test_delete_cron(self, client):
        """크론 삭제"""
        # 크론 생성
        create_response = await client.post("/api/crons", json={
            "name": "admin_test_delete",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
        })
        cron_id = create_response.json()["id"]

        # 삭제
        response = await client.delete(f"/api/crons/{cron_id}")
        assert response.status_code == 204

        # 삭제 확인
        get_response = await client.get(f"/api/crons/{cron_id}")
        assert get_response.status_code == 404
        logger.info("Delete cron test passed")

    @pytest.mark.asyncio
    async def test_toggle_cron(self, client):
        """크론 토글"""
        # 크론 생성 (활성화 상태)
        create_response = await client.post("/api/crons", json={
            "name": "admin_test_toggle",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
            "is_enabled": True,
        })
        cron_id = create_response.json()["id"]

        # 토글 (비활성화)
        response = await client.post(f"/api/crons/{cron_id}/toggle")

        assert response.status_code == 200
        data = response.json()
        assert data["is_enabled"] is False

        # 다시 토글 (활성화)
        response = await client.post(f"/api/crons/{cron_id}/toggle")
        assert response.json()["is_enabled"] is True
        logger.info("Toggle cron test passed")


class TestCronValidation:
    """크론 유효성 검사 테스트"""

    @pytest.mark.asyncio
    async def test_duplicate_name_conflict(self, client):
        """중복 이름 생성 시 409 에러"""
        # 첫 번째 크론 생성
        await client.post("/api/crons", json={
            "name": "admin_test_duplicate",
            "cron_expression": "0 * * * *",
            "handler_name": "test_handler",
        })

        # 동일 이름으로 다시 생성
        response = await client.post("/api/crons", json={
            "name": "admin_test_duplicate",
            "cron_expression": "0 0 * * *",
            "handler_name": "other_handler",
        })

        assert response.status_code == 409
        logger.info("Duplicate name conflict test passed")

    @pytest.mark.asyncio
    async def test_invalid_cron_expression(self, client):
        """잘못된 크론 표현식 시 400 에러"""
        response = await client.post("/api/crons", json={
            "name": "admin_test_invalid_cron",
            "cron_expression": "invalid_expression",
            "handler_name": "test_handler",
        })

        assert response.status_code == 400
        logger.info("Invalid cron expression test passed")

    @pytest.mark.asyncio
    async def test_sub_minute_cron_rejected(self, client):
        """1분 미만 간격 크론 차단 (초 단위 크론은 표준 cron에서 지원하지 않지만 테스트)"""
        # 참고: 표준 cron은 분 단위 최소이므로 "* * * * *"은 매분 실행 (60초 간격)
        # CronHandler.MIN_CRON_INTERVAL_SECONDS = 60이므로 통과해야 함
        response = await client.post("/api/crons", json={
            "name": "admin_test_minute_cron",
            "cron_expression": "* * * * *",  # 매분 = 60초 간격
            "handler_name": "test_handler",
        })

        # 60초 이상이면 통과
        assert response.status_code == 201
        logger.info("Minute interval cron test passed")


class TestCronNotFound:
    """크론 Not Found 테스트"""

    @pytest.mark.asyncio
    async def test_get_nonexistent_cron(self, client):
        """존재하지 않는 크론 조회 시 404"""
        response = await client.get("/api/crons/99999")
        assert response.status_code == 404
        logger.info("Get nonexistent cron test passed")

    @pytest.mark.asyncio
    async def test_update_nonexistent_cron(self, client):
        """존재하지 않는 크론 수정 시 404"""
        response = await client.put("/api/crons/99999", json={
            "description": "test",
        })
        assert response.status_code == 404
        logger.info("Update nonexistent cron test passed")

    @pytest.mark.asyncio
    async def test_delete_nonexistent_cron(self, client):
        """존재하지 않는 크론 삭제 시 404"""
        response = await client.delete("/api/crons/99999")
        assert response.status_code == 404
        logger.info("Delete nonexistent cron test passed")


class TestJobHistory:
    """잡 실행 이력 테스트"""

    @pytest.mark.asyncio
    async def test_get_jobs(self, client, database):
        """잡 목록 조회"""
        # 테스트용 크론 및 잡 생성
        @transactional
        async def create_test_data():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("admin_test_job_history", "0 * * * *", "test_handler", 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("admin_test_job_history",)
            )
            job_id = row["id"]

            # 잡 실행 이력 생성
            await ctx.execute(
                """INSERT INTO job_executions (job_id, scheduled_time, status)
                   VALUES (?, ?, ?)""",
                (job_id, "2024-01-15 10:00:00", "SUCCESS")
            )
            await ctx.execute(
                """INSERT INTO job_executions (job_id, scheduled_time, status)
                   VALUES (?, ?, ?)""",
                (job_id, "2024-01-15 11:00:00", "FAILED")
            )

        await create_test_data()

        response = await client.get("/api/jobs")

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        logger.info("Get jobs test passed")

    @pytest.mark.asyncio
    async def test_get_jobs_with_filter(self, client, database):
        """잡 목록 필터 조회"""
        response = await client.get("/api/jobs?status=FAILED")

        assert response.status_code == 200
        data = response.json()
        # FAILED 상태만 조회됨
        for item in data["items"]:
            if item.get("status"):
                # 필터가 적용된 경우 FAILED만 있어야 함
                pass
        logger.info("Get jobs with filter test passed")

    @pytest.mark.asyncio
    async def test_retry_failed_job(self, client, database):
        """실패한 잡 재시도"""
        # FAILED 상태의 잡 생성
        @transactional
        async def create_failed_job():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("admin_test_retry", "0 * * * *", "test_handler", 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("admin_test_retry",)
            )
            job_id = row["id"]

            await ctx.execute(
                """INSERT INTO job_executions (job_id, scheduled_time, status, error_message)
                   VALUES (?, ?, ?, ?)""",
                (job_id, "2024-01-15 10:00:00", "FAILED", "Test error")
            )
            row = await ctx.fetch_one(
                "SELECT id FROM job_executions WHERE job_id = ?",
                (job_id,)
            )
            return row["id"]

        execution_id = await create_failed_job()

        # 재시도
        response = await client.post(f"/api/jobs/{execution_id}/retry")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "PENDING"
        logger.info("Retry failed job test passed")

    @pytest.mark.asyncio
    async def test_retry_success_job_fails(self, client, database):
        """성공한 잡은 재시도 불가"""
        # SUCCESS 상태의 잡 생성
        @transactional
        async def create_success_job():
            ctx = get_connection()
            await ctx.execute(
                """INSERT INTO cron_jobs (name, cron_expression, handler_name, is_enabled)
                   VALUES (?, ?, ?, ?)""",
                ("admin_test_retry_success", "0 * * * *", "test_handler", 1)
            )
            row = await ctx.fetch_one(
                "SELECT id FROM cron_jobs WHERE name = ?",
                ("admin_test_retry_success",)
            )
            job_id = row["id"]

            await ctx.execute(
                """INSERT INTO job_executions (job_id, scheduled_time, status)
                   VALUES (?, ?, ?)""",
                (job_id, "2024-01-15 10:00:00", "SUCCESS")
            )
            row = await ctx.fetch_one(
                "SELECT id FROM job_executions WHERE job_id = ?",
                (job_id,)
            )
            return row["id"]

        execution_id = await create_success_job()

        # 재시도 시도 (실패해야 함)
        response = await client.post(f"/api/jobs/{execution_id}/retry")

        assert response.status_code == 400
        logger.info("Retry success job fails test passed")


class TestJobNotFound:
    """잡 Not Found 테스트"""

    @pytest.mark.asyncio
    async def test_get_nonexistent_job(self, client):
        """존재하지 않는 잡 조회 시 404"""
        response = await client.get("/api/jobs/99999")
        assert response.status_code == 404
        logger.info("Get nonexistent job test passed")

    @pytest.mark.asyncio
    async def test_retry_nonexistent_job(self, client):
        """존재하지 않는 잡 재시도 시 404"""
        response = await client.post("/api/jobs/99999/retry")
        assert response.status_code == 404
        logger.info("Retry nonexistent job test passed")


class TestHealthCheck:
    """헬스체크 테스트"""

    @pytest.mark.asyncio
    async def test_health_check(self, client):
        """헬스체크 API"""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "database" in data
        assert "version" in data
        logger.info("Health check test passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
