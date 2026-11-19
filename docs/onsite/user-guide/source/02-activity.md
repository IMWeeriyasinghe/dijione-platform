# Activity

*Who can use this: everyone. On-site Admins can also open and change review cases from this page.*

**Activity** shows **every** recorded fingerprint at the site - verified, unmapped and conflict - in site-local time. It has two views:

- **Daily summary** (default) - one row per **identity-day**: one identity on one site-local day.
- **Events** - one row per individual fingerprint.

Switch views with **Daily summary** and **Events** below the freshness bar. The period and filters are kept when you switch.

## Daily summary

![Activity, Daily summary (Last 7 days)](admin_activity.png){crop=0-1000}

### Identities in the Daily summary

| Identity shown as | Meaning |
|---|---|
| A team member name with BHR ID, EMP Number and ZK ID | **Verified**: all of that person's verified ZKBioTime IDs for that day are combined into one row. |
| **ZKBioTime ID 2006** - "Raw ID, not attributed to a person" | **Unmapped**: no verified owner for that ID on that day. Only the raw ID is shown. |
| **ZKBioTime ID 3001** - "Never attributed until resolved" | **Mapping conflict**: more than one verified mapping covers the ID that day, so it is never attributed to anyone. |

### Mapping selector

The selector **All activity**, **Verified**, **Needs review**, **Unmapped** and **Mapping conflict** limits the rows. **Needs review** means unmapped **and** conflict together.

### Summary cards

Four cards sit above the table. They show totals for the period and the current filters:

| Card | Shows |
|---|---|
| **Identity-days** | All identity-days and the total number of recorded fingerprints. |
| **Verified** (orange dot) | Identity-days of verified team members, with their fingerprints. |
| **Unmapped** (yellow dot) | Identity-days of unmapped IDs. |
| **Mapping conflict** (red dot) | Identity-days of conflicting IDs. |

The cards are also **filters**:

1. Select a card, for example **Unmapped**. The table shows only unmapped identity-days, the card is highlighted, and the table returns to page 1. Your search, terminal and review filters stay as they were.
2. Select the highlighted card again, or select **Identity-days**, to return to all activity.

The highlighted card matches the active choice in the mapping selector. Screen readers announce the selected card as "pressed".

![The Unmapped card selected: the table shows unmapped identity-days only](activity_card_unmapped.png){crop=330-1050}

### Filters

| Filter | Use |
|---|---|
| **Search name, BHR ID or EMP Number** | Verified team members only. |
| **ZKBioTime ID** | Exact ID, any mapping state. |
| **Terminal** | One reader. |
| **Review status** | Not reviewed, Under review, Justification submitted, Resolved, Reopened or Needs reassessment (chapter 7). |

Active filters appear as removable chips (for example **Verified ×**) under the filter panel.

### Columns

| Column | Meaning |
|---|---|
| **Identity** | See the table above. |
| **Date** | The site-local date ("Today" for the current day). |
| **First recorded fingerprint** | Earliest fingerprint of that identity-day. |
| **Last recorded fingerprint** | Latest fingerprint; — for a single fingerprint. |
| **Recorded span** | Last minus first for two or more fingerprints; — otherwise. |
| **Punches** | Number of recorded fingerprints. |
| **Review…** / **View case** | Opens the attendance review for that identity-day (chapter 7). |

### Expanding an identity-day

Select **⌄** at the start of a row to see the supporting fingerprints.

![An expanded identity-day: each fingerprint with its position in the day](activity_daily_expanded.png){crop=560-1270}

The expanded row lists each fingerprint with its time, its position ("First recorded fingerprint · 1 of 3", "Intermediate · 2 of 3", "Last recorded fingerprint · 3 of 3") and the terminal. It also shows the review status and offers **Review…** and **Show these events in the Events view**.

## Events

![Activity, Events view](admin_activity_events.png){crop=0-960}

The Events view lists each recorded fingerprint. Its cards show **Recorded events** (all mapping states), **Verified** (attributed to a team member) and **Unmapped / needs review** (unmapped plus conflict). The cards filter the list in the same way as the Daily summary cards.

