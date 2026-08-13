# DijiOne Platform Requirements

Source of truth: `CLAUDE.md` (repository root). This file summarizes the
platform-level (non-DijiTalentFlow) requirements and their implementation
status. See `docs/talent-flow/requirements.md` for the module-level list.

## Platform shell

| Requirement | Status |
|---|---|
| Single entry URL, single sign-in experience | Done (Dev Identity Mode; Entra ID seam documented, not implemented) |
| Global application shell + centralized navigation | Done — `AppShell`/`Sidebar`/`TopNav` |
| DijiOne Home with greeting, My Apps, Recent Activity, Ask DijiOne | Done |
| Module registry (`ApplicationModule`) | Done — `GET /api/modules`, role-filtered |
| Platform + module role model | Done — `PlatformRole`, `TalentFlowRole`, `UserModuleRole` |
| Multi-tenancy enforced server-side | Done — see `docs/talent-flow/data-model.md` tenant isolation section |
| Notifications | Done — `Notification` model, panel in `TopNav` |
| Audit logging | Done — `AuditLog`, written by every workflow-mutating service method |
| Shared UI design system | Done — `components/ui/*`, tokens in `globals.css` |
| Integration framework (provider abstraction) | Done — Lever/HubSpot mock clients + factory seam |
| Copilot readiness | Documented only (`docs/platform/copilot.md`), not implemented |
| Platform administration | Partial — `PLATFORM_ADMIN` role exists; no dedicated admin UI in this MVP (scope discipline, CLAUDE.md §8) |

## Explicitly out of scope for this delivery (by design)

- Real Microsoft Entra ID SSO (seam exists; no tenant/credentials supplied)
- Live Lever/HubSpot API calls (mock providers only; read-only live
  discovery is a Phase D/E activity per CLAUDE.md §59)
- Azure Blob Storage / SharePoint document storage (Document model stores
  metadata + a `storage_reference`; real upload is a later increment)
- Full Copilot/Cowork integration
- PostgreSQL in this local environment (SQLite for MVP; schema is written
  to be PostgreSQL-compatible via SQLAlchemy 2 + Alembic)

## Non-functional requirements

- Tenant isolation is enforced exclusively in the repository layer and is
  covered by automated tests (`apps/talent-api/tests/test_tenant_isolation.py`).
- Every workflow transition (request review, stage change, application
  status/score/visibility change, interview scheduling) writes an
  `AuditLog` entry and, where relevant, a `Notification`.
- Webhook ingestion (`/api/webhooks/lever`, `/api/webhooks/hubspot`) is
  idempotent by `(provider, external_event_id)` — verified by
  `test_webhook_idempotency.py`.
