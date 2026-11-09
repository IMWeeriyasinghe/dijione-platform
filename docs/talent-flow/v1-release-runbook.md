# DijiTalentFlow V1 release runbook

Every step needs its own approval. Never run a full `main.bicep` deployment
for this release: it removes custom domains and ad hoc settings
(`deploy/README.md`).

## Build

1. Commit the release candidate and pass CI, including PostgreSQL 16 and
   Alembic checks.
2. Build once from the clean commit with `az acr build`: `talent-api`,
   `recruitment-api`, `talent-web`, `talentflow-portal-web`, `shell-web`.
3. Record each digest. No migration is included in this release.

## DEV

1. Update each app by digest with `az containerapp update --image`.
2. Set `EXTERNAL_PORTAL_BASE_URL` on `talent-api` to the DEV portal URL.
3. Smoke test sign-in, then run one sync and one reconcile.
4. Record sync duration. Above about 240 s, stop and review the read budget.
5. Confirm the run reports `SUCCEEDED`, or review why it reports `PARTIAL`.

## UAT

1. Promote the same digests and set the UAT portal URL.
2. Confirm the first scheduled sync and reconcile, by logs.
3. Compare per-posting candidate counts with Lever for a sample of postings.
4. Review the 30 unknown-tag postings with TA.
5. Check existing `TALENT_CLIENT` accounts: a user without one resolved client
   now receives 403.
6. Run the role, isolation, withdrawal, field-exposure, callback and access-link
   checks, using test identities and a non-sensitive client.
7. Obtain business sign-off.

## Hosted checks that cannot be made locally

- **Access-link rate limit.** `POST /external/redeem` limits by
  `request.client.host`. Behind the portal rewrite and ingress that address may
  be a proxy, so all clients could share one 10-attempt window. Do not trust
  `X-Forwarded-For` until UAT shows who appends it: log the peer address and the
  header from two client networks, then choose a trusted hop count.
- **Notifications** are best-effort: one attempt, no retry or outbox, because
  the platform endpoint has no idempotency key. Failures are logged as
  `side effects undelivered`. Alert on that log line.
- **Sync heartbeat.** Confirm a long run's `updated_at` advances about every
  30 s, and a replica killed mid-run is recovered about 10 minutes later.

## Production

1. Confirm a recent restore point and capture current digests and settings.
2. `az acr import` by digest and confirm the digests match.
3. Update only the changed apps; confirm the `shell-web` domain stays bound.
4. Set the PROD portal URL.
5. Run reconcile and **review mapping changes before issuing any client link**:
   the first run applies all accumulated Lever changes, withdrawals and
   retirements.

## Rollback

1. Restore each app's previous digest with `az containerapp update --image`.
2. Remove `EXTERNAL_PORTAL_BASE_URL` if required.
3. Revoke grants to cut client access immediately.
4. Retired requests and unshared candidates do not revert with the image.
   Restore sharing through staff actions, or use a separately approved
   point-in-time restore.
