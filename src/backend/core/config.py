from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(REPOSITORY_ROOT / ".env"), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/archivist",
        alias="DATABASE_URL",
    )

    @property
    def psycopg_dsn(self) -> str:
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    redis_url: str = Field(
        default="redis://localhost:6379/0", alias="REDIS_URL"
    )
    redis_rate_limit_requests: int = Field(
        default=30, alias="REDIS_RATE_LIMIT_REQUESTS"
    )
    redis_rate_limit_window_seconds: int = Field(
        default=60, alias="REDIS_RATE_LIMIT_WINDOW_SECONDS"
    )
    redis_cache_ttl_seconds: int = Field(
        default=3600, alias="REDIS_CACHE_TTL_SECONDS"
    )

    voyage_api_key: str = Field(default="", alias="VOYAGE_API_KEY")
    voyage_embedding_model: str = Field(
        default="voyage-multimodal-3.5", alias="VOYAGE_MODEL"
    )
    voyage_rerank_model: str = Field(
        default="rerank-2.5", alias="VOYAGE_RERANK_MODEL"
    )

    gcp_project_id: str = Field(default="", alias="GCP_PROJECT_ID")
    gcp_location: str = Field(default="global", alias="GCP_LOCATION")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL"
    )
    openrouter_model: str = Field(
        default="google/gemini-2.0-flash-exp:free", alias="OPENROUTER_MODEL"
    )

    raw_archive_dir: Path = Field(
        default=REPOSITORY_ROOT / "data" / "raw_archive", alias="RAW_ARCHIVE_DIR"
    )
    extracted_assets_dir: Path = Field(
        default=REPOSITORY_ROOT / "data" / "extracted_assets",
        alias="ASSETS_DIR",
    )

    rerank_score_threshold: float = Field(
        default=0.50, alias="RERANK_SCORE_THRESHOLD"
    )
    retrieval_candidate_limit: int = Field(
        default=50, alias="RETRIEVAL_CANDIDATE_LIMIT"
    )
    rerank_top_k: int = Field(default=5, alias="RERANK_TOP_K")
    max_search_iterations: int = Field(default=5, alias="MAX_SEARCH_HOPS")

    weight_codex: float = Field(default=1.0, alias="WEIGHT_CODEX")
    weight_image: float = Field(default=1.0, alias="WEIGHT_IMAGE")
    weight_wiki: float = Field(default=0.8, alias="WEIGHT_WIKI")
    weight_novel: float = Field(default=0.6, alias="WEIGHT_NOVEL")
    weight_ephemera: float = Field(default=0.4, alias="WEIGHT_EPHEMERA")

    def get_epistemic_weight(self, source_category: str) -> float:
        category_weights = {
            "codex": self.weight_codex,
            "image": self.weight_image,
            "wiki": self.weight_wiki,
            "novel": self.weight_novel,
            "ephemera": self.weight_ephemera,
        }
        return category_weights.get(source_category.lower(), 0.5)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
