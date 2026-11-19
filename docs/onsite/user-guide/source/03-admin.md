# Identity Management

*Who can use this: On-site Admins.*

**Identity Management** links **ZKBioTime IDs** (the numbers the fingerprint reader uses) to **BambooHR team members**. Fingerprints are attributed to a person **only** inside an administrator-verified **ownership period** - never by matching numbers or names.

## Why verified mappings matter

| Mapping state | What Diji On-site does |
|---|---|
| **Verified** - one verified mapping covers the ID on that day | Fingerprints are shown with the team member's name, BHR ID, EMP Number and department. |
| **Unmapped** - no verified mapping covers the ID on that day | Fingerprints are stored safely and shown with the raw ZKBioTime ID only. They are never attributed to anyone. |
| **Mapping conflict** - two or more verified mappings cover the ID on that day | Fingerprints are never attributed until an administrator resolves the overlap. |

A mapping always has an **Owned from** date and an optional **Owned until** date. A ZKBioTime ID can be reassigned to another person later; each owner then has their own period, and history before and after the change stays with the right person.

Tabs: **Overview**, **Readiness**, **Unmapped IDs**, **Mappings**, **Conflicts & history** and **Import**. The **Map ZKBioTime ID** button (top right) is available on every tab.

## Overview

![Identity Management, Overview](admin_identity_overview.png){crop=0-1060}

The **Attendance ingestion** line confirms the feed state, the latest event received and the last successful sync. Cards:

| Card | Meaning |
|---|---|
| **ZKBioTime IDs observed** | Distinct biometric IDs with fingerprints in the period. These are IDs, not people. |
| **Verified IDs** | IDs covered by a verified mapping, split into fully verified (every day covered) and partly verified. |
| **Unmapped IDs** | IDs awaiting verification. |
| **Unmapped punches** | Fingerprints of unmapped IDs, stored safely, out of all punches. |
| **Verified coverage** | Share of punches in the period attributed to verified team members. |
| **Unresolved conflicts** | Conflicting days to review under **Conflicts & history**. |

The **Verified vs unmapped punches** chart shows punches per day; **Mapping coverage** shows verified and unmapped punches with the number of verified team members. **Highest-priority unmapped IDs** ranks IDs by unmapped punches - select an ID to investigate it or **Map…** to map it.

## Readiness

![Identity Management, Readiness](admin_identity_readiness.png){crop=0-1015}

**Readiness** summarises the last 30 site days: **Identified punches** (percentage), **Identified team members**, **Unmapped ZKBioTime IDs** and **Unresolved conflicts**, followed by **High-volume outstanding IDs** with their review status (for example **Awaiting Review**). These figures inform operational decisions; nothing on this tab changes data automatically.

## Unmapped IDs

![Identity Management, Unmapped IDs](admin_identity_unmapped.png){crop=0-900}

At the top of the tab:

- **Biometric ID distribution** - IDs with punches in the period, split into **Fully verified**, **Partly verified** and **Entirely unmapped**;
- **Review status** - outstanding IDs by state (for example **Awaiting Review**, **Rejected Association**, **Partly Verified**);
- **Backlog age** - outstanding IDs by the age of their oldest unmapped punch (0-7 days, 8-30 days, 31-90 days, over 90 days);
- **Recent activity** - outstanding IDs active in the last 7 days, 8-30 days ago, or not for 30+ days;
- **Search ZKBioTime ID** and **Export CSV** (downloads the list).

The list shows each unmapped ZKBioTime ID with:

- **Punches** - unmapped punches out of all punches for the ID;
- **Period** - the first to latest day with an unmapped punch;
- **Review** - the review state of the ID;
- **Hint** - for example "an EMP Number equals this ID". A hint is **never evidence** and is never applied automatically;
- **Days** and **All attendance** on wide screens;
- actions: **Map…**, **Investigate** and **Not this person…**.

### Investigate an unmapped ID

1. Select the ID or **Investigate** on its row.
2. Read the dialog: days with punches, unmapped punches, any existing ownership periods, and **Activity by day** with the mapping status and who each day is attributed to.

