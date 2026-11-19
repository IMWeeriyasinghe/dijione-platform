# Understanding the data

*Who can use this: everyone.*

## Recorded fingerprints

A recorded fingerprint is one successful reading at the entry-side reader, stored with the site-local time, the ZKBioTime ID and the terminal. It shows that a finger was placed on the reader at that time. It does not show arrival intent, presence, departure or work.

## Identity-day

One identity (a verified team member, or a raw ZKBioTime ID) on one site-local day. A verified team member with two ZKBioTime IDs has **one** identity-day. Unmapped and conflict IDs each have their own identity-day per ID.

## Recorded Span: worked examples

| Fingerprints on the day | First | Last | Recorded Span |
|---|---|---|---|
| 09:29, 14:13, 15:08 | 09:29 | 15:08 | 5h 39m |
| 07:34, 09:14 | 07:34 | 09:14 | 1h 40m |
| 09:23 only | 09:23 | — | — (Single Recorded Fingerprint) |

The Recorded Span is always last minus first. Fingerprints between them do not change it. It is not time in the office: people may leave and return through the anonymous push-to-exit door without being recorded.

## Declared departure and Reviewed Estimated Interval

| | Recorded Span | Reviewed Estimated Interval |
|---|---|---|
| Based on | Two recorded fingerprints | First recorded fingerprint and a declared departure |
| Source | The fingerprint reader | An administrative declaration with a named source |
| Needs | At least two fingerprints | A review case with a declaration |
| Status | Measured between observations | Reviewed estimate, not a confirmed duration |
| Changes recorded data? | No | No |

## Review resolution

Resolving a case records an administrative decision (**Justified**, **No further action** or **Not justified**). It never adds a fingerprint, never changes the Recorded Span and never confirms hours. If fingerprints or mappings change later, the case shows **Needs reassessment**.

## Site-local date and time zone

Every date and time is in the site's time zone (for example Asia/Colombo). A fingerprint at 00:30 local time belongs to that local date, even though UTC is still the previous day. Exports show site-local times and, where marked "(UTC)", universal time.

## Data freshness

Fingerprints normally appear within a few minutes. Check the freshness bar before drawing conclusions from missing activity, especially for **Today**.

## Historical changes in mappings

When an administrator adds, ends, reassigns or corrects a mapping, every page recalculates history from the ownership periods: earlier fingerprints of that ID inside the new period become attributed, and fingerprints outside it are not. Figures for past days can therefore change after identity work. Review cases are never re-keyed to another person; they show **Needs reassessment** instead.

# Common tasks

*Who can use this: everyone, except where marked On-site Admin.*

## Find a colleague's recorded fingerprint activity today

1. Open **Today**.
2. Type the name, BHR ID or EMP Number in **Search name, BHR ID or EMP Number**.

Expected result: one row with the first and last recorded fingerprint, events and Recorded Span (see chapter 4).

## View recorded activity for a previous date

1. Open **Activity** (Daily summary).
2. Select **Yesterday**, or **Custom** and choose the date as both start and end.
3. Search for the person, or leave the search empty for everyone.

## Identify the first and latest fingerprint of a day

- For **one person**: in Activity or Today, read **First recorded fingerprint** and **Last recorded fingerprint**.
- For **the whole site**: on **Overview**, choose the single day and read **Earliest Recorded Fingerprint** and **Latest Recorded Fingerprint**. "+N tied" means several identities share the same time.

## Understand a single-fingerprint record

A row with one punch, last fingerprint — and Recorded span — is a **Single Recorded Fingerprint**. On a completed day it is flagged for optional review. It is not evidence of a missing exit, because exits are never recorded. See chapter 7.

## Filter the Daily summary to unmapped identities

1. Open **Activity**, **Daily summary**.
2. Select the **Unmapped** card. The card is highlighted and the table shows unmapped identity-days only.
3. Select the card again to return to all activity.

## View the underlying fingerprint events

1. In the Daily summary, select **⌄** on the row.
2. Select **Show these events in the Events view**.
3. Select **⌄** on an event for its details.

## Export a report for a date range

