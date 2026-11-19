# Diji On-site — Requirements

**Status:** Phase 1 (foundations) in progress. Architecture approved
2026-10-22 — see `docs/onsite/architecture.md`.

## Purpose

Diji On-site turns raw attendance punches captured at Dijital Team sites
into operational information inside DijiOne: who has activity today, first
and latest activity, attendance history, items that need review, and the
health/freshness of each site's attendance feed. Employee identity comes
from BambooHR through the People / Workforce source domain.

## Source boundary

- Attendance events are ingested by the separate Diji On-site ingestion
  plane (on-site Agent → ingestion API v1 → Azure SQL `onsite.*`). That
  plane, its v1 contract and the on-premise collection software are **out
  of scope** and are never modified from DijiOne.
- DijiOne's boundary starts at the Azure SQL `onsite` schema
  (`onsite.Sites`, `onsite.AttendanceEvents`, `onsite.AgentStatus`), which
  DijiOne reads **SELECT-only**.
- Raw attendance records are never rewritten. Every dashboard value is a
  downstream derivation that stays traceable to the raw events
  (`EventId`, `SourceEpoch`, `SourceTransactionId`, `RecordHash`).

## Users (V1)

Internal DijiOne staff holding an On-site role:

| Role | Access |
|---|---|
| `ONSITE_VIEWER` — displayed as **On-site User** (v0.9) | Dashboard, Today, Activity (daily summary and events), Team Members, Exceptions, reports, and **read-only** attendance review cases |
| `ONSITE_ADMIN` — **On-site Admin** | Everything above, plus attendance review decisions (`onsite.exceptions.manage`: open / justify / resolve / reopen), site health, Identity Management (`onsite.identity.read` / `onsite.identity.manage`), "Sync now", site enablement, and granting / changing / revoking **On-site User** access (implied delegated access — see below) |

**Delegation (owner decision 2026-11-19).** Every On-site Admin (direct or group grant, eligible
employee, not suspended) is an implied access administrator of Diji On-site who may grant, change and
revoke **On-site User** only, from Admin → Access. They cannot grant On-site Admin, change another
administrator, a platform administrator or themselves, or appoint administrators; Platform / Super
Admins assign On-site Admin. The authority is computed on every request (demotion takes effect at
once), is audited on the APPLICATION channel, and requires `DELEGATED_ACCESS_ENABLED` (true in DEV,
false in UAT/PROD until enabled). An explicit appointment row always takes precedence.

**Add Person from Microsoft Entra ID (v0.9 closure).** Admin → Access → Add person searches the
organisation directory by name, email address or user principal name. Platform Core runs the search
with its own managed identity (Microsoft Graph v1.0 `GET /users` with `$search`, `ConsistencyLevel:
eventual`, application permission `User.Read.All`). Enabled internal member accounts only; the browser
never calls Graph or sees a token. Each result shows the photo or initials, email / UPN, and one of:
*Has On-site User*, *No access yet*, *New to DijiOne*, or *Not eligible* with the reason.
- The **Entra Object ID is the identity key.** A DijiOne profile found only by a matching email address
  that is not linked to the selected object id is never granted (Central Admin must verify it), so a
  reused address cannot give access to the wrong person.
- A directory entry alone is not eligibility: the person must be matched to a BambooHR employee record.
- A new person is created from the directory and granted in one transaction (idempotent: adding them
  again links the same profile). The confirmation shows the identity and role; the result shows the
  access now held and the audit record.
- Photos: `/api/access/{app}/people/{object_id}/photo` and `/users/{id}/photo` (access
  administrators only, server-side cache, 404 renders initials). Attendance views keep their verified
  BambooHR photos by BHR ID; unmapped and conflict IDs stay anonymous.

**Charts and writing (v0.9 closure).** Data series use the official Dijital Team colours from the style
guide as smooth gradients with no textures: Verified = Orange `#F1592A`, Unmapped = Yellow `#FCB040`,
Mapping conflict = Red `#BF1E2E` (green is not used, so Verified never reads as a "success" outcome).
User-facing text uses the ordinary hyphen; a long dash appears only as the placeholder for an
unavailable value (for example Recorded Span of a single fingerprint).

**Terminology (v0.9).** The office has an entry-side fingerprint reader and an anonymous push-to-exit
button: no employee-specific exit is ever recorded. Screens and reports say *first / last recorded
fingerprint*, *Earliest / Latest Recorded Fingerprint*, *Single Recorded Fingerprint* and *Recorded
Span* — never arrival, departure, exit, presence or hours worked for observed data. See
[attendance-reviews.md](attendance-reviews.md).

Sites are visible only after an `ONSITE_ADMIN` explicitly enables them
(fail closed). No client-facing or employee self-service access in V1.

## Identity rule

*Superseded 2026-11-14 (identity redesign).* The ZKBioTime ID
(`AttendanceEvents.EmpCode`) and the BambooHR employee are separate
identifiers. A punch is attributed to a BambooHR employee (`bamboohr_id`)
**only** through an administrator-verified mapping whose inclusive,
site-local ownership period covers the punch's day. BambooHR Employee
Number equality is never used for attribution (it is shown only as a
labelled, never-applied hint to administrators); no fuzzy or name matching;
no automatic mapping. Unmapped or conflicting punches are kept but excluded
from viewer records and identified KPIs, and are handled in Identity
Management. Full procedures: `docs/onsite/identity-management.md`.

## Time

All day grouping ("today", daily history) uses the site's configured time
zone (`onsite.Sites.TimeZone`), never server UTC. No time zone is hardcoded.

## Business rules

`PunchState` is preserved raw (currently `255` for all historical rows) and
is not interpreted as IN/OUT. Until an attendance policy is approved,
metrics use neutral wording only — *first activity*, *latest activity*,
*punch count*, *activity recorded*, *needs review*. Present / Absent / Late /
Early / worked hours are deferred until an approved, versioned policy exists.

## Freshness

The module must distinguish "no attendance recorded" from "attendance feed
may be stale" (agent heartbeat age, last DijiOne sync, source availability),
and must never present a pipeline outage as employee absence.

## Phases

1. **Foundations** — Workforce Directory in `people-api`, module
   registration, `onsite-api` with the raw mirror and sync lifecycle,
   deployment and module-boundary enforcement, admin-only web skeleton.
2. **Dashboard V1** — Overview, Today, Activity, Employee history,
   Exceptions (neutral metrics). Starts only after Phase 1 exit criteria and
   the module-removal drill pass.
3. **Business rules & trends** — approved, versioned attendance policy;
   Trends view.
4. **PROD readiness** — PROD grants, network hardening, retention policy.
