# Current status and outstanding-issues register (2026-11-13)

Everything in PROJECT-OVERVIEW.md marked **Live** is implemented, tested and deployed to DEV/UAT/PROD with
identical images (onsite-api `4e71488b…`, onsite-web `c156ba8c…`, people-api `21b77405…`).

## Issues register

| # | Issue | Component | Severity | Status | Evidence / root cause | Next action | Blocks |
|---|---|---|---|---|---|---|---|
| 1 | **Identity matching is string equality, not verified identity** — some displayed names/photos may belong to the wrong person | Diji On-site | **High** | Open | 104 of 399 codes "match" inactive employees, 15 before hire; ZKBioTime has 1 name / 0 emails in 373 personnel rows (IDENTITY-MATCHING.md) | Recover real identities (ZKBioTime UI, device user list, enrolment records, HR); then build admin-verified mapping + audit; decide interim display of unverified names | Correctness of names; not deploys |
| 2 | ZKBioTime personnel directory incomplete (`is_active=f` everywhere, single department) | ZKBioTime (source) | High | Open (fact) | export 2026-11-07, re-verified | Do not use ZKBio status/department; rely on BambooHR via verified mapping | #1 |
| 3 | Colombo site **disabled in UAT**; PROD state unverified | Diji On-site | Medium | Open | UAT mirror `site_settings` 2026-11-13; PROD in-container read not permitted | On-site Admin enables via Admin → Sites (audited) in UAT/PROD; confirm PROD in UI | Users see "No enabled sites" |
| 4 | Obsolete `dev-site` mirror rows in DEV (42,871) | Diji On-site DEV | Low | Site disabled ✔; rows retained | DEV mirror | Optional cleanup via a reviewed migration; never in UAT/PROD (not present) | No |
| 5 | Production PC clock ~1 minute slow (shows as "62–66 s delivery delay") | production PC / Agent | Medium | **Root cause likely identified**, unconfirmed | 2026-11-13: Agent `LastDeliveryUtc` 66 s before Azure `ReceivedUtc` | Operator: `w32tm /query /status`, resync time; re-measure punch→dashboard (target 1–2 min) | Latency acceptance |
| 6 | End-to-end live latency never measured with a controlled punch | All | Medium | Open | only historical stage timings | Controlled punch during office hours + watch timestamps | Near-real-time sign-off |
| 7 | `onsite-release.bicep` defaults (`none`, no sync job) + no param files | Diji On-site IaC | Medium | Open (risk) | file defaults on release branch | Add `onsite-release.uat/prod.bicepparam` with live values; what-if | Safe future IaC runs |
| 8 | Sync cron drift (6-hour vs 1-minute) | IaC | — | **Fixed** | both templates `* * * * *`; live `* * * * *` | — | — |
| 9 | Firewall rule `ClientIPAddress_2026-11-03_23-10-04` on the production SQL server (Windows dev PC) | Attendance infra | Low/Med | Open | `az sql server firewall-rule list` | User decides to remove or keep; add Mac IP only with approval | No |
| 10 | Ingestion App Insights heavily sampled (batch requests rarely visible) | Attendance infra | Low | Open | 60 heartbeats/day recorded vs 1,440 | Consider sampling settings for batch endpoint | Diagnostics |
| 11 | Agent integration tests run against `127.0.0.1:7496` — same as production ZKBio | Agent repo | Medium (safety) | Open (documented) | `PipelineFixture.cs` | Add a guard (refuse when not the dev replica) | No |
| 12 | Node pin 20 (`.nvmrc`) vs Windows dev on 22 | DijiOne | Low | Open | `node -v` | Use 20 on Mac; confirm CI version | No |
| 13 | Employees list ~0.75 s at 10k directory entries (flags computed per request) | onsite-api | Low | Open | local scale test | Optimize only if directory grows | No |
| 14 | Activity paging uses offset (not keyset) | onsite-api | Low | Accepted | 0.35 s at page 500 / 61k events | Revisit at 10× volume | No |
| 15 | Inactive employees have no photo (BambooHR directory lists active only) | people-api | Info | By design | 347/360 active have photos | — | — |
| 16 | Attendance policies (late/expected/absent) | Diji On-site | — | Planned | requires HR-approved rules | Needs owner | — |
| 17 | Per-user site scoping | Diji On-site | — | Planned | single site today | When a 2nd site exists | — |

Previously reported items now **fixed**: pagination default 10 + sizes; lazy profile/photos; chart drill-down;
responsive layout; profile photos; date defaults use site-local `today` (Asia/Colombo) from the API; dashboard
refresh 30 s without resetting state; mirror sync every minute with single-flight/advisory lock.

## Recommended next tasks (priority order — wait for approval)
1. Identity: plan + run the identity-recovery investigation (#1/#2) with the user/operator; then design the
   verified-mapping model (table, admin UI, audit, display rules for unverified matches).
2. Enable the Colombo site in UAT and confirm PROD (#3) — user/On-site Admin action.
3. Production PC time sync check + controlled end-to-end latency test (#5/#6) — operator.
4. Add `onsite-release` parameter files (#7) — small IaC PR, what-if only.
5. Firewall rule review (#9); Agent integration-test guard (#11).
