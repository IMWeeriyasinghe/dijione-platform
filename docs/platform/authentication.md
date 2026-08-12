# DijiOne Authentication & Authorization

## Production target

```mermaid
flowchart LR
    U[User] --> ENTRA[Microsoft Entra ID]
    ENTRA -->|OIDC Authorization Code + PKCE| WEB[DijiOne Next.js]
    WEB -->|Bearer access token| API[FastAPI]
    API -->|validate signature/issuer/audience/expiry/roles| API
    API --> DB[(Database)]
```

FastAPI validates, on every request:

- token signature (against Entra's JWKS)
- issuer and audience
- expiry
- role/group claims
- module permission scope
- client/tenant scope (for DijiTalentFlow)

Frontend route/UI hiding is never treated as authorization — every
tenant/role check enforced by the frontend is re-enforced server-side.

## Local / demo target: Dev Identity Mode

No Entra ID tenant is available during this build phase (CLAUDE.md §58), so
`DEV_IDENTITY_MODE=true` (the default) switches authentication to a fixed
set of personas seeded into the database (`scripts/seed.py`). Dev Identity
Mode is only the *identity acquisition* step — everything downstream
(platform role → module assignment → module role → permissions → client
scope) runs through the same `AuthorizationService` Entra ID will use in
production (Phase 2 CR §43). Deactivated personas (`is_active=false`) are
rejected at login with 403, matching production behavior.

| Persona key       | Name                     | Platform role   | DijiTalentFlow role |
|--------------------|--------------------------|-----------------|----------------------|
| `madushanka-ta`    | Madushanka Weeriyasinghe | PLATFORM_USER   | TA_MEMBER (all clients) |
| `customer-success` | Tharindu Fernando        | PLATFORM_USER   | CUSTOMER_SUCCESS (all clients) |
| `ta-manager`       | Sanduni Wickrama         | PLATFORM_USER   | TA_MANAGER (all clients) |
| `platform-admin`   | Dilani Rathnayake        | PLATFORM_ADMIN  | TA_MANAGER (all clients) |
| `super-admin`      | Priyantha Bandara        | SUPER_ADMIN     | — (platform admin only) |
| `abc-client`       | Amal Perera              | PLATFORM_USER   | TALENT_CLIENT (ABC Company) |
| `xyz-client`       | Nadeesha Silva           | PLATFORM_USER   | TALENT_CLIENT (XYZ Company) |
| `nova-client`      | Kasun Jayasuriya         | PLATFORM_USER   | TALENT_CLIENT (Nova Solutions) |
| `ta-portfolio`     | Ruwan Gunasekara          | PLATFORM_USER   | TA_MEMBER (ABC + XYZ only — demonstrates client/portfolio scope) |

Flow:

1. `GET /api/auth/dev-personas` — public, lists the personas above (used by
   the persona switcher screen at `/`).
2. `POST /api/auth/dev-login {persona_key}` — rejects deactivated accounts
   (403), stamps `User.last_login_at`, and issues a short-lived HS256 JWT
   (`app/core/security.py: DevAuthProvider`) encoding the user id.
3. Frontend stores the token in `localStorage` and sends it as
   `Authorization: Bearer <token>` on every request.
4. `GET /api/auth/me` returns the current user, their `module_roles`, and
   their resolved `platform_permissions` — the frontend never infers
   authorization from the `platform_role` string itself (see
   `docs/platform/authorization.md`).

## Microsoft Entra ID integration seam (not yet activated)

`app/api/routes/auth_entra.py` exposes the concrete OIDC Authorization Code
+ PKCE integration points the CR requires (Phase 2 §8), each failing fast
with a typed 501 until `ENTRA_TENANT_ID` / `ENTRA_CLIENT_ID` /
`ENTRA_CLIENT_SECRET` / `ENTRA_REDIRECT_URI` are configured:

- `GET /api/auth/entra/login-url` — builds the Microsoft identity platform
  v2.0 `/authorize` URL for the Next.js login page to redirect to.
- `POST /api/auth/entra/token` — where the authorization-code exchange,
  `EntraAuthProvider` JWKS validation, and DijiOne `User` resolution (by
  `entra_object_id`, falling back to email on first login) will happen.

Required Entra app-registration steps once credentials are available:
register a single-tenant (or multi-tenant, per Dijital Team's decision) app
registration, add a Web platform redirect URI matching
`ENTRA_REDIRECT_URI`, expose `openid profile email` delegated permissions,
and record the tenant/client id + client secret into `.env` (never commit
them). No other application code changes — `get_auth_provider()` remains
the single seam (CLAUDE.md §12).

## The auth seam (`app/core/security.py`)

```python
class AuthProvider(ABC):
    def issue_token(self, user_id: int, **claims) -> str: ...
    def decode_token(self, token: str) -> dict: ...

class DevAuthProvider(AuthProvider): ...   # active when DEV_IDENTITY_MODE=true
class EntraAuthProvider(AuthProvider): ... # production seam, not yet implemented
```

`get_auth_provider()` returns whichever implementation is active based on
`Settings.dev_identity_mode`. Route and service code depend only on
`AuthProvider` — swapping in real Entra ID token validation later touches
exactly this one file, never business logic.

## Role model

```text
Platform roles:        PLATFORM_USER, PLATFORM_ADMIN, SUPER_ADMIN
DijiTalentFlow roles:   TALENT_CLIENT, TA_MEMBER, CUSTOMER_SUCCESS, TA_MANAGER
```

Roles are now permission bundles resolved by a centralized authorization
engine rather than a fixed set of `if role == ...` checks — see
**`docs/platform/authorization.md`** for the full Phase 2 model (Role /
Permission / RolePermission / UserModuleClientScope, portfolio scope, and
the DijiOne Admin Center that manages all of it).

A `UserModuleRole` row still links a user to a `module_key` + `role`, and —
for `TALENT_CLIENT` — a `client_id` for fast single-tenant lookups. Staff
roles additionally resolve a *portfolio* (`TalentScope.client_ids`): either
a specific list of authorized clients or `None` for unrestricted
(ALL_CLIENTS) access, backed by `user_module_client_scopes`.

`app/api/deps.py: TalentScope` resolves this once per request:

```python
scope.client_id    # None for staff, a specific client id for TALENT_CLIENT
scope.client_ids    # staff portfolio restriction; None = ALL_CLIENTS
scope.permissions   # resolved module-role permission set
scope.is_staff       # "talent.workspace.staff" in scope.permissions
scope.has(key)        # generic permission check
```

Every tenant-scoped repository method takes an additional
`allowed_client_ids: list[int] | None` parameter, applied as an `.in_()`
filter only when the caller's portfolio is restricted — see
`docs/talent-flow/data-model.md` for the tenant isolation guarantee this
produces.
