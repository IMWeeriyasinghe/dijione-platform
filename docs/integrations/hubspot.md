# HubSpot Integration

> **HubSpot is not on the critical path** for associating a Lever job
> posting with a DijiTalentFlow client. That is done by the governed Lever
> posting tag `DTC - <Client Name>` — see
> `docs/platform/recruitment-source.md` "DTC client-tag resolution" and
> `CLAUDE.md` rule 4a. HubSpot / the Commercial-CRM domain remains
> **deferred**, for future commercial/company data only — never for client
> identity, which is permanently `platform-api`-owned
> (`docs/platform/data-ownership.md` §1).

## Ownership

HubSpot is Dijital Team's CRM/commercial system of record (CLAUDE.md §25):
companies, contacts, deals, sales/marketing activity. It is **not** assumed
to contain the detailed recruitment pipeline — that is Lever's job (see
`docs/integrations/lever.md`).

`apps/commercial-api` (port 8007) is the sole DijiOne owner of the HubSpot
integration, per Architecture Completion Plan Wave F — not `talent-api`,
which held this code before the extraction and now imports nothing from
`hubspot`. talent-api's `main.py` docstring states this explicitly: "holds
no Lever or HubSpot credential."

There is already an authorized HubSpot application visible in Lever
(CLAUDE.md §28) — nothing in this codebase touches, alters, or revokes that
integration.

## Current status: skeleton, no live client, no credential requested

```text
apps/commercial-api/app/integrations/hubspot/
├── client.py        # HubSpotClient — abstract interface
├── mock_client.py    # MockHubSpotClient — realistic in-memory data
└── schemas.py         # Provider-shaped DTOs (never returned to the frontend)
```

`app/integrations/factory.py: get_hubspot_client()` follows the same
mock-by-default pattern the Lever client used before its own live
verification: `INTEGRATIONS_MODE=mock` (the default, and the only mode ever
exercised for HubSpot to date) or a missing `HUBSPOT_ACCESS_TOKEN` returns
`MockHubSpotClient`; a "live" mode without a token raises
`IntegrationNotConfiguredError` instead of failing silently. No
`HUBSPOT_ACCESS_TOKEN` has been requested or supplied.

`commercial-api` owns exactly one table today, `integration_events` — a
webhook-delivery idempotency log, nothing else. There is no company/deal
read model yet; that is built when live access lands (see "Going live"
below).

## Webhook handling

`POST /api/commercial/webhooks/hubspot` → `SyncService.process_hubspot_event`
dedupes on `(provider="HUBSPOT", external_event_id)` before recording an
`IntegrationEvent`. No HubSpot event currently drives any domain mutation
anywhere in DijiOne — this endpoint exists to prove the architecture and
log activity for future use. It is gated by a pre-shared-secret placeholder
(`HUBSPOT_WEBHOOK_SECRET`), enforced outside `app_env=development` — **not**
HubSpot's real v3 signature scheme (HMAC over method+URI+body+timestamp
with the app's client secret), since there is no live HubSpot
app/credential yet to validate a real implementation against. Swap for the
real scheme in step 2 below.

## Going live (Phase D onward, CLAUDE.md §59)

1. Request read-only HubSpot access at ~55-65% maturity.
2. Implement `LiveHubSpotClient(HubSpotClient)` using `httpx` against
   `HUBSPOT_BASE_URL`, authenticated with `HUBSPOT_ACCESS_TOKEN`; replace
   the placeholder webhook secret check with HubSpot's real v3 signature
   verification.
3. Build the commercial-facts read model in `commercial_dev`, keyed by
   `client.public_id` (industry, account owner, deal context) —
   `docs/platform/data-ownership.md` §1. `commercial-api` may **propose**
   newly-discovered organisations for a platform-admin to confirm into the
   platform-owned `client` master; it never creates or owns the identity
   row itself.
4. Decide which HubSpot fields should surface on the Client Portfolio page
   in `talent-web`, and extend the relevant DTO accordingly — HubSpot data
   must still be converted into an internal DTO, never returned raw
   (CLAUDE.md §27).
5. Switch `INTEGRATIONS_MODE=live`.
