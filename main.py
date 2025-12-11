"""
jobu 통합 진입점

Dispatcher, Worker, Admin API를 한 번에 실행합니다.

사용법:
    python main.py                 # 전체 실행
    python main.py dispatcher      # Dispatcher만
    python main.py worker          # Worker만
    python main.py admin           # Admin API만
    python main.py dispatcher worker  # 복수 선택
"""

import sys
import os

# Windows 인코딩 설정 (cp949 -> UTF-8)
if sys.platform == "win32":
    os.environ["PYTHONUTF8"] = "1"
    
import asyncio
import signal
import logging
from pathlib import Path

import yaml

from database.registry import DatabaseRegistry

logger = logging.getLogger(__name__)


async def run_dispatcher(config: dict, stop_event: asyncio.Event):
    """Dispatcher 실행"""
    from dispatcher.main import Dispatcher
    from dispatcher.model.dispatcher import DispatcherConfig

    dispatcher_config = DispatcherConfig(**config.get("dispatcher", {}))
    dispatcher = Dispatcher(dispatcher_config)

    async def wait_stop():
        await stop_event.wait()
        await dispatcher.stop()

    asyncio.create_task(wait_stop())
    await dispatcher.start()


async def run_worker(config: dict, stop_event: asyncio.Event):
    """Worker 실행"""
    from worker.main import WorkerPool, WorkerConfig, _load_handlers

    _load_handlers()
    worker_config = WorkerConfig(**config.get("worker", {}))
    worker_pool = WorkerPool(worker_config)

    async def wait_stop():
        await stop_event.wait()
        await worker_pool.stop()

    asyncio.create_task(wait_stop())
    await worker_pool.start()


async def run_admin(config: dict, stop_event: asyncio.Event):
    """Admin API 실행"""
    import uvicorn
    from admin.main import app

    admin_config = config.get("admin", {})
    uv_config = uvicorn.Config(
        app,
        host=admin_config.get("host", "0.0.0.0"),
        port=admin_config.get("port", 8080),
        log_level="info",
    )
    server = uvicorn.Server(uv_config)

    async def wait_stop():
        await stop_event.wait()
        server.should_exit = True

    asyncio.create_task(wait_stop())
    await server.serve()


async def main(modules: list[str]):
    """메인 함수"""
    config_path = Path(__file__).parent / "config"

    # 설정 로드
    with open(config_path / "database.yaml", encoding="utf-8") as f:
        db_config = yaml.safe_load(f)

    with open(config_path / "dispatcher.yaml", encoding="utf-8") as f:
        dispatcher_config = yaml.safe_load(f)

    with open(config_path / "worker.yaml", encoding="utf-8") as f:
        worker_config = yaml.safe_load(f)

    with open(config_path / "admin.yaml", encoding="utf-8") as f:
        admin_config = yaml.safe_load(f)

    config = {**db_config, **dispatcher_config, **worker_config, **admin_config}

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # 필요한 DB 목록 수집
    db_names = set()
    if "dispatcher" in modules:
        db_names.add(config.get("dispatcher", {}).get("database", "default"))
    if "worker" in modules:
        worker_cfg = config.get("worker", {})
        db_names.add(worker_cfg.get("database", "default"))
        db_names.update(worker_cfg.get("databases", []))
    if "admin" in modules:
        db_names.add(config.get("admin", {}).get("database", "default"))

    # DB 초기화
    await DatabaseRegistry.init_from_config(config, list(db_names))

    # 종료 이벤트
    stop_event = asyncio.Event()

    # 시그널 핸들러
    loop = asyncio.get_running_loop()

    def signal_handler():
        logger.info("Received shutdown signal")
        stop_event.set()

    # Windows는 add_signal_handler를 지원하지 않음
    if sys.platform != "win32":
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    # 태스크 생성
    tasks = []
    if "dispatcher" in modules:
        tasks.append(asyncio.create_task(run_dispatcher(config, stop_event)))
        logger.info("Dispatcher started")
    if "worker" in modules:
        tasks.append(asyncio.create_task(run_worker(config, stop_event)))
        logger.info("Worker started")
    if "admin" in modules:
        tasks.append(asyncio.create_task(run_admin(config, stop_event)))
        logger.info("Admin API started")

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Tasks cancelled")
    finally:
        await DatabaseRegistry.close_all()
        logger.info("All modules stopped")


if __name__ == "__main__":
    # 인자 파싱
    args = sys.argv[1:]
    valid_modules = {"dispatcher", "worker", "admin"}

    if args:
        modules = [m for m in args if m in valid_modules]
        if not modules:
            print(f"Usage: python main.py [dispatcher] [worker] [admin]")
            sys.exit(1)
    else:
        modules = ["dispatcher", "worker", "admin"]

    print(f"Starting jobu: {', '.join(modules)}")
    try:
        asyncio.run(main(modules))
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
