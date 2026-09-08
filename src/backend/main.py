from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.backend.agents.router import router as agents_router
from src.backend.core.config import get_settings
from src.backend.core.database import check_database_health, close_database, init_database
from src.backend.core.exceptions import register_exception_handlers
from src.backend.core.logging import configure_logging, get_logger
from src.backend.core.rate_limit import RateLimitMiddleware
from src.backend.core.redis import check_redis_health, close_redis_client
from src.backend.retrieval.router import router as retrieval_router

configure_logging()
logger = get_logger("main")

OPENAPI_TAGS = [
    {"name": "agents", "description": "Ask questions and manage conversation sessions."},
    {"name": "retrieval", "description": "Search the archive, inspect documents and visual assets."},
    {"name": "system", "description": "Service health."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("hermes_backend_starting_up")
    # Neither check aborts startup: the API stays up and reports the outage per
    # request, so a stopped container does not require a backend restart.
    await init_database()
    database_healthy = await check_database_health()
    redis_healthy = await check_redis_health()
    logger.info(
        "dependency_health_status",
        database=database_healthy,
        redis=redis_healthy,
    )
    yield
    await close_redis_client()
    await close_database()
    logger.info("hermes_backend_shutting_down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Hermes API",
        description=(
            "Research assistant for the Ashen Era Archive.\n\n"
            "`/api/ask/stream` and `/agents/stream` return Server-Sent Events and "
            "cannot be exercised from this page; their event contract is documented "
            "in `docs/api.md`."
        ),
        version="0.2.0",
        openapi_tags=OPENAPI_TAGS,
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

    @app.get("/api/health", tags=["system"], summary="Service health")
    async def health_check() -> dict[str, str]:
        database_healthy = await check_database_health()
        redis_healthy = await check_redis_health()
        return {
            "status": "ok" if database_healthy and redis_healthy else "degraded",
            "service": "hermes-backend",
            "database": "connected" if database_healthy else "unavailable",
            "redis": "connected" if redis_healthy else "unavailable",
        }

    return app


app = create_app()
