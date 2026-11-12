# DijiBirthday Supplier Portal — authentication

Hosted Azure DEV uses **real Microsoft Entra ID B2B guest** sign-in for the
Birthday Supplier Portal. Local development keeps the seeded-persona picker.
Status: **ACTIVE in DEV** (2026-09-09). This is a post-completion DEV
improvement — it does not change the meaning of the DEV current-scope
completion checkpoint.

Not affected by this work: DijiTalentFlow external client access (still the
approved magic-link model), internal DijiOne staff Entra authentication,
`EMAIL_SENDING_MODE` (stays `mock`).

---

## 1. Trust model

Two independent layers. **Entra authenticates; DijiBirthday authorizes.**

```
Microsoft Entra ID authentication  (B2B guest, Dijital Team tenant)
        ↓  verified id_token (RS256/JWKS, iss, aud, tid, exp, nonce, PKCE)
verified external identity  (oid + verified email)
        ↓
Birthday SupplierUser lookup   (oid -> row, else verified email -> row)
        ↓
ACTIVE SupplierUser?           (status re-checked here AND on every request)
        ↓  yes
supplier + supplier scope established (supplier_id from the row, never the request)
        ↓
DijiOne-format supplier session token issued  (8h, module_roles + supplier claim)
        ↓
Birthday Supplier Portal access  (all routes derive supplier_id server-side)
```

**Fail closed.** A valid Microsoft account / B2B guest with **no matching
ACTIVE `SupplierUser`** gets a generic `403` and no portal access. A
`SupplierUser` set `INACTIVE` loses access on the next request, not when the
token expires. `SupplierUser` is **never auto-created** from a sign-in.

`SupplierUser` remains the application-level source of truth for supplier
authorization. Entra membership alone grants nothing.

## 2. The `SUPPLIER_AUTH_MODE` switch (`birthday-api`)

| Value | Sign-in UI | `/api/birthday/internal/dev/supplier-*` | Notes |
|---|---|---|---|
| `dev` (default, local) | seeded-`SupplierUser` persona picker | **available** | No Entra config needed. |
| `entra` (hosted DEV) | "Sign in with Microsoft" | **404** | Requires `SUPPLIER_ENTRA_*` + the `birthday-supplier-entra-secret-<env>` Key Vault secret. |

`SUPPLIER_AUTH_MODE` is the **authoritative** control — the persona routes
are no longer gated on `APP_ENV`. Rollback is one param: set
`supplierAuthMode = 'dev'` in `main.dev.bicepparam` and redeploy.

## 3. Entra configuration (hosted DEV)

**App registration** `dijione-birthday-supplier-dev` — separate from the
internal `dijione-dev` registration, for a clear trust boundary.

| Property | Value |
|---|---|
| Application (client) id | `30e36193-f0e4-40d5-875b-db1ef6a3f2b0` |
| Object id | `37bcee37-2fcf-4136-8987-dac2c0ad35a9` |
| Service principal id | `f68835b4-b177-4fb9-b136-6ea7ebd84df8` |
| Sign-in audience | `AzureADMyOrg` (single tenant — B2B guests are directory members of the resource tenant) |
| Directory | the existing **Dijital Team tenant** `2abce006-6ea2-4675-b39d-33e0a54c46c7` (no separate External ID / CIAM tenant) |
| Web redirect URI | `https://birthday-supplier-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io/api/auth/callback` |
| Front-channel logout | `https://birthday-supplier-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io/` |
| id_token optional claims | `email`, `preferred_username` |
| Delegated Microsoft Graph scopes | `openid`, `profile`, `email` (no `User.Read` — id_token claims are enough) |
| id/access token implicit issuance | disabled (Authorization Code + PKCE only) |
| Client secret | `kv-dijione-dev/birthday-supplier-entra-secret-dev` (1-year, never in the repo) |

`birthday-api` env in `entra` mode: `SUPPLIER_AUTH_MODE=entra`,
`SUPPLIER_ENTRA_TENANT_ID`, `SUPPLIER_ENTRA_CLIENT_ID`,
`SUPPLIER_ENTRA_REDIRECT_URI` (= `<supplierPublicBaseUrl>/api/auth/callback`),
`SUPPLIER_PUBLIC_BASE_URL`, and `SUPPLIER_ENTRA_CLIENT_SECRET` from Key Vault.
`birthday-supplier-web` env: `BIRTHDAY_API_URL`, `SUPPLIER_PUBLIC_BASE_URL`.

## 4. Code

`birthday-api`:

