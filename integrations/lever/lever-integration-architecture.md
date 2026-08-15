# Lever Integration Architecture — Foundation Phase

> Companion to `lever-api-capabilities.md` (public API docs) and
> `lever-live-discovery.md`-equivalent findings (live tenant discovery,
> summarized in conversation and in this repo's commit history). This
> document records the architectural decisions made when building the
> read-only Lever integration foundation, so future work doesn't have to
> re-derive them.

## Core facts this architecture is built on

- **Lever Posting is the real job-demand entity** in this tenant. Lever
  Requisitions were confirmed, by live read-only discovery, to be
  completely unused (`GET /requisitions` → `[]`, `GET /requisition_fields`
  → `[]`, every sampled Posting's `requisitionCodes` was empty). Do not
  build sync logic that depends on Requisitions.
- **The Posting → Client relationship is intentionally pluggable and
  fails closed.** No client-role user may ever see a Lever-sourced
  Posting, or any candidate/application under it, until an explicit,
  verified `PostingClientMapping` row exists for that exact client. Tag
  text, posting titles, and "About the Client" description prose may
  contain human-readable client hints and are shown to staff as
  diagnostics only — never treated as authorization evidence.
- **`Posting` and `PostingClientMapping` are separate tables.** `Posting`
  is pure Lever-sourced read-model data, freely overwritable by a future
  re-sync. `PostingClientMapping` is the DijiOne-owned trust/provenance
  record (`status`: UNMAPPED/VERIFIED/REJECTED, `source`:
  MANUAL/LEVER_STRUCTURED_FIELD/HUBSPOT/OTHER_VERIFIED_SOURCE). Only
  `MANUAL` is settable by anything built so far, via a staff-only
  verify-mapping route.
- **"Hired" is a Lever Archive Reason, not a pipeline stage.** The real
  14-stage pipeline has no hire/deploy stage at all. `map_lever_archive_outcome`
  handles hire/withdraw/reject outcomes separately from
  `map_lever_stage`.
- **"Deployed" is exclusively DijiOne-owned, post-hire state.** Lever has
  no equivalent concept and must never be expected to supply it.
- **Offer compensation is deliberately excluded from everything.** Only
  `lever_offer_status` and `lever_offer_created_at` are synced onto
  `Application`; salary, bonus, equity, and offer documents are never
  read into any schema, model, or log.
- **Interview data source remains unresolved.** Live discovery found
  structured Lever Interview records empty even for opportunities in
  interview-designated stages — real interviews are very likely tracked
  outside Lever. `LeverClient.list_interviews` stays available but nothing
  depends on it.

## Read-only architecture (this phase)

```
Lever GET API
    -> LiveLeverClient (read-only by construction — no write-capable
       method exists on the class)
    -> Provider DTOs (app/integrations/lever/schemas.py)
    -> mapper.py (stage + archive-outcome mapping)
    -> Posting + PostingClientMapping (UNMAPPED by default)
    -> DijiTalentFlow read model
```

Webhook receiver (`POST /api/talent/webhooks/lever`) is hardened
(HMAC-SHA256 signature verification, enforced only when
`LEVER_WEBHOOK_SIGNING_SECRET` is configured; duplicate deliveries are
marked `IGNORED_DUPLICATE`) but production Lever webhooks are **not**
being activated in this phase.

## What was not built this phase

- No tag/title-text-based auto-resolution of client identity.
- No HubSpot-backed resolution.
- No production Lever webhook registration.
- No frontend UI (no existing Postings page to extend; deferred as
  separable work).
- No `TalentRequest` ↔ `Posting` linkage.
- No dependency on Lever's structured Interview data.
