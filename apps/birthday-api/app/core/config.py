from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./birthday.db"

    integrations_mode: str = "mock"
    # Independent from integrations_mode (Phase-Next §7/§8): lets BambooHR
    # stay live while email sending stays mocked during the dry-run phase,
    # rather than one shared switch forcing both integrations to move
    # together. Defaults mock — real supplier email requires an explicit
    # opt-in, never an accidental side effect of enabling live BambooHR.
    email_sending_mode: str = "mock"

    api_cors_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )

    # Must match platform-api's JWT_DEV_SECRET — birthday-api verifies
    # tokens locally from claims, exactly like talent-api, proving the
    # module-framework authorization seam works before any real business
    # logic exists (CR §9).
    jwt_dev_secret: str = "dev-only-insecure-secret-change-me"
    jwt_algorithm: str = "HS256"

    platform_api_url: str = "http://localhost:8000"
    people_api_url: str = "http://localhost:8006"
    # Must match platform-api's INTERNAL_SERVICE_SECRET.
    internal_service_secret: str = "dev-only-internal-secret-change-me"

    # --- Supplier Portal authentication ---------------------------------
    # "dev"   -> the seeded SupplierUser persona picker
    #            (/api/birthday/internal/dev/supplier-*), local/dry-run only.
    # "entra" -> real Microsoft Entra ID B2B guest sign-in (Authorization
    #            Code + PKCE). The persona routes 404 in this mode. Requires
    #            supplier_entra_{tenant_id,client_id,client_secret,redirect_uri}
    #            + supplier_public_base_url. Independent of the internal
    #            DijiOne staff AUTH_MODE — a separate app registration and a
    #            separate trust boundary.
    supplier_auth_mode: str = "dev"
    supplier_entra_tenant_id: str = ""
    supplier_entra_client_id: str = ""
    supplier_entra_client_secret: str = ""
    supplier_entra_redirect_uri: str = ""
    supplier_public_base_url: str = ""

    # Microsoft Graph email adapter (plan §9) — client-credentials flow.
    # Unset until the user completes Graph app registration; GraphEmailClient
    # raises GraphNotConfiguredError until all four are set.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    graph_sender_mailbox: str = ""
    # Shared mailbox polled for supplier email replies (Phase 1 §1.5).
    # Same Graph app registration as outbound + the Mail.Read permission.
    graph_inbox_mailbox: str = ""
    graph_base_url: str = "https://graph.microsoft.com/v1.0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def dev_supplier_auth_enabled(self) -> bool:
        """The seeded-persona supplier login path is reachable only in
        explicit dev mode — NOT keyed off app_env, so a hosted DEV with
        supplier_auth_mode=entra correctly 404s it."""
        return self.supplier_auth_mode == "dev"

    @property
    def supplier_entra_authority(self) -> str:
        return f"https://login.microsoftonline.com/{self.supplier_entra_tenant_id}"

    @property
    def supplier_entra_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.supplier_entra_tenant_id}/v2.0"

    @property
    def supplier_entra_jwks_uri(self) -> str:
        return f"{self.supplier_entra_authority}/discovery/v2.0/keys"


@lru_cache
def get_settings() -> Settings:
    return Settings()
