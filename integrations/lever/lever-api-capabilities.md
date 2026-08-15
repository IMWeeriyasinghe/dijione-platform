# Lever API — Capability Investigation

> Documentation-only investigation of Lever's public developer API (`https://hire.lever.co/developer/documentation`). No code was written and no live Lever tenant was accessed for this report — everything below reflects what the API *documentation* describes as possible, not how Dijital Team's actual Lever account is configured. Claims not directly traceable to the documentation are explicitly marked "not verified." Use this as the reference for future DijiTalentFlow Lever integration design; it should be revisited once a live, read-only discovery pass against the real tenant is separately authorized.

**Sources used:** `https://hire.lever.co/developer/documentation`, `https://hire.sandbox.lever.co/developer/documentation`, `https://hire.lever.co/developer/updates`.

---

## 1. Executive Summary

Lever exposes a REST API (`https://api.lever.co/v1`, JSON over HTTPS, sandbox equivalent at `https://api.sandbox.lever.co/v1`) covering the full recruiting lifecycle: job postings, requisitions (headcount/approval tracking), candidates (via the "Opportunity" entity), applications, interviews, interview panels, feedback/scorecards, offers, users, tags, sources, notes, files/resumes, custom form fields, and referrals. Authentication is via Basic Auth (API key) for internal integrations or OAuth2 for partner integrations, with 48+ granular OAuth scopes. Lever supports webhooks for a defined but limited set of events (application/candidate/interview/contact changes) — webhook payloads are generally IDs-and-timestamps only, meaning most webhook-driven workflows require a follow-up API call to fetch full entity data. Lever is explicitly "candidate-centric": a Candidate/Contact can exist independent of any job, and an Opportunity represents that person's application/candidacy for one specific job at a time.

---

## 2. Lever Data Model

Verified from documentation text: "Lever is candidate-centric, meaning that candidates can exist in the system without being applied to a specific job posting." An Opportunity represents "a candidate's profile for a specific job posting." Applications are created when a candidate applies (or is added/referred) to a Posting, and documentation states "One opportunity contains one application maximum." Feedback, Interviews, Notes, Files, and Offers all hang off an Opportunity (accessed via `/opportunities/:opportunity/...` sub-resources), not off the Contact directly. Requisitions are a distinct entity for headcount/approval tracking; documentation references a `requisitionCode` concept but the precise Posting↔Requisition linkage field/semantics could not be fully confirmed in this pass (**not verified in detail** — see §5).

Verified relationship diagram (only relationships confirmed from docs):

```
Contact (person)
   └── 1..N Opportunity (candidacy for one specific job/track)
             ├── 0..1 Application (max one per Opportunity; links to a Posting)
             │            └── Posting (job/career-site listing)
             ├── 0..N Interview
             │            └── Feedback (scorecard, tied to interview/panel)
             ├── 0..N Note
             ├── 0..N File / Resume
             ├── 0..N Offer
             ├── Tags, Sources (labels on the Opportunity)
             └── Stage (current pipeline stage) / Archive state (+ Archive Reason)

Requisition (headcount/approval entity) — linked to Postings via requisitionCode
   (exact linkage mechanics: not verified in this pass)

Panel (interview panel) ── contains ── Interview(s) + interviewer Users
User (Lever seat holder) ── can be owner/hiringManager/follower/interviewer on Opportunities, Postings, Requisitions
```

---

## 3. Complete API Capability Inventory

