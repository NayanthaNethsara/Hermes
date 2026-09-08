from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.backend.agents.router import router as agents_router
from src.backend.core.config import get_settings
from src.backend.core.database import init_database
from src.backend.core.exceptions import register_exception_handlers
from src.backend.core.logging import configure_logging, get_logger
from src.backend.core.rate_limit import RateLimitMiddleware
from src.backend.core.redis import check_redis_health, close_redis_client
from src.backend.retrieval.router import router as retrieval_router

configure_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("archivist_backend_starting_up")
    await init_database()
    redis_healthy = await check_redis_health()
    logger.info("redis_health_status", healthy=redis_healthy)
    yield
    await close_redis_client()
    logger.info("archivist_backend_shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="The Archivist Backend",
        description="Multimodal Research Assistant for the Ashen Era Archive",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RateLimitMiddleware)

    register_exception_handlers(app)

    settings.extracted_assets_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/assets",
        StaticFiles(directory=str(settings.extracted_assets_dir)),
        name="assets",
    )

    app.include_router(retrieval_router)
    app.include_router(agents_router)

    @app.get("/api/health")
    async def health_check() -> dict[str, str]:
        redis_healthy = await check_redis_health()
        return {
            "status": "ok",
            "service": "archivist-backend",
            "redis": "connected" if redis_healthy else "unavailable",
        }

    return app


app = create_app()