Additional filters in this view:

| Filter | Use |
|---|---|
| **Department** | Verified team members of one department. |
| **Verified team member status** | For example active or inactive team members. |
| **Hour of day** | One site-local hour (set automatically when you open an hour from the Overview). |
| **Order** | **Newest first** or oldest first. |
| **Day review flag** | Events on days with a given review flag. |

Columns: **Site-local time**, **Team member / ID**, **Terminal** (and area), **Mapping status** (Verified, Unmapped (needs review), Mapping conflict) and **Punch in day** (for example "Last recorded fingerprint (2 of 2)").

### Event details

Select **⌄** on an event to open its details.

![Event details: Fingerprint record, Identity, Device & source and Technical details](activity_event_details.png){crop=520-1430}

| Group | Fields |
|---|---|
| **Fingerprint record** | Site-local time, sequence in the day, the day's first and last recorded fingerprint, and the day's Recorded Span. |
| **Identity** | Team member, BHR ID, EMP Number and ZKBioTime ID (verified only), and the mapping status. Unmapped events show only the raw ZKBioTime ID. |
| **Device & source** | Terminal, area and the raw device state. The raw state is limited device data and is not interpreted. |
| **Technical details** (select to open) | Time zone check, event ID, source epoch and verify type, for support use. |

Buttons below the details: **Open team member profile** and **Only ZKBioTime ID … on [date]**, which filters the list to that ID and day. On-site Admins with identity permission also see an **Investigate** link for unmapped IDs.

## Walkthrough: view the fingerprints of one identity-day

1. Open **Activity**. **Daily summary** and **Last 7 days** are selected.
2. Select **Yesterday**, or choose **Custom** for an older date.
3. Type the team member's name in **Search name, BHR ID or EMP Number**.
4. Select **⌄** on the row.

Expected result: each fingerprint of that day with its sequence and terminal. Select **Show these events in the Events view** for full event details.

# Team Members

*Who can use this: everyone.*

**Team Members** lists verified team members with their recorded activity for the selected period. A ZKBioTime ID counts only inside its administrator-verified mapping period, and several IDs of one person are combined into one row.

![Team Members (Last 30 days)](admin_employees.png){crop=0-900}

## Summary cards

**Team members in view**, **With recorded activity**, **Active · Inactive** (BambooHR employment status), **Needing review** (team members with at least one review flag) and **Verified mappings** (share of listed team members with a verified mapping).

## Filters

**Search name, BHR ID or EMP Number**, **ZKBioTime ID**, **Department**, **Employment status**, **Mapping status** and **Activity in period** (for example **Activity recorded**, to hide team members without activity).

## Columns

| Column | Meaning |
|---|---|
| **Team member** | Name, ZKBioTime ID(s), BHR ID and department. Several IDs are listed together (for example "ZK 1001, 3001"). |
| **BHR ID** / **EMP Number** | BambooHR identifiers. |
| **Status** | BambooHR employment status, for example **Active**. |
| **Mapping status** | **Verified** for a team member with a verified mapping. |
| **Last activity** | The latest recorded fingerprint in the period. |
| **Active days** | Days with at least one recorded fingerprint. |
| **Events** | Recorded fingerprints in the period. |
| **Review flags** | Number of flagged days. |

## Team member profile

Select a team member to open their profile panel.

![Team member profile](employee_profile.png)

The header shows the name, BHR ID, EMP Number, department, job title, ZKBioTime ID(s), the **Verified** and employment status badges, and each mapping period (for example "1013: 2020-01-01 → open"). Choose **7 days**, **30 days** or **90 days**.

| Tab | Contents |
|---|---|
| **Overview** | Activity days, total events, average per activity day, first and latest recorded fingerprint, review flags, and an **Events per day** chart. Select a day in the chart to inspect it. |
| **Daily activity** | One entry per day with first, latest, the span and the terminals, and each fingerprint. **Open in Activity** shows the day in Activity. |
| **Review flags** | Flagged days with their reasons. |

Profile pictures come from the verified BambooHR record. If there is no picture, initials are shown. Unmapped and conflict IDs never show a picture or name.

