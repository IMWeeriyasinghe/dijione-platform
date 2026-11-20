# Management overview

*Who can use this: DijiAtWork Managers.*

## Who can use Management

The **Management** area is only for people with the **DijiAtWork Manager** role. A **DijiOne administrator** assigns it in DijiOne administration, to a person or through an access group. It is never given automatically. Managers keep their own employee pages as well.

> **Note:** Managers see **all employees' attendance**. There are no team-based restrictions in this release.

## The Management Overview

Open **Management → Overview**. It shows today's picture for the whole organisation.

![Management Overview](22-management-overview.png){crop=0-760}

| Area | What it shows |
|---|---|
| **Working now** | People with an open session. |
| **On break** | People on a break. |
| **Completed today** | Sessions checked out today. |
| **Pending corrections** | Requests waiting for a decision. Open **Corrections** to decide them. |
| **Today so far** | Gross, break and net time for today, with any unverified time shown separately. |
| **Currently working** | Each person, work mode and start time. **Overdue** means the session is past the missed check-out threshold. |
| **On break** | Each person on a break and since when. |
| **Attendance exceptions** | Sessions open too long. |
| **Completed sessions today** | Each completed session with its times and net time. |

## Attendance that needs attention

- **Overdue** or **Attendance exceptions** - ask the person to check out and request a correction with the real time.
- **Pending corrections** - decide them in **Corrections** (chapter 9). Managers are notified of new requests.

