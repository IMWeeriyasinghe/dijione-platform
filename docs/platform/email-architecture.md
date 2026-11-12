# DijiOne email architecture — shared code, never shared runtime ownership

> Authoritative. Established for DijiBirthday's outbound supplier email
> (real Microsoft Graph, Managed Identity, no client secrets), designed from
> the start as the pattern every future DijiOne service adopts independently.

## The core principle

**DijiOne is a monorepo, not a monolith.** A monorepo means one Git repository
containing multiple independently deployable applications and services — it
does not mean one runtime, one identity, one release lifecycle, or one
database. Email support follows that same discipline:

```
birthday-api
    ↓
packages/mail-client-py (shared CODE, no runtime, no state)
    ↓
birthday-api's own system-assigned Managed Identity
    ↓
birthday-api's own Exchange RBAC-for-Applications scope
    ↓
Microsoft Graph

talent-api (future)
    ↓
same packages/mail-client-py code
    ↓
talent-api's own Managed Identity
    ↓
talent-api's own Exchange scope
    ↓
Microsoft Graph
```

**Share code. Never share runtime ownership.** No app's email flows through
another app's process; no app's identity is used to send another app's mail;
no app is forced to redeploy because a different app's email config changed.

## Why not a central `mail-api` service

A `birthday-api → central-mail-api → Graph` design was considered and
rejected:

1. **New runtime dependency for every consumer** — a network hop, a new
   failure mode, a new service to build/deploy/scale/monitor, where today
   there is none.
2. **Re-introduces identity sharing** — a central service would need either
   one broad identity covering every app's mailbox (exactly the anti-pattern
   this design avoids) or per-caller mailbox-routing logic that just
   relocates the per-service Exchange-scoping problem at extra cost.
3. **Coordinated-deployment risk** — a bug in the central service breaks
   email for every consuming app simultaneously.
4. **Contradicts the platform's release-target-aware versioning policy** — a
   shared runtime change would force every consumer to re-verify/redeploy
   against it, the exact "repository change ≠ application release"
   conflation that policy exists to prevent.
5. **No current requirement justifies the cost** — one Birthday mailbox, low
   volume, a genuine need for *independent* Exchange scoping per app.
   Reconsider only if a concrete future need emerges at real scale — never
   pre-emptively.

## `packages/mail-client-py` — what it is and isn't

