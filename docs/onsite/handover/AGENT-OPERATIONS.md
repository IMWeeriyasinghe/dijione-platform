# Diji On-site Agent — production PC operations

Code and Windows-specific detail: DijiOnsite-Agent repo (`CLAUDE.md`, `docs/architecture.md`,
`docs/handover/MAC-HANDOVER.md`). Nothing here can be done from a Mac.

## Production installation (from installer/scripts; status from Azure telemetry 2026-11-13)

| Item | Value |
|---|---|
| PC | `DESKTOP-V3H5OFI` (ZKBioTime host) |
| Service | `DijiOnsiteAgent`, display "Diji On-site Agent", Automatic (Delayed Start), account `NT SERVICE\DijiOnsiteAgent`, recovery restart 60 s / 60 s / 300 s |
| Program files | `C:\Program Files\DijiOnsiteAgent` (Inno Setup, stable AppId `{715F1E9C-411B-48BC-9EB0-F25AAC53BF0F}`) |
| Config | `%ProgramData%\DijiOnsiteAgent\config\agent.json` (admin-only ACL; secrets as `dpapi:<base64>`, LocalMachine scope, entropy `DijiOnsiteAgent.v1`) |
| State / outbox | `%ProgramData%\DijiOnsiteAgent\data\agent.db` (SQLite: checkpoint, outbox, gaps) |
| Logs | `%ProgramData%\DijiOnsiteAgent\logs` (Serilog rolling files) + Windows Application event log |
| Admin API / UI | loopback only `127.0.0.1:47800` (`/health`, `/status`), token-protected admin actions |
| Version | 0.1.1 (reported in heartbeat) |
| Source | PostgreSQL `127.0.0.1:7496` db `biotime`, user `diji_onsite_reader` (SELECT-only role, `deploy/sql/create-readonly-role.sql`); tables read: `iclock_transaction` (capture), `personnel_employee`/`personnel_department` (only by the export script) |
| Terminal | SN `CQZ7232560569`, alias `Office` |
| Destination | `https://app-diji-onsite-attendance.azurewebsites.net`, site `dijital-lk-colombo-office`, site key from KV `site-key-dijital-lk-colombo-office` (stored DPAPI-protected on the PC) |

Live (Azure `onsite.AgentStatus`, 2026-11-13 16:07 UTC): Healthy, heartbeat 56 s old, source connected,
HighWaterId 46040, pending 0, dead-letter 0, 14,426 heartbeats.

## Behaviour
- Capture every 10 s (`Source.PollIntervalSeconds`), loops immediately while catching up; batch 500 rows.
- Gap tracking: missing ids re-checked for 300 s before being treated as rolled-back (`GapTracker`).
- Atomic checkpoint + outbox commit; delivery worker sends one batch at a time (≤ 200 events), same batchId on
  retry, exponential backoff 2 s → 300 s, auth failures retry every 300 s; outbox rows kept 30 days after send.
- Heartbeat every 60 s (health, pending, dead-letter, high-water, last error).
- Start position is an explicit admin choice with no default. Production: `after-id:42881` (never changed).

## Rules
- **Never reset/re-baseline the production checkpoint or SourceEpoch.**
- Never write to ZKBioTime, the terminal, or device users; never weaken the read-only role/session settings.
- Never run Agent integration tests on the production PC (they write to `127.0.0.1:7496/biotime`).
- Production work requires someone physically/remotely on the PC with admin rights; reading
  `%ProgramData%\DijiOnsiteAgent` needs elevation.

## Upgrade (Windows only)
`deploy/installer/build-installer.ps1` → `artifacts\installer\DijiOnsiteAgent-Setup-<version>.exe`; run on the
PC; installer preserves `%ProgramData%\DijiOnsiteAgent` (config, queue, logs) and the checkpoint.

## Diagnostics scripts (production-pc, read-only)
- `deploy/production-pc/verify-production-source.ps1` — read-only fingerprint/role proof.
- `deploy/production-pc/export-employee-directory.ps1` — personnel export for identity work (writes CSV under
  `%ProgramData%\DijiOnsiteAgent\exports`, contains personal data; delete after use).

## Open operational item
Clock skew: on 2026-11-13 the Agent's `LastDeliveryUtc` (14:17:36) was 66 s **before** Azure's `ReceivedUtc`
for the same batch (14:18:42), i.e. the PC clock is about a minute slow. Check on the PC:
`w32tm /query /status` and `w32tm /stripchart /computer:time.windows.com /samples:3`. Fixing Windows time sync is an
operator action (no code change). It makes `CapturedAtUtc` and the "delivery delay" metric misleading.
