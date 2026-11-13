from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Diji On-site API settings. The only external application URLs are the
    shared platform/source contracts (platform-api, people-api) — see
    docs/onsite/architecture.md "Allowed dependencies"."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./onsite.db"

    # "mock" (default, CI/local), "live" (Azure SQL onsite.* via attendance_source)
    # or "none" (no attendance source provisioned for this environment yet:
    # the app runs, nothing is ever synced and health says so).
    integrations_mode: str = "mock"
    # Azure SQL source (SELECT-only, Entra managed-identity token, no password).
    onsite_sql_server: str = ""  # fully qualified server host name
    onsite_sql_database: str = ""  # e.g. sqldb-diji-onsite-attendance

    # Mirror sync (docs/onsite/architecture.md "Data flow").
    sync_page_size: int = 5000
    sync_overlap_minutes: int = 10
    # Total time to keep retrying a source connection (serverless resume).
    sync_source_retry_seconds: float = 90.0
    # Scheduled cadence (onsite-sync-job cron ``* * * * *``; docs/onsite/deployment.md).
    sync_cadence_minutes: int = 1
    # Last successful mirror sync older than this => "Delayed" (a few missed ticks).
    sync_delayed_minutes: int = 5
    # A QUEUED/RUNNING run older than this was abandoned (replica stopped
    # mid-run); the next request marks it FAILED instead of waiting forever.
    sync_stale_run_minutes: int = 10
    # Source-vs-mirror reconciliation (a full per-epoch aggregate on Azure SQL)
    # runs when a sync inserted rows, otherwise at most this often.
    sync_reconcile_minutes: int = 15
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
    # Identity redesign switches (architecture review §I.2 / §I.4).
    # ONSITE_LEGACY_CONTRACT keeps the pre-redesign response shapes and the
    # code-addressed employee routes for the running onsite-web (values are
    # always derived from verified mappings). ONSITE_IDENTITY_WRITES_ENABLED=false
    # freezes Identity Management writes (forward-only recovery).
    onsite_legacy_contract: bool = True
    onsite_identity_writes_enabled: bool = True
    workforce_cache_ttl_seconds: int = 600

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def source_configured(self) -> bool:
        """False when no attendance source exists for this environment."""
        return self.integrations_mode in ("mock", "live")


@lru_cache
def get_settings() -> Settings:
    return Settings()