Follows this repo's existing `packages/auth-client-py` convention exactly
(plain pip editable install — `-e ../../packages/mail-client-py` in each
consuming service's `requirements.txt` — no separate version, always builds
against whatever's on disk):

- `MailTransport` protocol, `NullMailTransport` (safe local/CI default),
  `GraphMailTransport` (real Microsoft Graph, Managed Identity only).
- `MailResult` / `MailOutcome` — the truthful transport-level contract (below).
- `MailPolicy` protocol + `DisabledPolicy` / `InternalAllowlistPolicy` /
  `ProductionPolicy` — generic recipient-policy mechanics.
- `MailClient` — the orchestration facade: checks policy **before** ever
  invoking the transport (structural "block before Graph," not caller
  discipline), generates a correlation id, sanitizes the sender.

It contains **no** running service, no database, no application-specific
templates, no idempotency logic, no audit logic, and reads no environment
variables itself. Every consuming service builds its own `MailClient` from
its own config, at module load time — its own "one change point," mirroring
`packages/auth-client-py`'s `make_verify_internal_request` factory pattern
(CLAUDE.md rule 21).

## Transport vs. policy

Two different questions, answered by two different, composable pieces:

- **Transport — "how do we send?"** `null` (nothing leaves the system) or
  `graph` (real Microsoft Graph, via `sendMail`).
- **Policy — "are we allowed to send to this recipient?"** `disabled`
  (reject everything — safe default), `internal_allowlist` (reject unless
  the recipient matches an explicit configured address/domain — the DEV-safe
  mode), or `production` (accept everything).

Policy only carries real safety weight once a real transport is in play —
`NullMailTransport` can never submit a real email regardless of policy, so a
consuming service is free to pair it with a permissive policy locally
without weakening anything (birthday-api does exactly this — see
`app/integrations/factory.py`). The moment a service turns on `graph`, its
own `mail_policy` setting (defaulting to `disabled`, fail-closed) governs —
an operator who forgets to also set it gets `DISABLED`, never an accidental
open send.

## Delivery-status model — the truthful contract

`MailOutcome`: `NOT_ATTEMPTED | DISABLED | BLOCKED | SIMULATED | SUBMITTED |
FAILED`.

- `SIMULATED` — `NullMailTransport` executed the flow; no real email left
  the system.
- `SUBMITTED` — Microsoft Graph accepted the real `sendMail` call (202
  Accepted). **This means submitted, not delivered.** Graph's 202 is not a
  delivery confirmation, and this library never claims otherwise.
- `BLOCKED` / `DISABLED` — policy rejected the recipient / the transport
  outright; the real transport is never invoked.
- `FAILED` — a real transport attempt was made and failed.

`MailResult.sent: bool` is **fully truthful** — `True` only when `outcome ==
SUBMITTED`, `False` for every other outcome including `SIMULATED`. A future
consumer can trust `sent == True` to mean a real transport genuinely
submitted an email; the shared library never teaches "simulated means sent."

**A consuming service's own "is this good enough to progress my workflow"
judgment is a separate, locally-owned concept.** Birthday, for example,
treats both `SIMULATED` and `SUBMITTED` as sufficient to progress an order
(`order_email_service._business_accepted`), because that's how its
mock-mode testing has always worked — but that adapter lives entirely inside
`birthday-api`, never in the shared library. Birthday records this split
durably as two separate fields: `SupplierCommunication.status` (its own
business/workflow state) and `SupplierCommunication.transport_outcome` (the
raw, truthful `MailOutcome`) — never overloading one with the other's
meaning.

## Two independent safety layers: SEND-AS vs. SEND-TO

Exchange RBAC (above) and the DB-backed Email Safety allowlist (below)
answer two different questions and neither replaces the other:

| Layer | Question | Controls | Owner |
|---|---|---|---|
| Exchange RBAC for Applications | Which mailbox may this identity send **as**? | `appassistant@dijitalteam.com` only, via `DijiApps-AppAssistant-Mailbox-Scope` | Exchange/Entra admin, tenant-wide |
| Email Safety (`BirthdayTestEmailRecipient`) | In DEV/UAT, who may this service send **to**? | An explicit, DB-backed, admin-managed list of approved test addresses | DijiBirthday application, per environment |

Exchange RBAC is identical across DEV/UAT/PROD (same sender mailbox, same
scope). Email Safety exists **only** in DEV/UAT — PROD never consults it,
never depends on it, and never restricts a real supplier address because of
it. Losing sight of this distinction is the most common mistake: a
`Test-ServicePrincipalAuthorization` check passing tells you the identity
*can send as* the mailbox — it says nothing about which recipients are safe
to send *to* in a non-production environment. That second question is
Email Safety's job, and it is deliberately DijiBirthday-owned, not a
DijiOne platform-admin or Customer Portal V2 concern — see
`docs/birthday/email-safety.md` for the full design, API surface, and
non-production-only enforcement mechanism.

The now-removed `MAIL_ALLOWLIST` environment variable was an early,
env-var-based sketch of the second layer; it has been fully replaced by the
DB-backed `BirthdayTestEmailRecipient` table precisely because an env var
requires a redeploy to change, while the actual requirement is "change the
approved list at runtime, with no redeploy." See
`docs/birthday/email-safety.md` for why and how.

## Managed Identity + Exchange RBAC for Applications

Every DijiOne Container App already gets a system-assigned Managed Identity
(declared in `deploy/bicep/modules/containerapp.bicep`, unconditional,
explicitly reserved in a code comment for "future per-service grants") —
`GraphMailTransport` authenticates via `azure.identity.DefaultAzureCredential`,
which resolves to that ambient identity inside a deployed Container App.
**No client secret, no SMTP, no mailbox password, ever.**

Permission is granted entirely through **Exchange Online RBAC for
Applications** — the model proven in the reference "Customer Portal V2"
implementation — never the legacy Application Access Policy mechanism, and
never a separate, unscoped Microsoft Graph `Mail.Send` application-role
assignment (that would create a second, independent authorization path that
could undermine the mailbox-specific scope RBAC for Applications provides).

Runbook (an Entra + Exchange admin action — outside any automated session's
authority, must be run by a human with the right role):

1. Inspect the identity's existing Entra app-role assignments first — if a
   tenant-wide Graph `Mail.Send` grant already exists for any reason, stop
   and report it rather than layering Exchange RBAC on top.
2. `New-ServicePrincipal -AppId <MI-AppId> -ObjectId <MI-ObjectId>
   -DisplayName "<Service>-<Env>-API-MI"` — registers the identity in
   Exchange.
3. `New-ManagementScope -Name "<Service>-MailSender-Scope"
   -RecipientRestrictionFilter "PrimarySmtpAddress -eq '<mailbox>'"` — defines
   the mailbox scope.
4. `New-ManagementRoleAssignment -Name "<Service>-<Env>-MailSend" -Role
   "Application Mail.Send" -App "<Service>-<Env>-API-MI" -CustomResourceScope
   "<Service>-MailSender-Scope"` — grants exactly one Exchange-scoped role.
   Never `Application Mail.ReadWrite` for outbound-only sending.
5. Verify both directions: `Test-ServicePrincipalAuthorization -Identity
   "<Service>-<Env>-API-MI" -Resource <mailbox>` → `InScope True`; against
   an unrelated mailbox → `InScope False`.
6. Allow a short propagation window before the first real send — Exchange
   RBAC changes may be cached; `Test-ServicePrincipalAuthorization` reads the
   authoritative scope directly and can confirm the grant before real Graph
   traffic observes it, so an initial post-grant `403` is expected to be
   transient, not necessarily a code defect.

DijiBirthday DEV specifically: identity `DijiBirthday-Dev-API-MI`, scope
`DijiBirthday-MailSender-Scope` restricted to `appassistant@dijitalteam.com`
only, role assignment `DijiBirthday-Dev-MailSend`.

## Mailbox strategy

Reuse **`appassistant@dijitalteam.com`** (display name "Diji Apps Notify",
Exchange-controlled) for Birthday Phase 1 — no dedicated mailbox needed at
this volume. The sender display name is resolved by Exchange from the
mailbox object at send time; `GraphMailTransport` never attempts to set a
display name in the Graph payload, and there is no `from`/`sender` parameter
on `MailClient.send()` to override it with. If a future app needs a visually
distinct sender identity, provision a dedicated mailbox for it — never fake
a per-app display name against a shared one.

## Future app adoption checklist

1. `-e ../../packages/mail-client-py` in the service's own `requirements.txt`.
2. Its own `MAIL_TRANSPORT` / `MAIL_POLICY` / `MAIL_SHARED_MAILBOX` settings
   in its own config — independently, same shared mailbox or its own
   dedicated one. If it adopts `mail_policy=internal_allowlist` for
   DEV/UAT, it needs its own local, DB-backed recipient-allowlist feature —
   DijiBirthday's `BirthdayTestEmailRecipient` (`docs/birthday/email-safety.md`)
   is a reference implementation, not a shared table another service reads.
3. Its own factory function (mirroring `birthday-api`'s
   `get_email_client()`), binding config once at module load time.
4. The Exchange RBAC runbook above, against its **own** already-existing
   system-assigned identity and its **own** mailbox scope — never shared
   with another app's grant.
5. `deploy/Dockerfile.api` already copies `packages/mail-client-py`
   unconditionally for every service; add the service's own import to the
   build-time hard-fail check only if it declares the dependency.
6. Ships on its own release schedule (`versions:check --apps <that-service>`)
   — no other app's version, image, or release date changes.

## Where this is enforced / referenced

- `packages/mail-client-py/` — the shared library itself.
- `apps/birthday-api/app/integrations/factory.py` — `get_email_client()`,
  Birthday's own factory/config-binding.
- `apps/birthday-api/app/services/order_email_service.py` —
  `_business_accepted`, Birthday's business-acceptance adapter.
- `apps/birthday-api/app/models/supplier_communication.py` —
  `transport_outcome` column.
- `deploy/Dockerfile.api` — the shared-package Docker wiring.
- `CLAUDE.md` — the standing platform-wide rule (near rule 21).