![A manager's notifications](23-notifications-manager.png){crop=0-560}

![Management with the navigation collapsed](36-management-collapsed.png){nav=1 crop=0-760}

# Employees and sessions

*Who can use this: DijiAtWork Managers.*

## Find an employee

Open **Employees**. The list shows people who have recorded attendance in DijiAtWork, with their email and current status (**Working**, **On break** or **Not checked in**). Use **Search by name or email** and select **Search**.

![Employees](24-management-employees.png){crop=0-420}

> **Note:** A colleague who has never checked in or made a request does not appear in this list yet.

## An employee's attendance

Select an employee to see their attendance by day, with each session's work mode, times, totals and status, for the date range you choose.

![One employee's attendance](25-employee-attendance.png)

## Incomplete and unverified sessions

Select a session to see its full details. An **open** session past the threshold is marked **unverified**: its elapsed time is shown but is not counted until a correction that confirms its real times is approved.

![An unverified open session seen by a manager](26-management-session-unverified.png){crop=0-560}

# Correction decisions

*Who can use this: DijiAtWork Managers.*

## The corrections queue

Open **Management → Corrections**. The queue shows **Pending** requests with the employee, the type (**Session correction** or **Missing session**) and when it was requested. Use **Status** to see **Approved**, **Rejected**, **Withdrawn** or **All history**.

![The corrections queue](27-corrections-queue.png){crop=0-380}

## Review a request

Open a request. It shows the employee, when it was requested, the employee's **Reason**, and a table of **Original** and **Proposed** values. Changed values are highlighted. For a missing session, Original shows "No session on record".

![A pending correction: compare Original and Proposed values](28-correction-detail.png){crop=0-520}

Check the proposed times against what you know (for example meeting records or the employee's explanation) before deciding.

## Approve a request

1. Select **Approve**.
2. Optionally add a **Note** for the employee.
3. Select **Approve** in the dialog.

![Approve dialog](29-approve-dialog.png)

Expected result: "The decision was saved." The official record changes now; the original values stay in the audit history. The request shows **Approved** with your note, and the employee is notified.

![An approved missing-session request](32-correction-approved.png){crop=0-640}

## Reject a request

1. Select **Reject**.
2. Enter the **reason**. The employee sees it.
3. Confirm.

Expected result: the request shows **Rejected**, the record is unchanged, and the employee is notified.

![Reject dialog with a reason](30-reject-dialog.png)

## Restrictions and audit

- **You cannot decide your own request.** DijiAtWork shows "This is your own request, so another manager must decide it." and offers no decision buttons.
- If the session changed after the request was made, the request is **stale**: "The session changed after this request was made. Reject it and ask the employee for a new one."
- Every decision, with who made it and when, is kept in **Audit History** (chapter 11).

![Your own request: another manager must decide it](31-own-request-restriction.png){crop=0-520}

# Reports and exports

*Who can use this: DijiAtWork Managers.*

## Open and filter a report

1. Open **Management → Reports** ("Operational working hours. These are not payroll figures.").
2. Choose **From** and **To** dates (up to 366 days) and a **Work mode**, or **All**.
3. Select **Apply**.

![Reports for 16-20 November](33-reports.png)

## Understand the totals

| Area | Shows |
|---|---|
| **Gross time / Break time / Net working time** | Totals for the period, counted time only. |
| Unverified line | Time from unverified sessions, **not included** in the totals. |
| **By work mode** | Net time per work mode. |
| **Correction requests** | Counts by status. |
| **Employee summaries** | Sessions, gross, break, net and unverified time per employee. |
| **Daily working hours** | Totals per day. |
| **Missed check-outs (over 12 hours)** | Sessions past the threshold, with how long they were open. |

## Export CSV or Excel

1. Under **Export**, choose **Employee summary**, **Sessions**, **Missed check-outs** or **Correction requests**.
2. Select **Download CSV** or **Download Excel**.

Expected result: the file downloads straight away and covers the period and work mode you selected. File names contain the report name and the time it was generated, in the business time zone, for example *DijiAtWork_Employee_Summary_Report_2026-11-20_132240.xlsx*.

## File layout

Every file has one row per employee (Employee summary) or per session (Sessions) and ends with the columns **Report**, **Reporting period from**, **Reporting period to**, **Export generated at** and **Time zone**.

![Employee Summary Report sheet, generated with synthetic data](xlsx:employee_summary:Employee Summary Report)

| Column (Sessions export) | Meaning |
|---|---|
| **Work date** | The business-time-zone date of the session. |
| **Check-in date/time / Check-out date/time** | With the time-zone offset, for example *2026-11-20T08:35:00+05:30*. |
| **Gross / Break / Net hours in period** | Decimal hours: 4.76 means 4 hours 46 minutes. |
| **Unverified** | **Yes** for a session past the threshold that has not been confirmed. |
| **Unverified hours in period (not included)** | Shown separately; never added to net hours. |
| **Corrections** | Number of approved corrections on the session. |

Excel files have a second sheet, **Export Information**, that records the report, the period, the filters, when the file was generated and the time zone.

![Export Information sheet](xlsx:sessions:Export Information){width=60}

# Settings and audit history

*Who can use this: DijiAtWork Managers.*

## Settings

Open **Management → Settings** ("DijiAtWork operational policy"), change what is needed and select **Save settings**.

![Settings](35-settings.png){crop=0-720}

| Setting | Effect |
|---|---|
| **Enabled work modes** | Which of Office, Remote and Client Site employees can choose. |
| **Business time zone** | The time zone for all times, daily totals and reports (an IANA name such as Asia/Colombo). |
| **Missed check-out threshold (hours)** | After how many hours an open session is flagged and becomes unverified (1-72; default 12). Nobody is checked out automatically. |
| **Time format** | 24-hour or 12-hour display. |
| **Default history range (days)** | How many days My Attendance shows by default (7-90). |

> **Important:** Settings apply to everyone. Changing the time zone or the threshold changes how totals and flags are calculated.

## Audit History

**Audit History** lists every attendance action and change: check-ins, breaks, check-outs, requests, decisions, corrections, exports and settings changes, with **When**, **Action**, **By** and **Employee**. Select **View** for the details, including the values before and after a change. Filter with **Action**.

![Audit History](34-audit-history.png)

## Which actions need elevated access

| Action | Needs |
|---|---|
| Record and correct your own attendance | Attendance eligibility (section 2.2) |
| Overview, Employees, Corrections, Reports, exports, Audit History and Settings | The **DijiAtWork Manager** role |
| Assign or remove the DijiAtWork Manager role | A **DijiOne administrator** |