1. On the relevant page select **Export report…**.
2. Choose the **Report type** and set **Date range** to **Custom (up to 92 days)** if needed.
3. Select **Export to Excel**.

## Review an attendance exception (On-site Admin)

1. Open **Exceptions** and select **Review…** on the day.
2. Choose the **Classification** and select **Open review case**.

## Add an explanation or justification (On-site Admin)

1. Open the case (**Under review**).
2. Choose the **Justification**, write the **Explanation** and, only if a person declared one, the **Declared departure** and its **Declaration source**.
3. Select **Submit justification**.

## Resolve a review case (On-site Admin)

1. Open the case (**Justification submitted**).
2. Choose the **Outcome**, write the **Decision note** and select **Resolve case**. Do not add a departure time that nobody declared.

## Find an unmapped ZKBioTime ID (On-site Admin)

1. Open **Identity Management**, **Unmapped IDs**, or type the ID in **ZKBioTime ID** on Activity.
2. Select the ID to investigate it. Map it only with written evidence (chapter 9).

## Grant access to a new On-site User (On-site Admin)

Follow the walkthrough in chapter 11: **Access → Add person → search → Select → Confirm and grant access**.

## Check whether fingerprint data is current

Look at the freshness bar on any page. **Feed current** means data is up to date. On-site Admins can open **Site Health** for details.

# Troubleshooting and FAQs

| Problem | What you see | What it generally means | What to check | Who can help |
|---|---|---|---|---|
| Cannot access Diji On-site | "No Diji On-site access" | Your account has no On-site role. | Ask whether you should have access. | An On-site Admin (for On-site User) or a platform administrator. |
| Application tile is missing | No Diji On-site tile on DijiOne Home | No On-site role, or the role was granted moments ago. | Sign out and in again, then check with an On-site Admin. | On-site Admin. |
| Insufficient permissions | "Administrator access required" | The page is for On-site Admins. | Use the operational pages. | On-site Admin, if you need the role. |
| Employee not found | No row for a person | No fingerprint in the period, the ID is unmapped, a filter is active, or the wrong site/date is selected. | Clear filters, check the site and date, search their ZKBioTime ID in Activity with **All activity**. | On-site Admin (mapping). |
| Entra search has no results | "Search Microsoft Entra ID" returns nothing | Fewer than two characters, a typing error, or the person is a guest or disabled account (never listed). | Try the email address or UPN. | IT, if the account should exist. |
| Person is not eligible | **Not eligible** with a reason | Not matched to a BambooHR employee record, or an address linked to a different Entra account. | Read the reason. | HR (BambooHR record) or IT (account). |
| Profile picture does not appear | Initials instead of a photo | No photo in the directory or HR record, or the directory is temporarily unavailable. Unmapped IDs never show photos. | Nothing - initials are expected. | IT, to add a photo. |
| Recent fingerprints are not displayed | Latest event is old | The feed is delayed or stale. | The freshness bar; select **Refresh**. | On-site Admin (Site Health), then IT. |
| Recorded Span is unavailable | — | Only one fingerprint that day. | Expected; see chapter 13. | - |
| Identity appears as unmapped | "ZKBioTime ID ####" | No verified mapping for that day. | - | On-site Admin (Identity Management). |
| Mapping conflict is displayed | "Never attributed until resolved" | Overlapping verified mappings. | - | On-site Admin (Conflicts & history). |
| An exception cannot be submitted | A field message, or the button stays disabled | Explanation shorter than 10 characters, declared departure without a source, or a time before the last fingerprint or on the next day. | Correct the fields (chapter 7). | - |
| A review is stale | **Needs reassessment** | Fingerprints or mappings changed after the case was recorded. | Compare the snapshot and current facts in the dialog; reopen if needed. | On-site Admin. |
| A change is refused | "changed by another administrator - reload" | Someone else changed the case. | Close, reopen and repeat. | - |
| Export fails | An error in the export dialog | The range or filters produce too large a file, or the session expired. | Narrow the date range or filters; sign in again. | IT, if it persists. |
| Site Health shows delayed data | **Feed delayed** / **Feed stale** | Sync or Agent issue. | Chapter 12. | IT. |
| Totals differ from expectations | Counts look high or low | Different site, period or filters; unmapped activity counted separately; today in progress; mappings changed history. | Compare the same site, period and mapping filter. | On-site Admin. |
| Session expires | Asked to sign in again | Normal security timeout. | Sign in again. | - |