> **Note:** The profile labels the interval between first and latest fingerprint as **Activity span**. It is the same measure as **Recorded Span** elsewhere in Diji On-site.

Close the panel with **×** or the Escape key. Use **Export report…** on the page to download team member activity (chapter 8).

# Exceptions and attendance reviews

*Who can use this: everyone can view. Only On-site Admins can open, change, resolve or reopen review cases.*

## Flags, review cases and decisions

Three different things appear on this page. Keep them apart:

| Concept | What it is | Who creates it |
|---|---|---|
| **Review flag** | An automatic prompt on a verified team-member day, for example **Single Recorded Fingerprint**. It is an observation for optional review, **not** a violation. | Diji On-site, automatically. |
| **Review case** | An administrative record to review one identity-day: a justification, an optional declared departure and a decision. | An On-site Admin. |
| **Decision** | The outcome when a case is resolved: **Justified**, **No further action** or **Not justified**, with a decision note. | An On-site Admin. |

A review case never changes fingerprint records or identity mappings, and **a resolved case is not a verified duration**.

## Review flags

| Flag | Raised when |
|---|---|
| **Single Recorded Fingerprint** | Only one fingerprint was recorded on a **completed** day. Leaving through the push-to-exit door is never recorded, so a single fingerprint is a neutral observation - not proof of a missing exit. |
| **Possible duplicate tap** | Two fingerprints within 60 seconds of each other. |
| **High activity count** | Eight or more fingerprints on one day. |
| **Inactive team member activity** | Activity for a team member who is inactive or past their termination date in BambooHR. |
| **Before-hire activity** | Activity before the BambooHR hire date. |
| **Time zone inconsistent** | The source local time does not match the site's configured time zone. |

## The Exceptions page

![Exceptions (Last 7 days)](admin_exceptions.png){crop=0-1080}

- **Category cards** - **All categories** and one card per flag with its count. Select a card to filter.
- **Filters** - **Search name, BHR ID or EMP Number**, **ZKBioTime ID**, **Department**, **Mapping status**, **Review status** and **Sort by** (for example **Newest day first**).
- **Columns** - **Date**, **Team member**, **Review flags**, **First · last recorded fingerprint**, **Fingerprints** and **Review** (the case status and **Review…**).
- **Expand (⌄)** - the reasons for each flag and the day's fingerprints.

## Review statuses

| Status on screen | Meaning |
|---|---|
| **Not reviewed** | No case exists. The flag is an observation only. |
| **Under review** | A case is open. No justification yet. |
| **Justification submitted** | A justification (and optional declaration) has been recorded. It can be updated or resolved. |
| **Resolved (duration not verified)** | An administrative decision has been recorded. |
| **Reopened** | A resolved case has been reopened. The earlier decision stays in the history. |
| **Needs reassessment** | Shown in addition to the status when the facts changed after the case was recorded: "Recorded fingerprints changed", "Identity mapping changed" or "A fingerprint is now later than the declared departure". Approved estimates are never recalculated automatically. |

![Review case lifecycle](diagram:lifecycle)

## The attendance review dialog

Select **Review…** (or **View case**) on any row in **Exceptions** or the Activity **Daily summary**. Every dialog shows:

- the identity and date;
- the reminder that fingerprints are recorded at the entry-side reader and are not a confirmed exit, presence or hours worked;
- **Recorded evidence (current)** - first and last recorded fingerprint, Recorded Span and punches;
- each fingerprint with its sequence and terminal;
- the case status, the exception type, the case number and version;
- **History**, which you can expand to see every action with who did it and when.

### Step 1: open a case (On-site Admin)

![A day with no case: Open review case](review_not_reviewed.png)

1. On a **Not reviewed** day select **Review…**.
2. Choose the **Classification** (the exception type): Single Recorded Fingerprint, Departure time query, Disputed Recorded Span, Device issue, Identity issue or Other.
3. Optionally add a note, then select **Open review case**.

Expected result: the case shows **Under review**. Opening a case that already exists does not create a duplicate.

### Step 2: submit a justification

![An open case with the Submit justification form](review_open.png)

