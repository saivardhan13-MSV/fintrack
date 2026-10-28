from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from FINTRACK_* environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="FINTRACK_", extra="ignore")

    database_url: str = "sqlite:///./fintrack.db"
    jwt_secret: str = "dev-only-secret-change-me-in-every-real-deployment"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60
    password_hash_iterations: int = 600_000  # OWASP 2023 guidance for PBKDF2-SHA256
    max_upload_bytes: int = 5 * 1024 * 1024
    log_level: str = "INFO"
    # Hosted demos: load the demo account's data on every startup.
    seed_demo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
