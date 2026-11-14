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
| `ONSITE_VIEWER` | Dashboard, today's activity, history, items needing review |
| `ONSITE_ADMIN` | Everything above, plus site health, Identity Management (`onsite.identity.read` / `onsite.identity.manage`), "Sync now", site enablement |

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