| Lever Entity | Endpoint | Important Fields | Read | Create | Update | Delete | Webhook | Notes |
|---|---|---|---|---|---|---|---|---|
| Opportunities (candidate) | `/opportunities`, `/opportunities/:id`, `/opportunities/deleted` | id, contact, stage, archived, tags, sources, confidentiality, isAnonymized | Y | Y | Y (stage, archived, contact, tags, sources) | N (only via archive) | Y (indirect, via candidate* events) | Successor to deprecated "Candidates" endpoint |
| Candidates (legacy) | `/candidates/*` | — | Y (deprecated) | — | — | — | — | Documentation marks as deprecated; use Opportunities |
| Contacts | `/contacts/:id` | name, headline, location, emails, phones, isAnonymized | Y | N (created implicitly) | Y | N | Y (`contactCreated`, `contactUpdated`) | One contact can back multiple opportunities |
| Applications | `/opportunities/:opp/applications*` (deprecated path), `/applications/deleted` | opportunityId, createdAt, type, posting, postingOwner, customQuestions | Y | (created implicitly on apply) | N documented | N (only "deleted" listing) | Y (`applicationCreated`) | Deprecated direct GET endpoints noted in docs |
| Postings | `/postings`, `/postings/:id`, `/postings/deleted`, `/postings/:id/apply` | id, text, state, content, location, department, team, owner, hiringManager, followers, tags, sources, customQuestions | Y | Y | Y | N documented (only "deleted" list) | Not verified (no dedicated posting webhook found) | Supports HTML content; public `apply` endpoint |
| Requisitions | `/requisitions`, `/requisitions/:id`, `/requisitions/:id/requisition_fields` | id, requisitionCode, hiringManager, status, department, location (full field list **not verified**) | Y | Y | Y | Y | Not verified | Headcount/approval entity, distinct from Posting |
| Requisition Fields (custom) | `/requisition_fields`, `/requisition_fields/:id` | field definitions | Y | Y | Y | Y | N | Custom fields specific to requisitions |
| Interviews | `/opportunities/:opp/interviews*` | interview date/time fields (exact list **not verified**), panel, opportunity | Y | Y | Y | Y | Y (`interviewCreated`, `interviewUpdated`, `interviewDeleted`) | Webhook payload is IDs + timestamp only |
| Panels | `/panels`, `/panels/:id` | interviewers/panel membership | Y | Y | Y | Y | N (not documented separately) | Groups interviews into a panel |
| Feedback / Scorecards | `/opportunities/:opp/feedback*` | type, text, instructions, baseTemplateId, fields[], user, panel, interview, completedAt | Y | Y | Y | Y | N documented | Field types: code, date, dropdown, multiple-choice, multiple-select, score-system, score, scorecard, text, textarea, yes/no |
| Feedback Templates | `/feedback_templates*` | template structure | Y | Y | Y | Y | N | Reusable scorecard templates |
| Offers | `/opportunities/:opp/offers`, `/opportunities/:opp/offers/:offer/download` | offer document/download only (no create/update documented) | Y | N documented | N documented | N documented | N documented | Read/download-oriented; compensation field detail **not verified** |
| Stages (pipeline) | `/stages`, `/stages/:id` | id, text | Y | N | N | N | N (but `candidateStageChange` event exists on Opportunity) | Read-only list of configured pipeline stages |
| Disposition Stages | `/disposition_stages` | combines stage + archive reason, pipeline (lead/applicant/screen/onsite/offer), rank, hasInterview | Y | N | N | N | N | Useful for understanding pipeline taxonomy |
| Archive Reasons | `/archive_reasons`, `/archive_reasons/:id` | id, text, status, type (hired/non-hired) | Y | N | N | N | N | Used for rejection/hire disposition tracking |
| Users | `/users`, `/users/:id`, deactivate/reactivate | id, name, email, accessRole | Y | Y | Y | N (deactivate instead) | N documented | Represents internal Lever seat holders |
| Sources | `/sources` | list of source labels | Y | N | N | N | N | Read-only reference list |
| Tags | `/tags` | list of tag labels | Y | N | N | N | N | Read-only reference list |
| Notes | `/opportunities/:opp/notes*` | text, author, timestamps | Y | Y | N documented | Y | N | Tied to Opportunity, not Contact |
| Files | `/files`, `/files/:id`, `/files/:id/download`, `/opportunities/:opp/files` | file metadata + binary download | Y | Y | N documented | Y | N | Formats: docx, doc, js, jpg, png, pdf, txt |
| Resumes | `/resumes`, `/resumes/:id`, `/resumes/:id/download` | resume metadata + binary download | Y | N documented separately (via Files/apply) | N | N | N | Resume is effectively a typed File |
| Uploads | `/uploads` | generic upload | N | Y | N | N | N | Used to attach documents |
| Custom Fields — Form Fields | posting/profile form definitions | 13+ field types incl. currency, date, dropdown, file-upload, score, scorecard | Y | Y (via posting/profile forms) | Y | Y | N | Definitions queryable via Posting/Profile Forms endpoints |
| Posting Forms / Profile Forms | `/profile_forms*`, `/profile_form_templates*` | custom application/profile form structures | Y | Y | Y | Y (templates only) | N | Defines candidate-facing custom questions |
| Referrals | `/referrals`, `/referrals/:id` | referral submissions | Y | N documented | N | N | N | Read-only per docs excerpt reviewed |
| EEO / Diversity Surveys | `/eeo/responses`, `/eeo/responses/pii`, `/surveys/diversity/:id` | demographic fields, both anonymous and PII variants | Y | N | N | N | N | Sensitive data; separate PII-gated endpoint |
| Audit Events | `/audit_events` | user provisioning/auth/export tracking (28 action types) | Y | N | N | N | N | Add-on feature per docs |
| Webhooks (config) | `/webhooks`, `/webhooks/:id` | target URL, event type, configuration | Y | Y | Y | Y | N/A (this endpoint manages webhooks themselves) | Requires Super Admin to configure via UI; API also available |

