# Handover validation checklist (all read-only)

Tick each item on the Mac and report results to the user. Stop and report on any mismatch.

## A. Repositories
- [ ] DijiOne at `/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform`, `origin` = `IMWeeriyasinghe/dijione-platform`, clean tree.
- [ ] `origin/release/onsite-v1` contains `5d93d42`-equivalent On-site commits (`git log --oneline origin/release/onsite-v1 -- apps/onsite-web | head`) and `7eabdc6` (or newer).
- [ ] `origin/docs/onsite-handover` contains `docs/onsite/handover/` (14 files).
- [ ] DijiOnsite-Agent cloned; `origin/main` = `d18e882` (or newer); `origin/docs/mac-handover` has `docs/handover/MAC-HANDOVER.md` and `deploy/production-pc/export-employee-directory.ps1`.
- [ ] No `*.csv`, `.env`, `agent.json`, `*.db` tracked: `git ls-files | grep -iE '\.(csv|db|pfx|pem|key)$|\.env$|agent\.json'` → empty.

## B. Toolchain
- [ ] `node -v` (20.x), `npm -v`, `python3.12 --version`, `.venv/bin/python -V`, `dotnet --version` (10.x), `az version`.

## C. Tests (expected 2026-11-13)
- [ ] onsite-api pytest 129 passed; ruff clean.
- [ ] people-api 35; auth-client-py 19.
- [ ] onsite-web vitest 68; `tsc --noEmit`, `eslint src`, `next build` clean.
- [ ] `node scripts/check-module-independence.js` OK.
- [ ] Agent: `dotnet test tests/DijiOnsiteAgent.Core.Tests` (66) and `tests/DijiOnsiteAttendance.Ingestion.Tests` (10) — record if any are Windows-only.

## D. Live state (read-only `az`, no changes)
```bash
for env in dev uat prod; do
  az containerapp job show -g rg-dijione-$env -n onsite-sync-job --query "[properties.configuration.scheduleTriggerConfig.cronExpression, properties.configuration.replicaTimeout, properties.template.containers[0].image]" -o tsv
  az containerapp show -g rg-dijione-$env -n onsite-api --query "properties.template.containers[0].image" -o tsv
  az containerapp job execution list -g rg-dijione-$env -n onsite-sync-job --query "[0:5].properties.status" -o tsv
done
curl -s -o /dev/null -w "%{http_code}\n" https://app-diji-onsite-attendance.azurewebsites.net/healthz
```
- [ ] cron `* * * * *`, timeout 120, digests as in INFRASTRUCTURE-ENVIRONMENTS.md (or newer, with explanation).
- [ ] recent executions Succeeded; ingestion `/healthz` 200.
- [ ] (Only if the user grants SQL access) authoritative counts/AgentStatus via DATA-MODEL-AND-SYNC.md queries.

Mirror contents in DEV/UAT can be read with a read-only Python script executed inside onsite-api via
`az containerapp exec` (chunked upload; rate-limited — wait 10 min after HTTP 429). **Never in PROD.**
Prefer the Site Health page when signed in.

## E. Documentation accuracy
- [ ] Spot-check routes in FRONTEND-BACKEND.md against `apps/onsite-api/app/api/routes/*.py`.
- [ ] Spot-check sync constants against `mirror_sync_service.py` / `core/config.py` (overlap 10 min, page 5000, stale 10 min, reconcile 15 min, delayed 5 min).
- [ ] Confirm photo path (people-api `workforce_photo.py`, onsite-api `employee_photos.py`); no Graph code: `git grep -n "graph.microsoft.com" apps/onsite-* apps/people-api` → empty.

## Not verifiable from Windows (Mac agent / user actions)
- PROD mirror contents and PROD site enablement (needs signed-in UI).
- Production PC state beyond Azure telemetry (service status, logs, clock).
- Open GitHub PRs (`gh pr list` on the Mac once `gh` is authenticated).
- macOS behaviour of pyodbc install and the Agent Core tests.
