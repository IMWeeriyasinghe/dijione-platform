# 06: Screen-by-screen guide

[Start](00-START-HERE.md) · prev [05 External client workflow](05-EXTERNAL-CLIENT-WORKFLOW.md) · next [07 Walkthrough and UAT](07-GUIDED-WALKTHROUGH-AND-UAT.md)

Every V1 screen involved in DijiTalentFlow, in the order you would normally use them. Paths are relative to the DijiOne address (UAT: `https://dijione-uat.dijitalteam.com`). Portal paths are relative to the portal address inside the access link.

Markers: ✏️ changes data · 🔑 external access · 🔄 runs a sync · 🛡️ administration. See [00](00-START-HERE.md#actions-that-change-data-or-grant-access).

| Part | Screens |
|---|---|
| Getting in | [S1](#s1-dijione-sign-in) · [S2](#s2-dijione-home) |
| Admin Center | [S3](#s3-admin-center-dashboard) · [S4](#s4-users) · [S5](#s5-user-detail) · [S6](#s6-client-access) · [S7](#s7-roles-permissions-and-guide) · [S8](#s8-audit) |
| DijiTalentFlow (staff) | [S9](#s9-no-dijitalentflow-access) · [S10](#s10-operations-dashboard) · [S11](#s11-client-portfolios) · [S12](#s12-client-detail) · [S13](#s13-all-requests) · [S14](#s14-talent-request-detail) · [S15](#s15-candidate-pool) · [S16](#s16-candidate-detail) · [S17](#s17-applications) · [S18](#s18-interview-manager) · [S19](#s19-recruitment-postings) · [S20](#s20-client-access-links) · [S21](#s21-messages-and-documents-overview-pages) |
| Client portal | [S22](#s22-portal-access-page) · [S23](#s23-portal-no-session-page) · [S24](#s24-portal-overview) · [S25](#s25-portal-requests) · [S26](#s26-portal-request-detail) · [S27](#s27-portal-candidate-review) · [S28](#s28-portal-interviews) |

---

## Part 1: Getting in

### S1. DijiOne sign-in
| | |
|---|---|
| Path | `/` when signed out |
| Purpose | Sign in to DijiOne |
| Shows | "Welcome to DijiOne"; note that new accounts are created inactive |
| Actions | **Sign in with Microsoft** |
| Roles | Anyone with a Dijital Team Microsoft account |
| Behaviour | Redirects to Microsoft and back. An inactive account is refused with "Your account is not yet active in DijiOne… ask a platform administrator to activate it and assign access." |
| Workflow | [02 A1](02-TA-WORKFLOW.md#a1-sign-in-and-access-check), [03 B1](03-ADMIN-WORKFLOW.md#b1-giving-a-staff-member-access) |

### S2. DijiOne Home
| | |
|---|---|
| Path | `/` |
| Purpose | Starting point for every DijiOne module |
| Shows | Greeting, "Here is what needs your attention today"; module cards for modules you can use; recent activity; notifications bell in the top bar |
| Actions | Open the **DijiTalentFlow** card; user menu; notifications |
| Roles | Every active user. The DijiTalentFlow card appears only with a TalentFlow role |
| Workflow | [02 A1](02-TA-WORKFLOW.md#a1-sign-in-and-access-check) |

---

## Part 2: Admin Center (administrators only)

### S3. Admin Center dashboard
| | |
|---|---|
| Path | `/admin` |
| Shows | Total Users, Active Users, Super Admins, Platform Admins; menu: Users, Applications, Groups, Roles, Permissions, Client Access, Guide & Access Model, Audit |
| Roles | Platform Admin, Super Admin. Others see "Administration access required" |
| Workflow | [03](03-ADMIN-WORKFLOW.md) |

### S4. Users
| | |
|---|---|
| Path | `/admin/users` |
| Shows | Table: User, Platform Role, Applications, Status, Last Login |
| Actions | Search; filter by application, platform role and **Active & Inactive / Active only / Inactive only**; open a user |
| Workflow | [03 B1](03-ADMIN-WORKFLOW.md#b1-giving-a-staff-member-access) |

### S5. User detail
| | |
|---|---|
| Path | `/admin/users/<id>` |
| Shows | Name, status, platform role, one access section per module, groups, client scope by application, platform permissions, effective access, recent audit activity |
| Actions | **Activate / Deactivate** 🛡️ (immediate). **Platform Role** drop-down 🛡️ (immediate; admin roles need Super Admin). **DijiTalentFlow** section: **Enabled**, **Role**, **Client Scope** (**All Clients** or tick clients), **Save DijiTalentFlow Access** 🛡️. **Add to group…** / remove 🛡️ |
| Behaviour | The person sees changes after signing in again |
| Workflow | [03 B1](03-ADMIN-WORKFLOW.md#b1-giving-a-staff-member-access), [B3](03-ADMIN-WORKFLOW.md#b3-client-portfolio-scope), [B5](03-ADMIN-WORKFLOW.md#b5-changing-or-removing-access) |

### S6. Client Access
| | |
|---|---|
| Path | `/admin/client-access` |
| Purpose | Edit DijiTalentFlow **staff** portfolio scope in one place (not client links) |
| Shows | Each TA / Customer Success assignment, with its role |
| Actions | **All clients** checkbox or client ticks, **Save** 🛡️ |
| Workflow | [03 B3](03-ADMIN-WORKFLOW.md#b3-client-portfolio-scope) |

### S7. Roles, Permissions and Guide
| | |
|---|---|
| Path | `/admin/roles`, `/admin/permissions`, `/admin/guide` |
| Purpose | Read-only reference: roles per module, permission catalogue, the access model explained |
| Actions | None |
| Workflow | [03 B2](03-ADMIN-WORKFLOW.md#b2-roles-and-permissions) |

### S8. Audit
| | |
|---|---|
| Path | `/admin/audit` |
| Shows | Latest 200 audit events across DijiOne: When, Actor, Action, Entity, Details |
| Behaviour | DijiTalentFlow events appear once delivered (within about 5 minutes). No filters; busy reconciles can push older events out of the 200 |
| Workflow | [04 F](04-LEVER-AND-CANDIDATE-WORKFLOW.md#f-background-automation), [03 B5](03-ADMIN-WORKFLOW.md#b5-changing-or-removing-access) |

---

## Part 3: DijiTalentFlow (staff)

Menu: **Operations Dashboard**; *Talent Operations*: **Client Portfolios, All Requests, Candidate Pool, Applications, Interview Manager, Recruitment Postings, Client Access Links**. Every screen is limited to the user's client scope.

### S9. No DijiTalentFlow access
| | |
|---|---|
| Path | `/talent-flow` without a TalentFlow role |
| Shows | "No DijiTalentFlow access" and **Back to DijiOne Home** |
| Workflow | [02 A1](02-TA-WORKFLOW.md#a1-sign-in-and-access-check) |

### S10. Operations Dashboard
| | |
|---|---|
| Path | `/talent-flow/dashboard` (where `/talent-flow` lands) |
| Shows | **Recruitment data (Lever)** panel: Last synced, status (Up to date / Syncing / Last sync failed / Last sync incomplete / Not yet synced / Sync status unavailable), schedule line, "N postings need client mapping review →". Tiles: **Clients, Active Requests, Active Applications, Interviews Scheduled, Offers in Progress**. Section "Needs Attention — Pending Customer Success Review" (always empty in V1) |
| Actions | Tiles and review link navigate. **Sync now** 🔄 changes data; use only with approval |
| Roles | All TA staff |
| Workflow | [02 A2](02-TA-WORKFLOW.md#a2-daily-ta-journey), [04 F](04-LEVER-AND-CANDIDATE-WORKFLOW.md#f-background-automation) |

### S11. Client Portfolios
| | |
|---|---|
| Path | `/talent-flow/clients` |
| Shows | **Cards** or **Table**. Card: client, status, "N requests · N active", "N shared with client · N in active pipeline", latest request date. Table: Client, Total Requests, Active Requests, Shared with Client, Latest Request, Status |
| Actions | Toggle view; open a client; request counts open filtered All Requests |
| Workflow | [02 A2](02-TA-WORKFLOW.md#a2-daily-ta-journey) |

### S12. Client detail
| | |
|---|---|
| Path | `/talent-flow/clients/<id>` |
| Shows | Name, status, Client Since; the client's Talent Request cards. (Industry and Account Manager are hidden: no source yet) |
| Actions | **Back to client portfolios**; open a request |
| Workflow | [02 A2](02-TA-WORKFLOW.md#a2-daily-ta-journey) |

### S13. All Requests
| | |
|---|---|
| Path | `/talent-flow/requests` |
| Shows | Cards: title, code (`SR-…`) and client, status, stage strip, progress bar, client-facing text, "N active candidate(s)", stage |
| Actions | Search by title or code; filter by stage (9) and status (Pending review, Approved, In progress, On hold, Fulfilled, Cancelled, Rejected); open a request. No "new request" button: retired |
| Workflow | [02 A2](02-TA-WORKFLOW.md#a2-daily-ta-journey), [04 C1](04-LEVER-AND-CANDIDATE-WORKFLOW.md#c1-from-lever-posting-to-talent-request) |

### S14. Talent Request detail
| | |
|---|---|
| Path | `/talent-flow/requests/<id>` (optional `?tab=candidates`, `interviews`, `messages`, `documents`) |
| Header | Title, status, code and client, client-facing text, progress; CS and TA status badges; **Update Stage** ✏️ (stage + optional client text); **Review Request** (never shown in V1) |
| Overview tab | Description, required skills, seniority, location, engagement, target start, priority, notes; progress timeline. Mostly empty for Lever-created requests |
| Candidates tab | Table: Candidate, Stage and Status ("Synced from Lever", read only), **Client Visible** checkbox 🔑 (saves at once). **Add Candidate** ✏️ (pool candidate + starting stage) |
| Interviews tab | This request's interviews; **Schedule Interview** ✏️ (candidate, date and time, type, meeting link, **Visible to client**); status drop-down ✏️ (saves at once) |
| Messages tab | Internal messages; **Send** ✏️. Not visible to clients |
| Documents tab | **Add Document** ✏️: file name and category (CV, Contract, Requirement, Offer letter, Other). Records details only; no file is uploaded |
| Workflow | [02 A3](02-TA-WORKFLOW.md#a3-working-on-a-talent-request), [02 A4](02-TA-WORKFLOW.md#a4-scheduling-and-tracking-interviews), [05 E4](05-EXTERNAL-CLIENT-WORKFLOW.md#e4-sharing-and-withdrawing-candidates) |

### S15. Candidate Pool
| | |
|---|---|
| Path | `/talent-flow/candidates` |
| Shows | Card per candidate: name, title, availability (always "Available": no real source), up to 4 skills, number of applications |
| Actions | Search by name or title; open a candidate. No "add candidate": retired |
| Behaviour | Loads the whole pool in scope; can be slow in Production |
| Workflow | [04 D1](04-LEVER-AND-CANDIDATE-WORKFLOW.md#d1-one-candidate-many-applications) |

### S16. Candidate detail
| | |
|---|---|
| Path | `/talent-flow/candidates/<id>` |
| Shows | Name, title, email, phone, location, source, summary, skills; every application (role, client, stage, status). Staff only; personal data |
| Actions | None (read only) |
| Workflow | [04 D1](04-LEVER-AND-CANDIDATE-WORKFLOW.md#d1-one-candidate-many-applications) |

### S17. Applications
| | |
|---|---|
| Path | `/talent-flow/applications` (dashboard link adds `?status=OFFER`) |
| Shows | Table: Candidate, Request and client, Stage and Status ("Synced from Lever"), **Client Visible** |
| Actions | Search by role title; clear status chip; tick **Client Visible** 🔑; open candidate or request |
| Behaviour | Loads every application in scope (about 11,700 in Production) |
| Workflow | [05 E4](05-EXTERNAL-CLIENT-WORKFLOW.md#e4-sharing-and-withdrawing-candidates) |

### S18. Interview Manager
| | |
|---|---|
| Path | `/talent-flow/interviews` |
| Shows | Every interview by date: candidate, role, date and time, type, client, **Join meeting** link |
| Actions | Status drop-down ✏️ (Scheduled, Completed, Cancelled, Rescheduled, No show; saves at once). Schedule from a request instead |
| Workflow | [02 A4](02-TA-WORKFLOW.md#a4-scheduling-and-tracking-interviews) |

### S19. Recruitment Postings
| | |
|---|---|
| Path | `/talent-flow/postings` |
| Shows | Filters: Recent / Active, Verified, Unmapped, Needs review, All (with counts). Table: Posting, Created, Lever client tag, Resolved client, Mapping (Auto-verified, Manually verified, Manually unmapped, Needs review + reason, Unmapped), Action |
| Actions | **Verify manually** / **Change** → client → **Save** ✏️🔑; **Unmap** (confirm) ✏️🔑; **Reopen** ✏️ (all-clients staff) |
| Workflow | [04 C2](04-LEVER-AND-CANDIDATE-WORKFLOW.md#c2-posting-matching-states-and-manual-actions) |

### S20. Client Access Links
| | |
|---|---|
| Path | `/talent-flow/access-links` |
| Shows | Form "Generate a client access link"; table: Client (issued date), Contact, Link (prefix only), Status, Expires, Redeemed, Last used, Uses, Actions |
| Actions | **Generate access link** 🔑 → **Copy link** (shown once); **Extend** → date → **Save** 🔑; **Regenerate** 🔑; **Revoke** 🔑 (immediate, no confirmation) |
| Workflow | [05 E1](05-EXTERNAL-CLIENT-WORKFLOW.md#e1-access-link-lifecycle) |

### S21. Messages and Documents overview pages
| | |
|---|---|
| Path | `/talent-flow/messages`, `/talent-flow/documents` (not in the menu) |
| Shows | Requests that have messages or documents, linking to the request tab. Wording is client-oriented ("Conversations with Dijital Team"), left from an earlier design |
| Workflow | [02 A3](02-TA-WORKFLOW.md#a3-working-on-a-talent-request) |

---

## Part 4: Client portal (external client)

Menu: **Overview, Requests, Interviews, Sign out**. Everything is read only.

### S22. Portal access page
| | |
|---|---|
| Path | `/access#<link secret>` |
| Shows | "Client Talent Review Workspace", "Opening your workspace…", or "This access link is invalid or has expired" |
| Workflow | [05 E2](05-EXTERNAL-CLIENT-WORKFLOW.md#e2-what-happens-when-the-client-opens-the-link) |

### S23. Portal no-session page
| | |
|---|---|
| Path | Any portal page without a session (for example a new tab) |
| Shows | "Use the access link your Dijital Team contact sent you. If it has expired, ask them…" |

### S24. Portal Overview
| | |
|---|---|
| Path | `/` |
| Shows | "Your engagement — *client*"; Active requests, Candidates in process, Interviews this week, Offers in progress; "Your requests" |
| Workflow | [05 E3](05-EXTERNAL-CLIENT-WORKFLOW.md#e3-what-the-client-can-and-cannot-see) |

### S25. Portal Requests
| | |
|---|---|
| Path | `/requests` |
| Shows | This client's requests: title, stage, client-facing text. Empty: "No requests yet" |

### S26. Portal request detail
| | |
|---|---|
| Path | `/requests/<id>` |
| Shows | Title, stage, status text, progress, stage timeline, "Candidates shared with you (N)" with name, title, skills, stage, interview status |

### S27. Portal candidate review
| | |
|---|---|
| Path | `/candidates/<id>` |
| Shows | Name, title, stage, skills, experience summary, upcoming interview. No actions. Un-shared: "Candidate not found" |

### S28. Portal Interviews
| | |
|---|---|
| Path | `/interviews` |
| Shows | Interviews for shared candidates marked visible: status, date and time, meeting link. Empty: "No interviews scheduled" |
| Workflow | [02 A4](02-TA-WORKFLOW.md#a4-scheduling-and-tracking-interviews) |