![Investigate dialog for ZKBioTime ID 3001 (a conflicting ID)](identity_investigate.png)

From here you can select **Map this ID…** or **Not this person…**.

### Create a verified mapping

> **Important:** Map an ID only with written evidence - for example the IT enrolment sheet or an HR confirmation - and with the correct start date. Never map an ID because a number or name looks similar.

1. Select **Map ZKBioTime ID** (or **Map…** on a row).
2. Enter the exact **ZKBioTime ID**.
3. In **Search the BambooHR Workforce Directory**, type at least two characters of the name, BHR ID or EMP Number, then select the correct team member. Nothing is pre-selected. Each result shows the BHR ID, EMP Number, status, department, hire date and any IDs already mapped to that person.
4. Enter **Owned from** (site-local date) from HR or enrolment evidence. It is never assumed from the first recorded punch. Enter **Owned until** only when the ID stopped belonging to that person.
5. Enter **Verification evidence** (at least 10 characters), for example "IT enrolment sheet 2026-11-01, confirmed by HR".
6. If warnings appear (for example the person already has another ID, or the period overlaps another mapping), tick each warning to confirm you have checked it.
7. Select **Confirm mapping**.

![The mapping form completed for a synthetic example](identity_map_filled.png)

Expected result: the mapping appears on **Mappings** with status **Verified**, and fingerprints of that ID inside the ownership period are attributed to the team member on every page.

### Record that an ID is not a person

**Not this person…** records that a given pairing is **not** the same person, so it is not proposed again. Active rejections are listed under **Conflicts & history** and can be withdrawn.

## Mappings

![Identity Management, Mappings](identity_map_after.png){crop=0-700}

**Mappings** lists verified mappings: **ZKBioTime ID**, **Team member**, **EMP Number**, **Mapping status**, **Ownership period** (for example "1 Jan - open") and **Verified** (who verified, when and the source, for example MANUAL or an import). Filter by **Exact ZKBioTime ID** or **Record status** (**Verified**, **Superseded (corrected)** or **All**). **Export CSV** downloads the list.

Row actions:

| Action | Use |
|---|---|
| **History** | The mapping record with its evidence and status. |
| **More → End ownership…** | The ID stopped belonging to this person on a date (for example the person left). Sets **Owned until**. |
| **More → Reassign ID…** | The ID now belongs to someone else from a date. Ends the current period and starts the new owner's period. |
| **More → Correct…** | The mapping was entered wrongly. Creates a corrected mapping; the original is kept as **Superseded (corrected)** for audit. |

Mappings are never deleted. Corrections and reassignments keep the full history, and historical fingerprints follow the ownership periods that were valid on each day.

## Conflicts & history

![Identity Management, Conflicts & history](admin_identity_conflicts.png){crop=0-560}

| Panel | Shows |
|---|---|
| **Ambiguous reassignment days** | Days deliberately left unmapped when an ID changed hands. |
| **Overlapping mappings** | Two verified mappings covering the same ID on the same days. Attendance on these days is not attributed. Resolve with **Correct…** or **End ownership…**. |
| **Reused ZKBioTime IDs** | IDs owned by different team members over time. |
| **Team members with several IDs** | People with more than one ID. They are counted once in every headcount. |
| **Active rejections** | Pairings recorded as **not** the same person. |
| **Recent changes** | Audit history of identity changes. |

### Resolve a mapping conflict

1. Under **Overlapping mappings**, note the ID and the two periods (for example ID 3001: Person 01 from 2020-01-01 to 2026-12-31 and Person 02 from 2026-11-01).
2. Check the evidence with HR or IT to find the correct owner for each date.
3. On **Mappings**, use **End ownership…** on the earlier mapping (for example until 2026-10-31), or **Correct…** if a mapping was wrong.
4. Return to **Conflicts & history** and confirm the overlap is gone.

## Import

![Identity Management, Import](admin_identity_import.png){crop=0-330}

