# Release runbook — Access Notifications V2 (platform-api + admin-web 1.7.0)

**Changes:**
- platform-api: snapshot v2, application-specific events, origin, migration `v4w6y8a0c2e4`
  (Birthday registry name → "DIJI Birthday").
- admin-web 1.7.0: origin shown in Notifications details.

**No change to:** mail transport, policy, sender, Exchange or Graph, or any other application.
Promote **the same image digests** DEV → UAT → PROD. Use image-only updates; never a full Bicep
deployment.

## Before each environment
1. **Recovery point.** Record the time (UTC) as the PostgreSQL point-in-time restore point for
   the platform database.
2. **Rollback revisions.** Record the current platform-api and admin-web revisions.
3. **Notification queue health,** read-only against the platform database:
   ```sql
   SELECT status, count(*) FROM email_outbox GROUP BY status;
   SELECT count(*) FROM email_outbox WHERE status IN ('PENDING','SENDING','RETRY');  -- expect 0 or a few genuine
   SELECT count(*) FROM users u WHERE NOT EXISTS (SELECT 1 FROM user_access_snapshots s WHERE s.user_id = u.id);  -- expect 0
   ```
4. **Mail configuration guard:** `deploy/mail-config-guard.sh <rg> deploy/bicep/main.<env>.bicepparam`
   must exit 0.

## Release (per environment)
1. **Migration.** Update the `migrate-platform-api` job to the new platform-api digest, then start
   it (`alembic upgrade head` → `v4w6y8a0c2e4`).
   - **Sessions:** every user's `access_version` is bumped, so all sessions are re-issued on their
     next request. People may be asked to sign in again. Schedule outside peak hours.
2. **platform-api image.** `az containerapp update -g <rg> -n platform-api --image <repo>@<digest>`.
   - **Startup:** the new revision upgrades v1 snapshots silently, within a 20 s budget, before it
     serves traffic. The dispatcher sweep finishes the rest and covers the rolling-switch window
     (30 minutes).
3. **admin-web image.** `az containerapp update -g <rg> -n admin-web --image <repo>@<digest>`.
4. **Configuration diff.** Before/after diff of env, secrets, identity, ingress and scale must show
   the image as the only change. The mail guard must still exit 0.

## After each environment (read-only)
```sql
-- 1. No release-generated burst: rows queued during the release window must be explained by genuine changes.
SELECT id, created_at, event_type, application_key, recipient_user_id, status
FROM email_outbox WHERE created_at >= :release_start ORDER BY id;

-- 2. Every snapshot is v2 (after the sweep): expect 0.
SELECT count(*) FROM user_access_snapshots WHERE snapshot NOT LIKE '%"v": 2%';

-- 3. Switchover review: access changes made from 5 minutes before to 5 minutes after the
--    revision switch. A role-, client- or administration-only change in this window may not
--    have been emailed (documented residual); review manually.
SELECT id, created_at, action, actor_id, subject_user_id, event_metadata
FROM audit_logs
WHERE created_at BETWEEN :switch_time - interval '5 minutes' AND :switch_time + interval '5 minutes'
  AND (action LIKE 'module_assignment.%' OR action LIKE 'application_admin.%' OR action LIKE 'user.platform_role%'
       OR action LIKE 'group%' OR action LIKE 'module_access.%')
ORDER BY id;
```
- **Revision health:** Healthy, 100% traffic. The live admin-web bundle shows `1.7.0`.

## Rollback
- **Images:** move traffic to the recorded previous revisions of platform-api and admin-web.
  v1 code reads v2 snapshots safely, because it compares only `active`, `permissions` and
  `default_only`. Its startup rebaseline then rewrites snapshots to v1 silently.
- **Migration:** downgrade only if required: `alembic downgrade u3v5x7z9b1d3`, which restores
  "DijiBirthday". Otherwise leave it; the name is harmless to v1.
- **Mail:** unchanged throughout. Turning delivery off stays the existing procedure (remove the
  platform-api `MAIL_*` settings).
