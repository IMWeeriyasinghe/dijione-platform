# HubSpot Integration

## Ownership

HubSpot is Dijital Team's CRM/commercial system of record (CLAUDE.md §25):
companies, contacts, deals, sales/marketing activity. It is **not** assumed
to contain the detailed recruitment pipeline — that is Lever's job (see
`docs/integrations/lever.md`). DijiTalentFlow uses HubSpot only for
client/company context.

There is already an authorized HubSpot application visible in Lever
(CLAUDE.md §28) — this build does not touch, alter, or revoke that
integration; all HubSpot work here is a separate, read-only, mock-first
adapter.

## Architecture

```text
apps/api/app/integrations/hubspot/
├── client.py        # HubSpotClient — abstract interface
├── mock_client.py    # MockHubSpotClient — realistic in-memory data
└── schemas.py         # Provider-shaped DTOs (never returned to the frontend)
```

`MockHubSpotClient` seeds companies matching the demo `Client` rows (ABC
Company, XYZ Company, Nova Solutions) with plausible contacts and deals, so
the mapping between a DijiTalentFlow `Client` and a HubSpot company can be
demonstrated via `ExternalMapping` (`provider="HUBSPOT",
external_object_type="company"`) — see `scripts/seed.py`.

`app/integrations/factory.py: get_hubspot_client()` follows the same
mock-by-default pattern as the Lever client: `INTEGRATIONS_MODE=mock` or a
missing `HUBSPOT_ACCESS_TOKEN` returns `MockHubSpotClient`; a "live" mode
without a token raises `IntegrationNotConfiguredError` instead of failing
silently.

## Webhook handling

`POST /api/webhooks/hubspot` → `SyncService.process_hubspot_event` follows
the same idempotency pattern as Lever: dedupe on `(provider="HUBSPOT",
external_event_id)` before recording an `IntegrationEvent`. No HubSpot
event currently drives a DijiTalentFlow domain mutation (HubSpot doesn't
own recruitment pipeline state), so this endpoint exists primarily to
prove the architecture and log activity for future use (e.g. surfacing
deal context on a client portfolio page).

## Going live (Phase D onward)

1. Request read-only HubSpot access at ~55-65% maturity (CLAUDE.md §59).
2. Implement `LiveHubSpotClient(HubSpotClient)` using `httpx` against
   `HUBSPOT_BASE_URL`, authenticated with `HUBSPOT_ACCESS_TOKEN`.
3. Decide which HubSpot fields (industry, deal stage, primary contact)
   should surface on the Client Portfolio page, and extend
   `ClientPortfolioOut` accordingly — HubSpot data must still be converted
   into an internal DTO, never returned raw (CLAUDE.md §27).
4. Switch `INTEGRATIONS_MODE=live`.
