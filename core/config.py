"""Application configuration via Pydantic BaseSettings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    secret_key: str = "changeme"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # PostgreSQL
    postgres_user: str = "telegram_listener"
    postgres_password: str = "changeme"
    postgres_db: str = "telegram_listener"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # Redis
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_url: str | None = None

    @property
    def resolved_redis_url(self) -> str:
        """Redis URL shared by API, Celery, and sync cache clients."""
        if self.redis_url:
            return self.redis_url
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    # Telegram
    telegram_api_id: int | None = None
    telegram_api_hash: str | None = None

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy connection URL for PostgreSQL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()
