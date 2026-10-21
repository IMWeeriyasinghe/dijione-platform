from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Diji On-site API settings. The only external application URLs are the
    shared platform/source contracts (platform-api, people-api) — see
    docs/onsite/architecture.md "Allowed dependencies"."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./onsite.db"

    # "mock" (default, CI/local) or "live" (Azure SQL onsite.* via attendance_source).
    integrations_mode: str = "mock"
    # Azure SQL source (SELECT-only, Entra managed-identity token, no password).
    onsite_sql_server: str = ""  # fully qualified server host name
    onsite_sql_database: str = ""  # e.g. sqldb-diji-onsite

    # Mirror sync (docs/onsite/architecture.md "Data flow").
    sync_page_size: int = 5000
    sync_overlap_minutes: int = 10
    # Total time to keep retrying a source connection (serverless resume).
    sync_source_retry_seconds: float = 90.0
    # Expected scheduled cadence — drives the "Delayed" freshness state.
    sync_cadence_minutes: int = 360
    # Agent heartbeat older than this => "Stale" (On-site alert threshold).
    heartbeat_stale_minutes: int = 10
    # Neutral review flags.
    high_punch_count_threshold: int = 8
    duplicate_tap_seconds: int = 60

    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3004,http://127.0.0.1:3000,http://127.0.0.1:3004"
    )

    platform_jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    platform_api_url: str = "http://localhost:8000"
    # Optional: when empty or unreachable, On-site shows raw EmpCodes only.
    people_api_url: str = "http://localhost:8006"
    people_api_timeout_seconds: float = 30.0
    workforce_cache_ttl_seconds: int = 600

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
