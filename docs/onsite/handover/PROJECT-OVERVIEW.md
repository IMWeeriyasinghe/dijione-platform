# Project overview and feature inventory

Diji On-site turns fingerprint-terminal activity at Dijital Team offices into an attendance-operations
dashboard inside DijiOne. One production site today: **`dijital-lk-colombo-office`**
("Dijital Team - Colombo Office", `Asia/Colombo`, source epoch `1`).

Vocabulary is deliberately neutral: *activity events, first/latest activity, activity span*. There is
**no** Present/Absent/Late/Worked-hours logic, and raw ZKBioTime `PunchState` (always `255` here) is never
interpreted as check-in/out. No fingerprint templates or biometric data are read, stored or required
anywhere — only transaction rows (code, time, terminal).

## Status legend
**Live** = implemented, tested and deployed to DEV/UAT/PROD with identical images ·
**Partial** · **Blocked** · **Planned**.

## Diji On-site (DijiOne module)

| Area | Feature | Status | Notes |
|---|---|---|---|
| Overview | KPI cards with tooltips, drill-down links, previous-period deltas (complete periods only) | Live | |
| | Period presets Today/Yesterday/7/30/custom (site-local date from API) | Live | |
| | Activity by hour — clickable bars → hour sheet (exact events, paged) → employee profile | Live | hour boundary `[hh:00, hh+1:00)` UTC-converted per date |
| | Daily trend (7/30 d) — clickable days drive every widget; "Selected day" strip | Live | |
| | Needs review (links to Exceptions with flag), Recent activity, freshness strip | Live | |
| Today | Site-local day view per employee (first/latest/count/span/flags), day stepper, filters, sort | Live | |
| Activity | Event list, filters (search, Employee Number, dept, terminal, identity, day flag, **hour**), newest/oldest, expandable details, review flags column | Live | offset paging |
| Employees | Workforce-Directory population + attendance metrics, summary tiles, sortable, filters | Live | |
| | Profile photos (BambooHR `photoUrl` via people-api proxy) with initials fallback | Live | **not** Microsoft Graph — see IDENTITY-MATCHING / FRONTEND-BACKEND |
| | Employee profile drawer (summary, daily chart, per-day events lazily, review flags tab) | Live | |
| Exceptions | Category tiles, flag explanations, sort, links to supporting events | Live | flags = prompts, not violations |
| Admin | Site Health (feed, mirror, Agent, reconciliation, sync history, Sync now) | Live | admin roles only |
| | Identity Match (server-paged report + CSV) | Live | exact-string matching only — see IDENTITY-MATCHING |
| | Sites (enable/disable, audited) | Live | Colombo **enabled in DEV, disabled in UAT**, PROD unverified |
| Platform | Pagination default 10, sizes 10/20/50/100, remembered per view | Live | |
| | Responsive layouts, mobile bottom nav, cards on phones | Live | 9 pages × 7 widths checked in a browser |
| | 30-s refetch, URL-backed filters, no reset during refresh | Live | |
| | Excel exports (filter-aware, formula-injection safe) | Live | |
| | Near-real-time mirror (1-minute `onsite-sync-job`) | Live | |
| Identity | Administrator-verified ZKBioTime ↔ BambooHR mapping with audit trail | **Planned / Blocked** | needs identity source; see IDENTITY-MATCHING |
| Policy | Attendance policies (late/expected/absent) | Planned | needs HR-approved rules |

## Diji On-site Agent (production PC)

| Feature | Status |
|---|---|
| Windows service `DijiOnsiteAgent` 0.1.1, poll every 10 s, gap-aware capture, SQLite outbox, retries, heartbeat 60 s | Live (Healthy on 2026-11-13) |
| WPF setup wizard / settings UI, admin API on loopback `:47800` | Live |
| Inno Setup installer | Live |
| `verify-production-source.ps1` (read-only fingerprint/role proof) | Live, committed |
| `export-employee-directory.ps1` (read-only personnel export for identity work) | Used 2026-11-07; **committed in this handover** |

## Diji On-site Attendance (Azure)

| Feature | Status |
|---|---|
| Ingestion API v1 (batches, heartbeats, per-site key auth, idempotent EventId) | Live |
| Azure SQL `onsite.*` schema, 5 indexes incl. `IX_AttendanceEvents_Received` | Live |
| Alerts: backlog, errors, heartbeat, health, http5xx, failure anomalies | Present (thresholds not reviewed in this handover) |
| Per-environment SELECT-only DijiOne principals (dev/uat/prod) | Live |

Live numbers on 2026-11-13 16:07 UTC: 46,019 events, max source transaction id 46040, 0 duplicates,
Agent heartbeat 56 s old, 0 pending. See DATA-MODEL-AND-SYNC.md for how to re-check.
