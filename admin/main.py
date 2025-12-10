"""Admin API 서버 진입점"""

import logging
from pathlib import Path
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database.registry import DatabaseRegistry
from admin.api.router.api import router, cron_handler, job_handler

logger = logging.getLogger(__name__)

# 템플릿 설정
TEMPLATES_DIR = Path(__file__).parent / "front"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def load_config() -> dict:
    """설정 파일 로드"""
    config_path = Path(__file__).parent.parent / "config"

    # admin.yaml 로드
    admin_config_path = config_path / "admin.yaml"
    with open(admin_config_path, 'r', encoding='utf-8') as f:
        admin_config = yaml.safe_load(f)

    # database.yaml 로드
    db_config_path = config_path / "database.yaml"
    with open(db_config_path, 'r', encoding='utf-8') as f:
        db_config = yaml.safe_load(f)

    return {**admin_config, **db_config}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리"""
    # 시작 시
    config = load_config()
    admin_config = config.get('admin', {})
    db_name = admin_config.get('database', 'default')

    # 지정된 DB만 초기화
    await DatabaseRegistry.init_from_config(config, [db_name])
    logger.info("Database initialized")

    yield

    # 종료 시
    await DatabaseRegistry.close_all()
    logger.info("Database closed")


def create_app() -> FastAPI:
    """FastAPI 앱 생성"""
    config = load_config()
    admin_config = config.get('admin', {})

    app = FastAPI(
        title="JobU Admin API",
        description="크론 잡 관리 Admin API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS 설정
    cors_config = admin_config.get('cors', {})
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_config.get('origins', ['*']),
        allow_credentials=cors_config.get('allow_credentials', True),
        allow_methods=cors_config.get('allow_methods', ['*']),
        allow_headers=cors_config.get('allow_headers', ['*']),
    )

    # API 라우터 등록
    app.include_router(router)

    # HTML 화면 라우트
    @app.get("/crons", response_class=HTMLResponse, include_in_schema=False)
    async def crons_page(request: Request):
        """크론 관리 화면"""
        return templates.TemplateResponse("cron.html", {"request": request})

    @app.get("/jobs", response_class=HTMLResponse, include_in_schema=False)
    async def jobs_page(request: Request):
        """잡 이력 조회 화면"""
        crons = await cron_handler.get_all_for_select()
        return templates.TemplateResponse("job.html", {"request": request, "crons": crons})

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index(request: Request):
        """메인 페이지 - 크론 관리로 리다이렉트"""
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/crons")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = load_config()
    admin_config = config.get('admin', {})

    uvicorn.run(
        "admin.main:app",
        host=admin_config.get('host', '0.0.0.0'),
        port=admin_config.get('port', 8080),
        reload=admin_config.get('debug', True),
    )