---

## 4. Candidate & Recruitment Pipeline Analysis

- **Unique person identifier:** the **Contact** object (`id`), not the Opportunity. A Contact holds name, emails, phones, headline, location, and an `isAnonymized` flag.
- **Multiple opportunities per person:** confirmed structurally — a Contact can back more than one Opportunity (one Opportunity is scoped to "a candidate's profile for a specific job posting"; the same person applying to two different jobs, or being reconsidered for a role, would produce multiple Opportunity records tied to one Contact). `GET /opportunities` documents a `contact_id` filter, which only makes sense if multiple opportunities can share a contact — this is direct structural evidence.
- **Pipeline movement:** represented via `PUT /opportunities/:opportunity/stage` (moves to a new Stage) and `PUT /opportunities/:opportunity/archived` (archive/unarchive, with an associated Archive Reason of type "hired" or "non-hired"). The `disposition_stages` endpoint combines both concepts (active pipeline stage + archive/rejection reasons) into one taxonomy.
- **Candidate history:** Opportunity-level webhooks (`candidateStageChange` includes `fromStageId`/`toStageId`; `candidateArchiveChange` includes `fromArchived`/`toArchived` and `archivedAt`) imply Lever tracks state transitions, but whether a full timeline/audit history is retrievable via a dedicated GET endpoint (vs. only via webhook events captured historically by the integrator) **could not be confirmed from documentation** in this pass.
- **IDs to store externally:** at minimum, `contactId` (person identity) and `opportunityId` (candidacy/application instance) should both be persisted, since they serve different purposes — the same person may need to be recognized across multiple opportunities, but a specific candidacy's pipeline state is tracked at the Opportunity level.

---

## 5. Requisition / Posting Analysis

Per the docs actually retrieved:

