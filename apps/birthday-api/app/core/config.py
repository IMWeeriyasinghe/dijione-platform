from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "sqlite:///./birthday.db"

    integrations_mode: str = "mock"
    # Gates INBOUND supplier-mail polling only (GraphInboundMailClient vs.
    # MockInboundMailClient) — inbound is out of scope for the Managed
    # Identity migration and still uses the client-credentials
    # graph_tenant_id/graph_client_id/graph_client_secret trio below.
    # Independent from integrations_mode (Phase-Next §7/§8) so BambooHR can
    # stay live while inbound mail stays mocked. Outbound email transport
    # is governed separately by mail_transport (below), not this setting.
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
    # Phase 1.6 §9 root-cause fix: people-api scales to zero in DEV
    # (minReplicas=0); a measured cold start took 23s against the old
    # hard-coded 5s timeout, which was the actual cause of the daily scan's
    # consecutive DEFERRED_SOURCE_UNAVAILABLE runs. Deployment-visible via
    # PEOPLE_API_TIMEOUT_SECONDS (see deploy/bicep/main.bicep), not buried
    # in code.
    people_api_timeout_seconds: float = 30.0

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

    # --- Outbound mail (packages/mail-client-py) -------------------------
    # "null"  -> NullMailTransport, no real email ever leaves the system.
    # "graph" -> GraphMailTransport, authenticates via this Container App's
    #            own system-assigned Managed Identity (DefaultAzureCredential)
    #            — never a client secret. Safe by default: null.
    mail_transport: str = "null"
    # "disabled" (safe default) | "internal_allowlist" | "production".
    # Unknown/misconfigured values behave as "disabled" — fail closed,
    # never a silent pass-through. See resolve_policy() in mail_client_py.
    mail_policy: str = "disabled"
    # The one mailbox this service ever sends as — e.g.
    # "appassistant@dijitalteam.com". Exchange, not this code, resolves the
    # sender display name at send time.
    mail_shared_mailbox: str = ""
    # Comma-separated exact addresses and/or "@domain" entries, read only
    # when mail_policy == "internal_allowlist". DEV must be one or more
    # explicit test addresses, never a bare "@dijitalteam.com" domain entry.
    mail_allowlist: str = ""

    # --- Inbound mail (client-credentials, out of scope for the Managed
    # Identity migration — see app/integrations/inbound_mail/) -----------
    # tenant/client/secret are read ONLY by GraphInboundMailClient today;
    # the outbound path (mail_transport above) needs none of them.
    graph_tenant_id: str = ""
    graph_client_id: str = ""
    graph_client_secret: str = ""
    # Shared mailbox polled for supplier email replies (Phase 1 §1.5).
    # Same Graph app registration as legacy outbound + the Mail.Read
    # permission — untouched by this round's outbound migration.
    graph_inbox_mailbox: str = ""
    graph_base_url: str = "https://graph.microsoft.com/v1.0"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.api_cors_origins.split(",") if origin.strip()]

    @property
    def mail_allowlist_list(self) -> list[str]:
        return [a.strip() for a in self.mail_allowlist.split(",") if a.strip()]

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
