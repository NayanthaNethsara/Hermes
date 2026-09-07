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
from src.backend.retrieval.router import router as retrieval_router

configure_logging()
logger = get_logger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("archivist_backend_starting_up")
    await init_database()
    yield
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
        return {"status": "ok", "service": "archivist-backend"}

    return app


app = create_app()