- **Posting** = a job listing/career-site entry. Confirmed fields: `id`, `text` (title), `state`, `content`, `location`, `department`, `team`, `owner`, `hiringManager`, `followers`, `tags`, `sources`, `customQuestions`. Supports HTML body content. Has a public-facing `POST /postings/:posting/apply` endpoint (i.e., Postings are what candidates literally apply to).
- **Requisition** = a headcount/approval-tracking entity, separate from Postings. Confirmed fields (partial): `id`, `requisitionCode`, `hiringManager`, `status`, `department`, `location`. The documentation references a `requisitionCode` as the evident linking mechanism between Requisitions and Postings, but the **precise linkage semantics (one-to-one vs. one-to-many, which side stores the reference) could not be fully confirmed from the documentation retrieved in this pass** — flagged as not verified and worth a targeted follow-up read of the Requisitions doc section.
- **Opportunity** is neither of the above — it is the candidate's application instance against a Posting (see §2). Requisitions do not appear to directly hold candidates; they exist one level above Postings for headcount/approval purposes.
- Fields such as compensation bands, employment type enum values, headcount numbers (`headcount`/`offeredHeadcount`/`closedHeadcount` were seen only in secondary/aggregator sources, not confirmed directly in Lever's own doc text during this pass) are **not verified** and should be confirmed via a direct schema read or a live sandbox call.
- Custom fields on Requisitions are explicitly supported via a dedicated `/requisition_fields` endpoint (full CRUD), separate from Posting custom questions.

---

## 6. Interview Analysis

Confirmed retrievable via `/opportunities/:opportunity/interviews` (list/get/create/update/delete): interviews are tied to a specific Opportunity and to a Panel (`panelId`). Feedback/scorecards are linked back to a specific `interview` and `panel` (see Feedback object fields: `user`, `panel`, `interview`, `completedAt`). Detailed interview fields such as exact date/time, duration, timezone, location, and interviewer list are referenced by the doc's table of contents but the **exact field names/types could not be fully extracted in this pass** (marked not verified) — the entity's existence, its CRUD support, and its 3 webhook events (created/updated/deleted) are confirmed. Interview status/cancellation state field existence is plausible given "canceled" is a commonly cited field in secondary sources, but is **not verified** directly from Lever's own text here.

---

## 7. Offer Analysis

Confirmed: Offers are sub-resources of Opportunities (`/opportunities/:opportunity/offers`), with a `download` endpoint for the offer document/PDF (`/opportunities/:opportunity/offers/:offer/download`). The documentation excerpt retrieved in this pass showed **read/download support only** — no POST/PUT create-or-update endpoints for Offers were found in what was retrieved, so **create/update capability for Offers via API is not verified and should not be assumed present**. Detailed compensation field names (base salary, bonus, equity, start date, offer status enum) were **not verified** in this pass. Offer data (compensation, signed documents) is inherently sensitive/PII-adjacent and likely falls under the "confidential data" access-gating mentioned generally in the docs (API keys need explicit confidential-data grant) — this general confidentiality mechanism is confirmed, though its specific application to Offers specifically is inferred, not directly quoted.

---

## 8. User / Recruiter Analysis

Confirmed via `/users` endpoints: Users represent internal Lever seat holders with `id`, `name`, `email`, `accessRole`, and support create/update/deactivate/reactivate (no hard delete). Users relate to other entities as: Posting `owner`/`hiringManager`/`follower`, Requisition `hiringManager`, Opportunity `postingOwner` (via Application), Panel/Interview `interviewers`, and Feedback `user` (the feedback author). This gives a documented (though not always exhaustively field-listed) way to trace recruiter, hiring manager, and interviewer identities back to specific candidates and jobs.

---

## 9. Custom Field Analysis

Custom fields are supported in multiple places with different mechanisms:
- **Requisitions**: dedicated `/requisition_fields` endpoint with full CRUD — field definitions are queryable and writable via API.
- **Postings**: `customQuestions` on the Posting object, and dedicated Posting Forms / Profile Forms / Profile Form Templates endpoints (full CRUD on templates) define custom application/profile questions, supporting 13+ field types (code, currency, date, dropdown, file-upload, multiple-choice, multiple-select, note, score-system, score, scorecard, text, textarea, yes/no).
- **Feedback**: scorecard `fields[]` array on the Feedback object, sourced from Feedback Templates (full CRUD).
- Discovery/definition access is generally read+write via API for the container objects (requisition_fields, feedback_templates, profile_form_templates), meaning custom field *definitions*, not just values, are queryable — this is confirmed structurally, though the exact response shape for each field type was not individually verified.

---

## 10. Client Identification Analysis

Lever's documentation, as retrieved, shows **no native Client/Customer/Account entity** for representing an external staffing client (which matters for a staffing/ATS-integration use case like Diji Talent Flow). Structurally possible mechanisms per the API surface actually confirmed:
- **Tags** on Opportunities/Postings (free-text labels, read-only list endpoint but tags are assignable via `PUT /opportunities/:opportunity/tags`).
- **Requisition custom fields** (`/requisition_fields`) — could hold a client identifier as a structured custom field on the Requisition.
- **Posting fields** `department`/`team` — generic organizational grouping fields that could be repurposed, though they are documented as department/team concepts, not explicitly client concepts.
- **Sources** — documented as candidate-sourcing-channel labels, not client identity, but structurally a similarly-shaped list.

No recommendation is made here — this section only reports what is structurally possible based on confirmed API objects. Whether Dijital Team actually uses one of these mechanisms for client identity is unverifiable from documentation alone (see §15 Q1/Q4).

---

## 11. Webhook Inventory

Confirmed webhook events and payload shape (all include common envelope fields `triggeredAt`, `event`, `token`, `signature`, `data`):

| Event | Configurable (source trigger) | Payload data fields | Follow-up GET needed for full record? |
|---|---|---|---|
| `applicationCreated` | Y | `applicationId`, `opportunityId`, `contactId` | Yes |
| `candidateHired` | Y | `opportunityId`, `contactId` | Yes |
| `candidateStageChange` | Y | `opportunityId`, `fromStageId`, `toStageId`, `contactId` | Yes |
| `candidateArchiveChange` | Y | `opportunityId`, `fromArchived`, `toArchived` (incl. `archivedAt`, reason UID), `contactId` | Partial — archive state included, but full opportunity data still needs a GET |
| `candidateDeleted` | N | `opportunityId`, `deletedBy`, `contactId` | N/A (deletion) |
| `interviewCreated` | N | `interviewId`, `panelId`, `opportunityId`, `createdAt` | Yes |
| `interviewUpdated` | N | `interviewId`, `panelId`, `opportunityId`, `updatedAt` | Yes |
| `interviewDeleted` | N | `interviewId`, `panelId`, `opportunityId`, `deletedAt` | N/A (deletion, but IDs given for local cleanup) |
| `contactCreated` | N | `contactId`, `createdAt`, `accountId` | Yes (for full contact details) |
| `contactUpdated` | N | `contactId`, `updatedAt`, `accountId` | Yes |

No webhook events for **Offers**, **Postings**, **Requisitions**, **Feedback**, **Notes**, or **Users** were found in the documentation retrieved — **not verified as existing**; treat these as polling-only unless a follow-up check of the full webhook doc page finds additional events.

**Feasibility conclusion:** Event-driven integration is **partially feasible** — candidate pipeline movement, hires, archiving, applications, interviews (create/update/delete), and contact changes can be pushed via webhook, but every payload is IDs-plus-timestamps only (with `candidateArchiveChange` giving slightly more detail), so a follow-up API call is required in nearly all cases to get usable data. Entities with no webhook coverage at all (Offers, Postings, Requisitions, Feedback) would require **polling** for change detection, since Lever provides no push notification for changes to those objects based on what was found in this pass.

**Webhook security:** confirmed HMAC-SHA256 signing — verify by concatenating the signing token and `triggeredAt`, HMAC-SHA256 with the account's signature token as key, and comparing to the provided `signature` hex digest. HTTPS-only endpoints, self-signed certs rejected, failed deliveries retried up to 5 times with increasing intervals.

---

## 12. Authentication / API Limits

- **Auth mechanisms:** Basic Auth using an API key as username with blank password (for internal/first-party integrations), or OAuth2 (required for partner/third-party integrations) with authorization-code flow against `https://auth.lever.co/authorize` and `https://auth.lever.co/oauth/token`, Bearer tokens, 1-hour default access-token expiry, and refresh tokens (`offline_access` scope).
- **Scopes:** 48+ granular OAuth scopes confirmed, generally following a `<entity>:read/write:admin` pattern (e.g. `opportunities:read:admin`, `postings:write:admin`, `requisitions:read:admin`, `interviews:write:admin`, `webhooks:read:admin`), plus `confidential:access:admin` specifically for confidential postings/opportunities/requisitions.
- **Sandbox environment:** confirmed to exist — `https://api.sandbox.lever.co/v1` and `https://hire.sandbox.lever.co/developer/documentation` mirror the production API/docs, intended for partner development.
- **Rate limits:** confirmed as token-bucket — 10 requests/second per API key sustained, burst up to 20 requests/second; documentation notes these defaults "may vary with server load."
- **Pagination:** `limit` (1–100, default 100) and `offset` query params; responses include `data`, `next` (offset token), and `hasNext` boolean. Max page size is 100.
- **Historical data limitations:** the `/applications/deleted` and (implicitly, by pattern) other "deleted" listing endpoints impose a **max 30-day window** via `deleted_at_start`/`deleted_at_end` params — this is a documented, real historical-data constraint. Beyond that specific example, general historical-data retention/limitations for the core API were **not verified** in this pass.
- **Webhook security:** covered in §11.
- **Documented unsupported operations:** based on what was retrieved, Offers appear to be read/download-only (no create/update found); Users cannot be hard-deleted (only deactivated); Tags/Sources/Stages/Referrals appear to be read-only via the endpoints found. These should be treated as **provisional** findings pending a direct confirmation pass, not certainties, since the retrieval process may not have surfaced every documented method.

---

## 13. Diji Talent Flow Mapping

| Requirement | Lever Data Available? | Entity | Endpoint | Key Fields | Webhook? | Gap/Concern |
|---|---|---|---|---|---|---|
| Client requisitions | Partial | Requisition (client identity not native) | `/requisitions` | requisitionCode, department, hiringManager, status | Not verified | No native client entity (§10); client identity would need to be encoded in a custom field or tag |
| Job vacancies | Yes | Posting | `/postings` | text, state, location, department, team, owner | Not verified | Posting↔Requisition link semantics not fully verified (§5) |
| Candidates | Yes | Contact | `/contacts/:id` | name, emails, phones, location | Y (`contactCreated/Updated`) | Contact is minimal; richer candidate data lives on Opportunity |
| Candidate pipeline/status | Yes | Opportunity + Stage + Archive Reason | `/opportunities/:id`, `/opportunities/:id/stage`, `/opportunities/:id/archived` | stage, archived, archivedAt, reason | Y (`candidateStageChange`, `candidateArchiveChange`) | Webhooks are IDs-only; needs follow-up GET |
| Candidate→job relationship | Yes | Opportunity/Application | `/opportunities/:id`, Application sub-object | posting, postingOwner | Y (`applicationCreated`) | Legacy Application GET endpoints are deprecated |
| Candidate→client relationship | Not verified / structurally indirect | (via Requisition/Posting custom field, if configured) | — | — | No | Biggest structural gap — see §10 and §14 |
| Interviews/schedule/feedback | Yes | Interview, Feedback | `/opportunities/:id/interviews`, `/opportunities/:id/feedback` | panel, interview, fields[], completedAt | Y (interview create/update/delete only; no feedback webhook found) | No webhook when feedback itself is submitted/updated — polling needed |
| Offers | Yes (read/download only, confirmed) | Offer | `/opportunities/:id/offers` | offer document download | Not verified (no offer webhook found) | No confirmed create/update via API; polling only for status changes |
| Hiring outcome | Yes | Opportunity archive + `candidateHired` event | `/opportunities/:id/archived`, disposition | archived, reason (hired/non-hired) | Y (`candidateHired`, `candidateArchiveChange`) | — |
| Recruiters | Yes | User | `/users` | name, email, accessRole | Not verified | No dedicated user-change webhook found |
| Hiring managers | Yes | Posting.hiringManager, Requisition.hiringManager | `/postings/:id`, `/requisitions/:id` | hiringManager (User id) | Not verified | — |
| Candidate documents/resumes | Yes | Files, Resumes | `/opportunities/:id/files`, `/resumes/:id/download` | file metadata + binary | No | Formats limited to docx/doc/js/jpg/png/pdf/txt |
| Candidate history | Partial | Opportunity + webhook event log (if captured historically) | — | fromStageId/toStageId, fromArchived/toArchived | Y (partial) | No confirmed dedicated "history/timeline" GET endpoint — not verified |
| Candidate reassignment | Not verified | — | — | — | — | No specific "reassignment" concept found in docs retrieved; would need direct confirmation |
| Notes | Yes | Note | `/opportunities/:id/notes` | text, author | No | No update endpoint documented (only create/list/delete) |
| Source | Yes | Sources (list) + Opportunity.sources | `/sources`, `/opportunities/:id/sources` | source label | No | Read-only reference list; assignment via PUT on opportunity |

---

## 14. Data Gaps

Based on documentation retrieved in this pass, the following would need clarification or a workaround if required by Diji Talent Flow:
- **No native Client/Customer/Account entity** — client identity is not modeled by Lever at all (§10); confirmed absent from every entity list reviewed.
- **No confirmed webhook for Offer changes, Feedback submission, Posting changes, or Requisition changes** — these require polling if real-time sync is needed.
- **No confirmed dedicated "candidate history/timeline" API** — beyond stage/archive transition data implicit in webhook payloads, a full audit trail endpoint for a single candidate's journey was not found (Audit Events endpoint exists but is described as tracking user/account provisioning and auth activity, not candidate pipeline history specifically).
- **Offer create/update via API not confirmed** — if Diji Talent Flow needs to push offer data into Lever (rather than just read it), this may not be supported; needs direct confirmation.
- **No confirmed "candidate reassignment" concept** (e.g., transferring an opportunity's owner/recruiter) — not found in the documentation retrieved.
- **Exact Posting↔Requisition linkage mechanics** not fully confirmed — matters for accurately mapping "job vacancy" to "client requisition" in Diji Talent Flow's model.

---

## 15. Questions for the Lever Administrator (Dijital Team's tenant)

These cannot be answered from public documentation alone and require someone with admin access to the actual Lever account:
1. Which custom fields exist on Requisitions and Postings in this tenant, and is any of them used to store a client/customer identifier?
2. What are the exact names/order of the configured pipeline Stages, and do they map consistently across all job postings or vary by team/department?
3. What Archive Reasons are configured (hired vs. non-hired dispositions), and do their labels map cleanly to Diji Talent Flow's desired outcome states?
4. Is there a tenant-specific convention for representing which client/company a requisition or posting belongs to (tag, custom field, department, team)?
5. Are API keys already provisioned for this tenant, and do they have `confidential:access:admin` scope granted (needed if any postings/requisitions/opportunities are marked confidential)?
6. Has this tenant configured any webhooks already, and if so, to which endpoint(s) and for which events?
7. Is Offer data actively used/populated in this tenant (compensation fields, signature workflows), or are offers handled outside Lever?
8. How is candidate reassignment (e.g., recruiter handoff) actually performed operationally in this tenant, if at all?
9. Are Requisitions actively used and 1:1 with Postings in practice, or does this tenant only use Postings without a formal Requisition/approval workflow?
10. What data retention settings or GDPR/anonymization policies (`isAnonymized`) are configured, which could affect what candidate data remains queryable over time?

---

## 16. Access Required to Start Development

- A Lever **API key** (Basic Auth) provisioned in Settings → Integrations and API → API Credentials, scoped appropriately — or an **OAuth2 client_id/client_secret** if this will be a partner-style integration rather than an internal one.
- Explicit **confidential data access** grant on the key/OAuth client if any postings/opportunities/requisitions in the tenant are marked confidential (otherwise those records will be inaccessible or filtered).
- Relevant **OAuth scopes** (if using OAuth) covering at minimum: `opportunities:read`, `postings:read`, `requisitions:read`, `interviews:read`, `feedback:read`, `offers:read` (if offers are needed), `users:read`, `webhooks:read/write` (if webhooks are to be configured programmatically), plus `offline_access` for refresh tokens.
- **Super Admin** access to the Lever account UI if webhooks need to be configured (documentation states Super Admin is required to set up webhooks via account integration settings).
- Access to the **sandbox environment** (`api.sandbox.lever.co`) for safe development/testing before touching production data, if the tenant has sandbox provisioned.
- A publicly reachable **HTTPS endpoint** (or ngrok-style tunnel for local dev) to receive webhook deliveries, plus the account's **webhook signature token** to verify HMAC signatures.

---

## 17. Recommended Next Investigation

- Do a targeted, section-by-section direct read (not a single full-page fetch) of the Postings, Requisitions, Interviews, and Offers subsections of `https://hire.lever.co/developer/documentation` to extract complete, exact field lists/enums — several of these were only partially retrievable in this pass and are flagged "not verified."
- Directly confirm whether Offers support create/update via API (this materially affects any workflow that needs to push offer data into Lever).
- Confirm the exact Requisition↔Posting linkage mechanism (field name and cardinality).
- Check for a dedicated candidate/opportunity history or timeline endpoint beyond what's inferable from webhook payloads.
- Separately (and outside the scope of this investigation): once credentials are available, perform a **live, read-only discovery pass** against Dijital Team's actual Lever tenant to answer the §15 questions empirically (actual pipeline stage names, actual custom fields in use, actual client-identification convention, actual archive reasons configured) — documentation alone cannot answer these, only inspection of the real tenant can.

---

**Caveat throughout:** none of the above assumes how any specific company (including Dijital Team) actually configures or uses their Lever instance. Every entity/field is what the public API structurally *supports*; what's actually populated, named, or used in practice in the real tenant is unverifiable from documentation and is called out explicitly in §15 and §17.