# Reference

## Glossary

| Term | Meaning |
|---|---|
| **Agent (Diji On-site Agent)** | The Windows service on site that sends fingerprints from ZKBioTime to DijiOne. |
| **BHR ID** | The BambooHR employee identifier. |
| **Classification** | The exception type of a review case. |
| **Declared departure** | A stated departure time recorded as an administrative declaration. Never a fingerprint. |
| **DijiOne** | The Dijital Team digital workspace that hosts Diji On-site. |
| **EMP Number** | The BambooHR employee number. It is not the ZKBioTime ID, even when the numbers are equal. |
| **Entra ID / Object ID** | Microsoft Entra ID is the company directory used for sign-in. The Object ID identifies each account. |
| **Identity-day** | One identity on one site-local day. |
| **Mapping** | A verified link between a ZKBioTime ID and a BambooHR team member for an ownership period. |
| **Mapping conflict** | Two or more verified mappings covering the same ID on the same day. |
| **Recorded Span** | Last minus first recorded fingerprint, when there are at least two. |
| **Review case** | An administrative record reviewing one identity-day. |
| **Review flag** | An automatic prompt for optional review. |
| **Reviewed Estimated Interval** | First recorded fingerprint to declared departure. A reviewed estimate, not a confirmed duration. |
| **Single Recorded Fingerprint** | A day with exactly one recorded fingerprint. |
| **Site-local time** | Time in the site's configured time zone. |
| **Unmapped** | No verified mapping for the ID on that day. |
| **ZKBioTime ID** | The number the biometric system uses for a fingerprint enrolment. |

## Role and permission matrix

| Permission (as shown in DijiOne administration) | On-site User | On-site Admin |
|---|---|---|
| View Dashboard | Yes | Yes |
| View Attendance | Yes | Yes |
| View Items Needing Review | Yes | Yes |
| Review Attendance Exceptions | - | Yes |
| View Site Health | - | Yes |
| View Identity Match Report | - | Yes |
| Manage Identity Mappings | - | Yes |
| Request Sync | - | Yes |
| Manage Sites | - | Yes |
| Manage On-site User access (Access page) | - | Yes |

## Navigation index

| Page | Address (after https://dijione.dijitalteam.com/onsite) | Chapter |
|---|---|---|
| Overview | / | 3 |
| Today | /today | 4 |
| Activity | /activity | 5 |
| Team Members | /employees | 6 |
| Exceptions | /exceptions | 7 |
| Identity Management | /admin/identity | 9 |
| Sites | /admin/sites | 10 |
| Access | /admin/access | 11 |
| Site Health | /admin/health | 12 |

## Review-state reference

| From | Action | To | Required |
|---|---|---|---|
| (no case) | **Open review case** | Under review | Classification |
| Under review / Reopened | **Submit justification** | Justification submitted | Justification and explanation (10+ characters); a declaration needs a source |
| Justification submitted | **Save update** | Justification submitted | As above |
| Justification submitted | **Resolve case** | Resolved (duration not verified) | Outcome and decision note (10+ characters) |
| Resolved | **Reopen case** | Reopened | Reason (10+ characters) |

## Data interpretation and limitations

- Fingerprints are entry-side observations only; exits are never recorded.
- Diji On-site does not measure presence, hours worked, lateness or attendance compliance.
- Recorded Span and Reviewed Estimated Interval are different measures and must not be added or swapped.
- Unmapped and conflict fingerprints are never attributed to a person.
- Figures for today grow during the day.
- Past figures can change after identity mappings change.

## Related resources

- DijiOne Home: https://dijione.dijitalteam.com/
- DijiOne Platform user manual (DijiOne sign-in, Home and Central Admin), where available in your internal knowledge base.
- For access requests, contact an On-site Admin. For technical issues, contact IT through your usual internal channel.

## Document version history

| Version | Date | Application version | Change |
|---|---|---|---|
| 1.0 | 20 November 2026 | 0.9.1 | First complete edition. |
