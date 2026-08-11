# Lever Integration

## Ownership

Lever is Dijital Team's Applicant Tracking System and recruitment source of
truth (CLAUDE.md §26): candidates, opportunities, requisitions, postings,
pipeline stages, interviews, feedback, offers. DijiTalentFlow does not
duplicate this data — it stores only what it needs to drive its own UI and
workflow state (see `docs/talent-flow/data-model.md`), linked back to Lever
via `ExternalMapping`.

## Architecture

```text
apps/api/app/integrations/lever/
├── client.py        # LeverClient — abstract interface
├── mock_client.py    # MockLeverClient — realistic in-memory data
├── mapper.py         # LEVER_STAGE_MAP — provider stage text → CanonicalStage
└── schemas.py         # Provider-shaped DTOs (never returned to the frontend)
```

`app/integrations/factory.py: get_lever_client()` returns `MockLeverClient`
whenever `INTEGRATIONS_MODE=mock` (the default) or no `LEVER_API_KEY` is
configured — which is always true in this build phase, since no
credentials have been supplied (CLAUDE.md §58/§60). A live `LeverClient`
implementation is not built yet; calling `get_lever_client()` in "live"
mode without a key raises `IntegrationNotConfiguredError` rather than
silently falling back, so a misconfiguration is loud, not silent.

## Stage mapping

`LEVER_STAGE_MAP` (`mapper.py`) maps Lever's actual pipeline stage text
(e.g. `"Client Submission"`, `"Onsite Interview"`, `"Offer Extended"`) into
DijiOne's fixed `CanonicalStage` enum. This mapping is a placeholder built
from typical Lever pipeline naming — it **must** be revisited during Phase
D/E live discovery (CLAUDE.md §59) against the client's actual Lever
pipeline configuration. An unrecognized stage text falls back to
`SOURCING` rather than raising, so a mapping gap degrades gracefully.

## Sync / webhook handling

`POST /api/webhooks/lever` → `SyncService.process_lever_event`:

1. Look up `(provider="LEVER", external_event_id)` in `IntegrationEvent`;
   if already present, return the existing row unprocessed (idempotent —
   CLAUDE.md §64-65).
2. Otherwise record a new `IntegrationEvent`, resolve the Lever
   `opportunityId` to an internal `Application` via `ExternalMapping`, map
   the reported stage through `LEVER_STAGE_MAP`, update the `Application`,
   and write an `AuditLog` entry (`action="application.stage_synced_from_lever"`).
3. On any error, the event is marked `FAILED` and `TA_MANAGER` users are
   notified (`INTEGRATION_SYNC_FAILED`) — the failure is recorded, not
   swallowed.

No write ever goes back to Lever from this MVP — all initial integration
work is read-only (CLAUDE.md §28/§60).

## Going live (Phase D onward)

1. Request read-only Lever API access once the app reaches ~55-65%
   maturity (CLAUDE.md §59 Phase D).
2. Implement `LiveLeverClient(LeverClient)` in `client.py` using `httpx`
   against `LEVER_BASE_URL`, authenticated with `LEVER_API_KEY`.
3. Update `LEVER_STAGE_MAP` against the real pipeline's stage names.
4. Switch `INTEGRATIONS_MODE=live`; `get_lever_client()` requires no other
   code changes.
5. Add Lever webhook signature validation before accepting production
   traffic on `/api/webhooks/lever` (Phase G hardening).