1. Choose a **Justification**: Fingerprint not recorded, Device fault, Assigned off-site, Approved leave or duty, or Other.
2. Write an **Explanation** of at least 10 characters.
3. Optional: enter a **Declared departure** as site-local **HH:MM** on the same date, and choose its **Declaration source**: Team member statement, Manager confirmation, Security or visitor log, or Other. A source is required when you enter a declaration.
4. Optional: add an **Evidence reference**, for example a ticket or log number.
5. Select **Submit justification**.

Diji On-site checks the declared departure:

- it must be **at or after the last** recorded fingerprint, and **after the first**;
- it must be on the same date - next-day declarations are not supported;
- times that do not exist or are ambiguous because of a daylight-saving change are refused.

### How the Reviewed Estimated Interval is calculated

When a declared departure is recorded, Diji On-site calculates:

**Estimated interval = declared departure − first recorded fingerprint**

Example (synthetic): first recorded fingerprint 09:23, declared departure 17:30 (manager confirmation) gives an **Estimated interval of 8h 07m**. The dialog labels it "reviewed declaration, not a confirmed duration" and shows the **Estimate basis**, which names the first fingerprint, the declared time, the source and who recorded it. The Recorded Span is unchanged (— for a single fingerprint).

![A submitted justification with a declared departure and the Estimated interval](review_submitted.png)

### Step 3: resolve the case

In the **Resolve (administrative decision, duration not verified)** section:

1. Choose the **Outcome**: **Justified**, **No further action** or **Not justified**.
2. Write a **Decision note** of at least 10 characters.
3. Select **Resolve case**.

A declared departure is **not** required to resolve a case. For example, a Single Recorded Fingerprint with the justification **Assigned off-site** can be resolved with **No further action** and no departure time. Never invent a departure time to close a case.

While the case is **Justification submitted** you can also correct the justification with **Update justification** and **Save update**. Each change adds one history entry.

### Step 4: reopen a resolved case

![A resolved case with its decision and the Reopen option](review_resolved.png)

1. Open the resolved case.
2. In the **Reopen** section, enter the reason (at least 10 characters) and select **Reopen case**.

Expected result: the status changes to **Reopened**. The previous decision remains visible in the history, and a new justification can be submitted.

### What On-site Users see

On-site Users can open every case but cannot change it. The dialog ends with "Read-only: only an On-site Admin can change attendance reviews."

![The same case as seen by an On-site User (read-only)](review_viewer.png)

### Messages you may see

| Message | Meaning |
|---|---|
| "changed by another administrator - reload" | Someone else changed the case after you opened it. Close and reopen the dialog, then repeat your change. |
| A field message such as "explanation: …" | A required field is missing or too short, or a declared departure fails a rule above. |
| "You do not have permission to change attendance reviews." | Your account is an On-site User. |

# Reports and Excel exports

*Who can use this: everyone. Every export applies your site access on the server.*

## Exporting a report

1. On **Overview**, **Today**, **Activity**, **Team Members** or **Exceptions**, select **Export report…**. The dialog opens with the report type, period and filters of the page you are on.
2. Choose the **Report type**. A short description of the report appears below it.
3. Choose the **Date range**: **As on the page**, **Today**, **Yesterday**, **Last 7 days**, **Last 30 days** or **Custom (up to 92 days)**.
4. Set the filters the report supports. Filters that do not apply to the chosen report are not shown.
5. Select **Export to Excel**. The workbook downloads to your computer.

![Export report dialog](export_dialog.png)

If an export would be too large, Diji On-site asks you to narrow the date range or filters.

## Report catalogue

