# Mac coding agent — start here

You are taking over development of **Diji On-site** (DijiOne module), with read access to the
**Diji On-site Agent** and **Diji On-site Attendance** code. Read this page fully before running anything.

## Hard rules (production safety)

1. **Do not deploy, merge, force-push or rewrite history** without explicit approval from the user.
   Pushing a feature/docs branch is fine; merging into `release/onsite-v1` or `main` is not.
2. **Never write to the authoritative database** `sqldb-diji-onsite-attendance` except via the ingestion
   service. DijiOne identities are SELECT-only. Schema/index changes need a separate, approved justification
   (the precedent is `IX_AttendanceEvents_Received`, added online 2026-11-03).
3. **Never touch the production PC, ZKBioTime, the terminal or the Agent checkpoint.** The production
   checkpoint/SourceEpoch must never be reset or re-baselined. No production Agent work can be done from a Mac.
4. **Never run `DijiOnsiteAgent.IntegrationTests` on the production PC** — they insert/delete rows in
   `127.0.0.1:7496/biotime`, which on that PC is production ZKBioTime.
5. **No secrets, personnel exports or biometric data in Git or chat.** Never copy secrets from Windows. Use
   your own `az login` / GitHub auth. `employee-directory-*.csv` exports stay off-repo.
6. **Do not change live Container Apps jobs/apps** (especially `onsite-sync-job`, cron `* * * * *`) during
   validation. Read-only `az ... show/list` is fine.
7. **Do not guess identities** (see IDENTITY-MATCHING.md). Do not modify ZKBioTime personnel or device user IDs.
8. Keep the three component names exact: Diji On-site Agent / Diji On-site Attendance / Diji On-site.

## First commands (macOS)

```bash
cd "/Volumes/SD_APFS/Diji Projects/DijiOne/dijione-platform"
git remote -v                      # expect github.com/IMWeeriyasinghe/dijione-platform
git status --short                 # must be clean before switching branches; report anything found
git fetch --all --prune
git log --oneline -1 origin/release/onsite-v1   # integration line (7eabdc6 or newer)
git log --oneline -1 origin/docs/onsite-handover
git switch docs/onsite-handover 2>/dev/null || git switch -c docs/onsite-handover --track origin/docs/onsite-handover
ls docs/onsite/handover/
```

Then follow [README.md](README.md) reading order, [MAC-DEVELOPMENT-SETUP.md](MAC-DEVELOPMENT-SETUP.md)
for the toolchain, and [VALIDATION-CHECKLIST.md](VALIDATION-CHECKLIST.md) for safe validation.

## What to report back before any development

- Repo path, remote, branch, HEAD, clean/dirty state (both repos).
- Toolchain versions found vs required.
- Results of the safe test commands.
- Anything in this package that disagrees with the code or live (read-only) state.
- Your prioritized next-task list (start from CURRENT-STATUS-AND-BACKLOG.md).

**Wait for the user's approval before starting any development work.**
