# DijiTalentFlow V1 DEV deployment plan

Prepared, not executed. Every command needs separate approval. Do not run a full
`main.bicep` deployment (`deploy/README.md`). Run all commands against
`rg-dijione-dev` only.

## Source

Build from commit `ac4a04dc6f0484555d91d4939d6000060121106f` on `fix/talent-phase2-security`, after CI passes on the
PR head. The later commit that records this SHA changes documentation only.

## Services and rollback images

Current DEV digests, read on 2026-11-09. Registry: `crdijionenonprod.azurecr.io/dijione`.

| Order | App | Change | Rollback digest (`sha256:`) | New digest |
|---|---|---|---|---|
| 1 | `recruitment-api` | Sync hardening | `04c2f76fdb8201170ef99cf8419ee5ec0dc925d41254cdfa041f8703770890af` | Record at build |
| 2 | `talent-api` | Security, reconcile, DTOs | `ad5776134a1af26c05bdfc65240a5de6839dc12be10ffc9e80ee94fc46e2919b` | Record at build |
| 3 | `talent-web` | Screens, accessibility | `f69e6c11d2cb7a86ff871e8c7ef4d91607f168482a90a3d80098ea5f2f672ab7` | Record at build |
| 4 | `talentflow-portal-web` | Portal, accessibility | `f5d559d572e03318146edb86024e090333c8781124176ad83b096d13d8553bf5` | Record at build |
| 5 | `shell-web` | Sign-in callback XSS fix | `3cf02863ec5d77c655748d3d17829c469ad68a626ae9ec2582079eea806242ae` | Record at build |

Backends go first because the new API fields are additive for the current web
apps. Unchanged: `platform-api`, all other apps, schedules and secrets.

**`shell-web` compatibility.** DEV runs image tag `fd98c09`. Between that commit
and this release, `apps/shell-web` differs only in the auth callback fix and its
test, and `next.config.ts` is identical, so module routes do not change. Shared
changes are the `UserMenu` accessibility attributes and contract types.
`fd98c09` is not an ancestor of this branch, but no other shell source differs.

## Jobs

`talent-reconcile-job`, `recruitment-sync-job`, `migrate-*` and
`bootstrap-talent-clients` stay unchanged. The scheduled jobs call the APIs, so
new behaviour comes from the app images.

## Configuration

| App | Setting | Value |
|---|---|---|
| `talent-api` | `EXTERNAL_PORTAL_BASE_URL` (currently absent) | `https://talentflow-portal-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io` |

No secret changes. Confirm `talent-api` does not carry `TEST_`-style overrides.

## Database

No migration in this release: talent head `b3c5d7e9f1a2`, recruitment head
`0002_widen_free_text`. Confirm both from `/health/deep` before starting, since
DEV revisions were not confirmed in the audit.

## Commands (template)

```bash
# APIs: -f deploy/Dockerfile.api --build-arg SERVICE=<app>
# Web:  -f deploy/Dockerfile.web --build-arg APP=<app> --build-arg GIT_SHA=<sha> --build-arg BUILD_DATE=<date>
az acr build -r crdijionenonprod -t dijione/<app>:<sha> <flags above> .
az containerapp update -g rg-dijione-dev -n <app> --image crdijionenonprod.azurecr.io/dijione/<app>@sha256:<new>
az containerapp update -g rg-dijione-dev -n talent-api --set-env-vars EXTERNAL_PORTAL_BASE_URL=<url>
```

Rollback: the same `update` with the digest above, per app, in reverse order.
Remove the portal setting if required. Retired requests and unshared candidates
do not revert with the image.

## Verification

1. `/health` and `/health/deep` on both APIs: expected revisions, database reachable.
2. Staff sign-in through Entra reaches the TalentFlow dashboard with real role claims.
3. The crafted callback error URL renders inert.
4. Portal: open the URL. Issue one test link to a non-sensitive test client only
   with approval, confirm it points at the portal URL, redeem, then revoke.
5. Anonymous and forged-token API calls return 401.
6. Reconcile, on approval: start one sync and one reconcile. Record duration; above
   about 240 s, stop and review. The outcome must be `SUCCEEDED`, or a reviewed `PARTIAL`.
7. Confirm heartbeat: a long run's `updated_at` advances about every 30 s.
8. Rate limit: log the peer address and `X-Forwarded-For` from two client networks.
9. Confirm other DEV apps, routes and custom domains are unaffected.