Import adds several verified mappings from an **HR-approved CSV file** with the columns **site_id, zk_emp_code, bamboohr_id, valid_from, valid_to, evidence, verified_by, verified_on, source_reference**. Every row needs its own evidence.

1. Select **Choose File** and pick the CSV.
2. Select **Dry run**. Nothing is saved. The **Dry-run result** lists each line with the ZKBioTime ID, BHR ID, team member name, period and result (errors and warnings).
3. Fix any errors in the file and run the dry run again.
4. Review every warning with HR, then tick **I have reviewed every warning above with HR.**
5. Select **Apply N verified mapping(s)**. Applying is all-or-nothing: if any row fails, nothing is saved.

![Dry-run result with one warning](identity_import_dryrun.png){crop=0-620}

# Sites

*Who can use this: On-site Admins.*

![Sites](admin_sites.png){crop=0-330}

Sites are discovered automatically from the attendance source. A new site stays **Disabled** until an On-site Admin enables it. **Disabled sites are invisible everywhere else** in Diji On-site - in every page, chart and export.

| Column | Meaning |
|---|---|
| **Site** | The site code from the attendance source, for example *dev-site*. |
| **Name** | The display name used in Diji On-site, for example *Sample Office*. |
| **Time zone** | The site's IANA time zone, for example *Asia/Colombo*. All site-local dates and times use it. |
| **Last seen** | When the attendance source last reported the site. |
| **Status** | **Enabled** or **Disabled**. |

The only action on this page is **Enable** or **Disable**:

1. Find the site.
2. Select **Enable** to make it visible, or **Disable** to hide it.

Expected result: the status changes, and the site appears in (or disappears from) the site selector for all users at their next request. Disabling a site does not delete any fingerprints.

> **Note:** The site name and time zone are shown but cannot be edited on this page. Ask IT if a name or time zone is wrong; a wrong time zone affects site-local dates and every daily figure.

# Access management

*Who can use this: On-site Admins.*

**Access** decides who can use Diji On-site and with which role. Changes apply at the person's next request.

## Roles

| Capability | On-site User | On-site Admin |
|---|---|---|
| Overview, Today, Activity, Team Members, Exceptions | Yes | Yes |
| Export reports | Yes | Yes |
| View attendance review cases | Yes | Yes |
| Open, submit, resolve and reopen review cases | - | Yes |
| Identity Management (view and change mappings) | - | Yes |
| Sites (enable and disable) | - | Yes |
| Site Health and **Sync now** | - | Yes |
| Access: grant, change and remove **On-site User** | - | Yes |
| Grant or remove **On-site Admin** | - | - (Platform or Super Admins only, in DijiOne administration) |

- An On-site Admin can grant, change and remove **On-site User** access only.
- An On-site Admin **cannot** create another On-site Admin, change another On-site Admin, change a platform administrator or change their own access.
- On-site Admin assignments are managed by authorised platform-level administrators in DijiOne administration (Central Admin).
- A platform-level administrator does **not** automatically have Diji On-site permissions. They need an On-site role like anyone else.

## The Access page

![Access, People tab](access_after.png){crop=0-430}

The **People** tab lists everyone with Diji On-site access: **Person**, **Access** (role), **From** (how the access was granted, for example "Granted here · On-site User") and **Actions**. "You may grant: On-site User" confirms what you can grant.

Some rows cannot be changed, and say why:

- "You cannot change your own access."
- "Platform administrators' access is managed in Central Admin."
- Access that comes from a group or from default employee access is shown with its source and cannot be removed here.

The **Administrators** tab lists appointed access administrators. "Administrators are appointed and removed by a Super Admin in Central Admin."

![Access, Administrators tab](access_admins_tab.png){crop=0-330}

## Walkthrough: add an eligible Entra user as an On-site User

1. Open **Access** and select **Add person**.
2. In **Search Microsoft Entra ID**, type at least two characters of the person's name, email address or user principal name (UPN).
3. Read the results. Each person shows a profile photo (or initials), their email and job title, and a status badge:
   - **Has On-site User** / **Has On-site Admin** - already has access;
   - **New to DijiOne** - not yet in DijiOne; a profile is created from Microsoft Entra ID when you grant access;
   - **No access yet** - in DijiOne without Diji On-site access;
   - **Not eligible** - cannot be granted, with the reason (for example "Not matched to a BambooHR employee record, so access cannot be granted here.").
