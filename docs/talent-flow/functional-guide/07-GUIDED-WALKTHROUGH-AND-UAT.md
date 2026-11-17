# 07: Guided walkthrough and UAT checklist

[Start](00-START-HERE.md) · prev [06 Screen-by-screen guide](06-SCREEN-BY-SCREEN-GUIDE.md)

## Part A: Before you start

- **Environment:** use **UAT** (`https://dijione-uat.dijitalteam.com`). Production holds real client and candidate data; use it only for the read-only steps.
- **You need:** an active account with a DijiTalentFlow role (TA Manager is fine). For the restricted-scope tests you also need a second test account limited to one client. Testers T1 and T2 were approved but never activated; see [03 B1](03-ADMIN-WORKFLOW.md#b1-giving-a-staff-member-access).
- **For portal tests:** a private browser window, and a UAT client agreed as the test client.
- **Steps W1–W13 only look.** Steps W14 onward change data or grant access (✏️ 🔑 🔄 🛡️). **Do them only in UAT, only with explicit approval, and record what you changed** so it can be undone (untick, revoke, cancel).
- **UAT note:** the scheduled reconcile is paused in UAT, so UAT data is as of the last reconcile. Do not click **Sync now** unless that is approved.

---

## Part B: Guided walkthrough

| Step | Open | You should see | Do | What happens next | Fits in workflow |
|---|---|---|---|---|---|
| W1 | DijiOne address | "Welcome to DijiOne" | **Sign in with Microsoft** | DijiOne Home. If refused as inactive, an administrator must activate you | [02 A1](02-TA-WORKFLOW.md#a1-sign-in-and-access-check) |
| W2 | Home | A **DijiTalentFlow** card | Note the other cards; open the bell | Notifications panel | [S2](06-SCREEN-BY-SCREEN-GUIDE.md#s2-dijione-home) |
| W3 | `/admin/users` → your user (admins only) | Active; DijiTalentFlow role and client scope | Only look; change nothing | Confirms what access you will have | [03 B1](03-ADMIN-WORKFLOW.md#b1-giving-a-staff-member-access) |
| W4 | DijiTalentFlow card | **Operations Dashboard**, the Lever panel and five tiles | Read *Last synced* and the status. **Do not click Sync now** | You know how fresh the data is | [02 A2](02-TA-WORKFLOW.md#a2-daily-ta-journey) |
| W5 | Click the **Clients** tile | **Client Portfolios** cards | Switch **Table**/**Cards**; compare counts | Count of clients matches the tile | [S11](06-SCREEN-BY-SCREEN-GUIDE.md#s11-client-portfolios) |
| W6 | Open a client with requests | Client detail and its requests | Click "N active" on a card instead, too | Filtered All Requests | [S12](06-SCREEN-BY-SCREEN-GUIDE.md#s12-client-detail) |
| W7 | Open a request | Header, progress, five tabs; Overview mostly "—" | Read the progress timeline | Normal for Lever-created requests (L5) | [02 A3](02-TA-WORKFLOW.md#a3-working-on-a-talent-request) |
| W8 | **Candidates** tab | Stage and status "Synced from Lever"; all **Hidden** | Compare two candidates with Lever | Stages match per the [mapping table](04-LEVER-AND-CANDIDATE-WORKFLOW.md#d2-lever-stage-to-dijitalentflow-stage) | [04 D1](04-LEVER-AND-CANDIDATE-WORKFLOW.md#d1-one-candidate-many-applications) |
| W9 | **Candidate Pool** → search → a candidate | Profile and all applications | Find someone with two applications | One person, many applications | [S16](06-SCREEN-BY-SCREEN-GUIDE.md#s16-candidate-detail) |
| W10 | **Applications** | Every application in scope | Search a role title | Same stage and status read-only labels | [S17](06-SCREEN-BY-SCREEN-GUIDE.md#s17-applications) |
| W11 | **Interview Manager** | Probably "No interviews scheduled" | – | Interviews appear only when TA records them | [02 A4](02-TA-WORKFLOW.md#a4-scheduling-and-tracking-interviews) |
| W12 | **Recruitment Postings** | Filter chips with counts | Open **Needs review**; read the reasons | Shows why postings are unmatched | [04 C2](04-LEVER-AND-CANDIDATE-WORKFLOW.md#c2-posting-matching-states-and-manual-actions) |
| W13 | **Client Access Links** | Existing links and their status | Only look | In Production, Access4 is listed (open item 1) | [05 E1](05-EXTERNAL-CLIENT-WORKFLOW.md#e1-access-link-lifecycle) |
| W14 ✏️ | Test request → **Update Stage** | Stage list and client text | Pick a stage, add text, **Update Stage** | Header, progress and text change; audit entry | [02 A3](02-TA-WORKFLOW.md#a3-working-on-a-talent-request) |
| W15 🔑 | Test request → Candidates | Hidden candidates | Tick **Client Visible** on one | Shows "Visible" | [05 E4](05-EXTERNAL-CLIENT-WORKFLOW.md#e4-sharing-and-withdrawing-candidates) |
| W16 🔑 | **Client Access Links** | The form | Test client, short expiry (e.g. 2 days) → **Generate** → **Copy link** | Link shown once; new Active row | [05 E1](05-EXTERNAL-CLIENT-WORKFLOW.md#e1-access-link-lifecycle) |
| W17 | Private window → paste the link | "Opening your workspace…", then Overview | Visit Requests, the request, the shared candidate, Interviews | Only that client; only the shared candidate; no email or phone | [05 E3](05-EXTERNAL-CLIENT-WORKFLOW.md#e3-what-the-client-can-and-cannot-see) |
| W18 ✏️ | Test request → Interviews → **Schedule Interview** | The form | Shared candidate, **Visible to client** ticked → save; then change status | Appears in Interview Manager and the portal | [02 A4](02-TA-WORKFLOW.md#a4-scheduling-and-tracking-interviews) |
| W19 🔑 | Untick **Client Visible** | – | Refresh the portal | Candidate gone; its address says not found | [05 E4](05-EXTERNAL-CLIENT-WORKFLOW.md#e4-sharing-and-withdrawing-candidates) |
| W20 🔑 | **Revoke** the test link | Status Revoked | Refresh the portal | Access refused | [05 E2](05-EXTERNAL-CLIENT-WORKFLOW.md#e2-what-happens-when-the-client-opens-the-link) |
| W21 | `/admin/audit` (admins) | Latest events | Find your W14–W20 actions (wait about 5 minutes) | Each change was recorded | [S8](06-SCREEN-BY-SCREEN-GUIDE.md#s8-audit) |

**Clean-up after W14–W20:** set the stage back, untick visibility, set the interview to Cancelled, and confirm the link is Revoked.

### If a screen is empty or an action is unavailable

| What you see | Why | What to do |
|---|---|---|
| "Your account is not yet active" | First sign-in, or deactivated | Ask an administrator ([03 B1](03-ADMIN-WORKFLOW.md#b1-giving-a-staff-member-access)) |
| No DijiTalentFlow card / "No DijiTalentFlow access" | No role, or a role change not yet picked up | Get a role; sign out and in |
| Fewer clients than expected | Your scope is limited to specific clients | Check scope in the Admin Center |
| "Administration access required" | Not a Platform Admin | Expected for non-admins |
| A client has no requests | No posting with a valid tag for it | See [Recruitment Postings](06-SCREEN-BY-SCREEN-GUIDE.md#s19-recruitment-postings) |
| "Sync status unavailable" | Services waking up | Wait a minute and reload |
| Pending Customer Success review is empty | Always empty in V1 (L9) | Nothing to do |
| No interviews | None recorded in DijiTalentFlow | Expected (L7) |
| Review Request / new request / add candidate buttons missing | Retired or unused in V1 | Expected |
| Portal: "invalid or has expired" | Expired, revoked or mistyped link | Regenerate or extend (staff) |
| Portal asks for the link in a new tab | Sessions are per tab (L17) | Open the link again |
| Slow Candidate Pool or Applications | Whole list loads (L11) | Wait; use search |

---

## Part C: UAT checklist

Record **PASS**, **FAIL** or **BLOCKED** and a note. "Changes?" marks tests that need approval in UAT.

### U1. Login and access control
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-01 | Sign in as an active TA user | Home shows DijiTalentFlow | No | | |
| UAT-02 | Sign in with a new account | Refused: not yet active | Creates inactive account | | |
| UAT-03 | Admin activates it, assigns TA Member, all clients; user signs in again | Workspace opens | 🛡️ | | |
| UAT-04 | User with no TalentFlow role opens `/talent-flow` | "No DijiTalentFlow access" | No | | |
| UAT-05 | Restrict a user to one client; sign in again | Only that client everywhere | 🛡️ | | |
| UAT-06 | Restricted user opens another client's request address | Not found | No | | |
| UAT-07 | Deactivate a user; check before and after their next sign-in | Refused at next sign-in; note any delay | 🛡️ | | |
| UAT-08 | Non-admin opens `/admin` | "Administration access required" | No | | |

### U2. Dashboard and navigation
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-09 | Open the Operations Dashboard | Lever panel with a recent Last synced; five tiles | No | | |
| UAT-10 | Click each tile | Lands on the matching list; counts agree | No | | |
| UAT-11 | Use every menu entry | Each screen loads | No | | |

### U3. Client Portfolios
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-12 | Cards and Table views | Same clients and counts | No | | |
| UAT-13 | Open a client | Only that client's requests | No | | |

### U4. Job postings and client mapping
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-14 | Check one tagged, one unknown-tag and one untagged posting | Matched; Needs review (unknown client); Unmapped | No | | |
| UAT-15 | Verify manually an unmapped test posting, then reconcile | Request created for that client, all hidden | ✏️ 🔄 | | |
| UAT-16 | Unmap it | Request no longer visible to the client; next sync does not re-verify | ✏️ 🔑 | | |
| UAT-17 | Reopen it | Back to Unmapped | ✏️ | | |
| UAT-18 | Confirm nothing changed in Lever | Lever unchanged | No | | |

### U5. Talent Requests
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-19 | Search and filter All Requests | Results match | No | | |
| UAT-20 | Each verified posting has exactly one request | No duplicates | No | | |
| UAT-21 | Update Stage with custom client text | Header and portal show it; survives the next reconcile | ✏️ | | |

### U6. Candidates and applications
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-22 | Compare a request's candidates with Lever | Same people; none shared by default | No | | |
| UAT-23 | A person in two roles | One pool record, two applications | No | | |
| UAT-24 | Add Candidate twice for the same person | Second attempt refused | ✏️ | | |

### U7. Screening and stage changes
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-25 | Application stage and status | Read only, "Synced from Lever" | No | | |
| UAT-26 | Confirm the provisional stage mappings | Business agrees with the D2 table | No | | |
| UAT-27 | Archived candidate (Hired, Withdrew, other) | Hired, Withdrawn, Rejected | No | | |

### U8. Candidate visibility restrictions
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-28 | Share one candidate, leave another hidden | Only the shared one in the portal | 🔑 | | |
| UAT-29 | Portal candidate page | No email, phone, notes, scores, TA status | No | | |
| UAT-30 | Untick a shared candidate | Gone at once; address refused | 🔑 | | |

### U9. External access-link management
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-31 | Generate a link | Shown once; Active row; no email sent | 🔑 | | |
| UAT-32 | Extend | Same link works; new date | 🔑 | | |
| UAT-33 | Regenerate | Old link refused; new link works | 🔑 | | |
| UAT-34 | Revoke | Portal refused at the next page | 🔑 | | |
| UAT-35 | Restricted user's client list | Only their clients | No | | |

### U10. Client portal access
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-36 | Open a valid link | Overview; secret removed from the address bar | No | | |
| UAT-37 | Made-up or altered link | "Invalid or has expired" | No | | |
| UAT-38 | Client A tries client B's request number | Not found | No | | |
| UAT-39 | Open the portal in a new tab | Asks for the link | No | | |
| UAT-40 | Stay over 45 minutes | Session renews while the link is valid | No | | |
| UAT-41 | Look for feedback or upload actions | None (read only) | No | | |

### U11. Interviews and other V1 workflows
| ID | Test | Expected result | Changes? | Result | Notes |
|---|---|---|---|---|---|
| UAT-42 | Schedule for a shared and an unshared candidate | Client sees only the shared one | ✏️ | | |
| UAT-43 | Untick Visible to client when scheduling | Not shown in the portal | ✏️ | | |
| UAT-44 | Change interview status | Saved at once; portal shows it | ✏️ | | |
| UAT-45 | Add a message and a document | Staff only; nothing in the portal | ✏️ | | |
| UAT-46 | Audit shows the test actions | Entries within about 5 minutes | No | | |

### Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| Application owner | | | |
| TA representative | | | |