| File | Role |
|---|---|
| `app/core/config.py` | `supplier_auth_mode` + `supplier_entra_*` settings + `dev_supplier_auth_enabled` / authority / issuer / jwks properties |
| `app/core/supplier_entra.py` | `SupplierEntraVerifier` — self-contained id_token validation (same pattern as `platform-api/app/core/security.py::EntraTokenVerifier`) |
| `app/services/supplier_auth.py` | `resolve_supplier_user` (identity → ACTIVE row, fail-closed; `#EXT#` UPNs never treated as email; stamps `entra_object_id` on first email match) + `mint_supplier_session_token` (shared by both auth modes) |
| `app/api/routes/supplier_auth_entra.py` | `GET /api/birthday/supplier/auth/config`, `GET …/login-url`, `POST …/token` |
| `app/api/routes/dev_auth.py` | persona picker — now gated on `SUPPLIER_AUTH_MODE=dev`, token minting delegated to the shared helper |

`birthday-supplier-web`:

| File | Role |
|---|---|
| `src/app/login/route.ts` | starts Entra sign-in (fetch `login-url`, httpOnly `dijibirthday_supplier_flow` cookie, 302 to Microsoft) |
| `src/app/api/auth/callback/route.ts` | code exchange → `sessionStorage` token (no token in URL) → `/` |
| `src/app/login-screen.tsx` | reads `…/auth/config`; `entra` → "Sign in with Microsoft" (no "development mode" wording); `dev` → persona picker |
| `src/lib/api.ts` | `getSupplierAuthConfig` |
| `next.config.ts` | rewrite `/api/birthday/supplier/auth/:path*` → birthday-api |

## 5. Operational onboarding for a supplier (hosted DEV)

1. **Internal admin** (DijiBirthday → Suppliers) creates the **Supplier**
   record (lead time, working days, cutoff, service location, catalogue).
2. **Internal admin** adds a **SupplierUser** to that supplier — name +
   the email the person will sign in with. `ACTIVE` by default.
3. **Entra admin** invites that email as a **B2B guest** in the Dijital
   Team tenant (Entra ID → Users → *Invite external user*), if it is not
   already a member/guest. A `@dijitalteam.com` work account needs no
   invitation.
4. The supplier opens the portal → **Sign in with Microsoft** → completes
   the Microsoft prompt.
5. On first sign-in, `resolve_supplier_user` matches the verified email to
   the `SupplierUser` row and stamps `entra_object_id`; every later
   sign-in matches on that stable id.
6. The supplier sees only their own supplier-scoped orders.

**No** `SupplierUser` is created by a sign-in — step 2 is always a
deliberate internal action.

## 6. Security boundaries

- `supplier_id` is taken from the `SupplierUser` row, never from a request
  parameter — a manipulated order id belonging to another supplier `404`s.
- `get_supplier_scope` re-loads the `SupplierUser` and re-checks `ACTIVE`
  on every request.
- The supplier session token carries only id, name, email, the
  `birthday.portal.*` permissions and the `supplier` claim — no other PII.
- The Entra client secret lives only in Key Vault, resolved via the shared
  managed identity; it never reaches the browser bundle.
- `birthday-api` holds no BambooHR credential and no cross-service DB
  access; Birthday still consumes People only through `people-api`.
- The supplier portal talks only to `/api/birthday/portal/*` and
  `/api/birthday/supplier/auth/*` — never the internal `/orders` /
  `/suppliers` paths.

## 7. Tests

`birthday-api` `tests/test_supplier_entra_auth.py` (20):

- config reports `dev` / `entra`; `login-url` 501 unconfigured, 200 + PKCE
  configured
- active guest + ACTIVE SupplierUser → working portal token; `entra_object_id`
  stamped on first login; second login matches by `oid`
- valid identity + no SupplierUser → 403 generic
- INACTIVE SupplierUser → 403
- missing email **and** oid → 403; `#EXT#` UPN not treated as an email → 403
- wrong tenant / audience / signature / expiry / nonce → 401
- Entra rejects the code → 401; state mismatch → 400
- supplier A's token cannot read supplier B's order (list count 0, by-id 404)

`tests/test_dev_supplier_auth.py`: persona routes 404 under
`SUPPLIER_AUTH_MODE=entra`, available under `dev` (even with
`APP_ENV=production`).

`birthday-supplier-web` `src/app/__tests__/login-screen.test.tsx` (3):
`entra` → "Sign in with Microsoft" link to `/login`, no dev wording, no
persona fetch; `dev` → persona picker; config-error → persona-picker
fallback.

## 8. Local development

`SUPPLIER_AUTH_MODE` defaults to `dev` — the persona picker keeps working
with no Entra setup. Set `SUPPLIER_AUTH_MODE=entra` locally only if you are
testing the OIDC flow against a real registration.