4. Select **Select** next to the right person. Unavailable people have a disabled button.

![Search results in Add person](access_add_search.png){width=70}

5. Check the identity card (photo, name, email and job title) carefully. Leave **Role** as **On-site User**. Select **Back to search** if it is the wrong person.

![Confirm the identity and role](access_add_confirm.png){width=80}

6. Select **Confirm and grant access**.

![Access granted, with the audit record](access_add_result.png){width=80}

Expected result: **Access granted** shows the person, **Access now: On-site User**, where it comes from, and the **Audit record** (record number, action, who made the change and when). "The change applies at the person's next sign-in or session refresh." Select **Done**. The person now appears on the People tab.

> **Note:** The person's Microsoft Entra **Object ID** decides who they are. If an existing DijiOne profile has the same email address but is linked to a different Entra account, the search shows the person as unavailable instead of granting access to the wrong account. Guest, disabled and ineligible accounts are never grantable. Entra details and photos are fetched by DijiOne on the server; no directory credentials reach your browser.

## Change or remove access

**Change:** select **Change** on a row, choose the **Role** and select **Save access**.

![Change access](access_change.png){width=80}

**Remove:** select **Remove**, enter a **Reason (recorded in the audit log)** and select **Remove access**. Only the role granted on this page is removed. If the person also has access from a group, Diji On-site records an application-level suspension instead, so they lose Diji On-site access while group membership elsewhere is unchanged.

![Remove access](access_remove.png){width=80}

# Site Health

*Who can use this: On-site Admins.*

![Site Health](admin_health.png){crop=0-1103}

**Site Health** shows whether fingerprints are flowing from the site into DijiOne. The page refreshes every 30 seconds.

| Section | Shows |
|---|---|
| **Last mirror sync** | When DijiOne last synchronised (normally every minute). |
| **Latest run** | The result of the latest sync, for example **SUCCEEDED**. |
| **Latest event received** | The time of the newest fingerprint received. |
| **Agent heartbeat** | When the Diji On-site Agent last reported, and its state (for example **Healthy**). |
| **Enabled sites** | Per site: feed state, latest received, Agent heartbeat, **Pending** and **Dead-letter** deliveries and the last error. Expand a row for details. |
| **Reconciliation (source vs mirror)** | Event counts per site and source epoch in the source and in DijiOne, with **In sync** or **Drift**. |
| **Recent syncs** | Requested time, trigger (**SCHEDULED** or **AD_HOC** for **Sync now**), status, and events read, new and already mirrored. |

> **Note:** The **Drift** row in the figure comes from synthetic data added directly to the test copy. In a live environment, **Drift** means the source and DijiOne hold different counts and should be investigated.

## Feed states

| State | Meaning | What to do |
|---|---|---|
| **Feed current** | Normal. | Nothing. |
| **Feed delayed** | No completed sync for a few minutes (5 by default), or the Agent has deliveries pending. | Wait a few minutes and select **Refresh**. Select **Sync now** once. |
| **Feed stale** | No Agent heartbeat recently (10 minutes by default). | Check whether the site office computer running the Agent is on and connected. If it persists, escalate to IT. |
| **Source unavailable** | The attendance source could not be reached. | Escalate to IT. |

![A stale feed as shown to all users on the Overview](feed_stale.png){crop=0-260}

## When data appears delayed

1. Open **Site Health**. Check **Agent heartbeat** and **Last mirror sync**.
2. Select **Sync now** once. A new **AD_HOC** row appears in **Recent syncs**.
3. If the sync succeeds but no new events arrive, and the heartbeat is old, the Agent or the site network is the likely cause.
4. Escalate to IT with the site, the time of the latest event received, the heartbeat time and any **Last error** text. Do not restart or change ZKBioTime, the Agent or the reader yourself.
