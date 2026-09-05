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

    # Local SOCKS/HTTP proxy (same flags as Telethon listener)
    use_proxy: bool = False
    proxy_type: str = "socks5"
    proxy_host: str = "127.0.0.1"
    proxy_port: int = 10808

    # Notifier bot (Phase 6 deep link)
    bot_token: str | None = None
    bot_username: str | None = None
    notifier_bot_token: str | None = None

    @property
    def resolved_bot_token(self) -> str | None:
        """BOT_TOKEN, falling back to NOTIFIER_BOT_TOKEN."""
        raw = (self.bot_token or self.notifier_bot_token or "").strip()
        return raw or None

    @property
    def resolved_bot_username(self) -> str | None:
        raw = (self.bot_username or "").strip().lstrip("@")
        return raw or None

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