| Report type | Contents | Filters | Workbook sheets |
|---|---|---|---|
| **Daily Fingerprint Activity Summary** | One row per identity-day for verified, unmapped and conflict IDs, with the administrative review in a separate column group. | Team member, ZKBioTime ID, Mapping status, Terminal, Review status, **Detail level** | Daily Summary, Punch Detail, Case History, Summary |
| **Recorded Activity (raw events)** | Every recorded fingerprint of the chosen mapping states, with its whole-day sequence. Unverified events show the raw ZKBioTime ID only. | Team member, ZKBioTime ID, Mapping status, Department, Terminal | Recorded Events, Summary |
| **Verified Attendance** | Verified team-member days and their events only. Unmapped activity is counted in the summary but never attributed. | Team member, ZKBioTime ID, Department, Terminal, Exception category | Attendance Report, Event Detail, Summary |
| **Team Member Attendance** | One row per verified team member: activity days, recorded events, review flags and last recorded fingerprint. | Team member, ZKBioTime ID, Department | Team Members, Summary |
| **Exceptions** | Verified team-member days with review flags, their reasons and the administrative review columns. | Team member, ZKBioTime ID, Department, Exception category | Exception Report, Event Detail, Summary |
| **Overview summary (single day)** | The day's key figures, recorded events by mapping state, Earliest / Latest Recorded Fingerprint, hourly and 30-day trend. | none (one day) | Summary, Hourly Activity, 30-Day Trend |

**Detail level** (Daily Fingerprint Activity Summary only): **Summary (one row per identity-day)**, **Detailed (every fingerprint + case history)** or **Both**.

## Workbook layout

Every workbook starts with a header block: DijiOne, Diji On-site, the report title, the site, the date range, every filter used, the report type, the time zone, when it was generated (site time and UTC) and by whom. Unavailable values are shown as —.

![Daily Summary sheet, first 11 of 26 columns (the Recorded evidence group), rendered from a workbook generated with synthetic data](xlsx:daily:Daily Summary)

### Recorded evidence and Administrative review

The **Daily Summary** and **Exception Report** sheets have two column groups with different header colours:

- **Recorded evidence** - Date, Identity or Team Member Name, BHR ID, EMP Number, ZKBioTime ID(s), Mapping Status, First Recorded Fingerprint, Last Recorded Fingerprint, Recorded Span (minutes), Recorded Span, Punches, Single Recorded Fingerprint and Terminal(s).
- **Administrative review** - Classification, Review Status, Outcome, Justification, Explanation, Declared Departure (declaration), Declaration Source, Estimated Interval (minutes, reviewed estimate), Estimate Basis, Duration Verified, Reviewer, Reviewed At (UTC) and Needs Reassessment.

Keep these groups separate when you analyse a workbook: the review columns are reviewed declarations, not biometric records, and **Duration Verified** is never "yes".

### Detail sheets

- **Punch Detail** and **Recorded Events** - Local Date, Local Time, ZKBioTime ID, Mapping Status, Punch Sequence (whole day), Team Member Name, BHR ID, EMP Number, Department, Terminal, Raw State and Verify Type.
- **Event Detail** - the events behind each verified day, with their review flags.
- **Case History** - Date, Identity, Case ID, Action, From Status, To Status, Version, By, At (UTC) and Note.

### Summary sheet

![Summary sheet: report scope, definitions and totals](xlsx:daily:Summary)

The Summary sheet lists the scope, the definitions and the totals. Fingerprint totals (recorded evidence) and case totals (administrative review) are **reported separately and never added together**. Totals reconcile with the pages: for the same site, period and filters, the identity-days and fingerprints in the Daily Fingerprint Activity Summary equal the cards on the Activity page.

## Worked examples

- **Daily Fingerprint Activity Summary** - Activity, Last 7 days, **Export report…**, Detail level **Both**. Use **Daily Summary** for one row per identity-day, **Punch Detail** for every fingerprint and **Case History** for review actions.
- **Recorded Activity (raw events)** - Activity, Events view, ZKBioTime ID 2006, **Export report…**. The workbook lists every fingerprint of that unmapped ID with its raw ID only.
- **Verified Attendance** - Today, Department **Finance**, **Export report…**, report type Verified Attendance. One row per verified Finance team-member day.
- **Team Member Attendance** - Team Members, Last 30 days, **Export report…**. One row per team member with activity days and events.
- **Exceptions** - Exceptions, category **Single Recorded Fingerprint**, **Export report…**. Each flagged day with its reason and any review case.
- **Overview summary (single day)** - Overview, Yesterday, **Export report…**. The day's figures, hourly table and 30-day trend.
