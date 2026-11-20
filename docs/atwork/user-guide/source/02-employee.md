# Today

*Who can use this: everyone linked to an employee record.*

**Today** is where you record your working day. The badge at the top right shows your status: **Not checked in**, **Working** or **On break**. Below it, the page shows the date, today's totals, your **Completed sessions** and an **Activity** list.

## Check in

1. Open **Today**.
2. Under **Where are you working today?** choose **Office**, **Remote** or **Client Site**.
3. Select **Check In**.

![Choose where you are working, then Check In](06-today-work-mode-selected.png){crop=0-640}

Expected result: the status changes to **Working** and "You are checked in." appears. The large timer shows your **Net working time**, with **Session elapsed** and **Break time** beside it, and the line below shows the work mode and start time. **Activity** records "Checked in · Office".

![Checked in and working](07-today-checked-in.png){crop=0-700}

## Take a break

1. Select **Start Break**. The status changes to **On break** and the break timer runs.
2. When you return, select **End Break**.

![On a break](08-today-on-break.png){crop=0-560}

Break time is subtracted from gross time to give your net working time. You cannot check out while a break is running: end the break first.

## Check out

1. Select **Check Out**.
2. Read the confirmation **End this session?**. It shows your net working time and reminds you that this cannot be undone.
3. Select **Confirm Check Out**, or **Keep Working** to cancel.

![The check-out confirmation](09-check-out-confirm.png)

Expected result: "You are checked out." The session appears under **Completed sessions** with its gross, break and net time, and the day's totals update.

![Checked out: the completed session, today's totals and the activity list](10-today-checked-out.png){crop=0-880}

## Check in again after an early or accidental check-out

1. Choose the work mode and select **Check In** again. A **new session** starts and is added to today's total.
2. The gap between the two sessions is **not counted**. If it should count, select **Request a missing session** in the notice on Today (chapter 5).

## Today's totals

| Total | Meaning |
|---|---|
| **Gross time** | All completed sessions today, from check-in to check-out. |
| **Break time** | All breaks inside those sessions. |
| **Net working time** | Gross time minus break time. |

**Completed sessions** lists each finished session. **Activity** lists every check-in, break and check-out in time order.

## If you forgot to check out

When a session has been open longer than the missed check-out threshold (12 hours by default):

- Today shows "This session has been open for over 12 hours and its time is unverified, so it is not counted in your totals.";
- the timer is labelled **Session elapsed (unverified)** with "Not counted as working time until confirmed.";
- you receive a notification (chapter 6).

![A session left open past the threshold is unverified](12-today-missed-check-out.png){crop=0-880}

1. Select **Check Out** to close the session.
2. Select **Request correction** and enter your real check-out time and a reason (chapter 5).

Expected result: when Management approves the correction, the session's hours are counted.

> **Important:** Nobody is checked out automatically. Until a correction with the real times is approved, an unverified session's time is not counted in your totals, reports or exports.

# My Attendance

*Who can use this: everyone linked to an employee record.*

**My Attendance** shows your recorded sessions, one day at a time, with each day's totals.

## Choosing the dates

1. Open **My Attendance**.
2. Choose **From** and **To** dates and select **Apply**.

Days without records are not shown. The default range covers recent weeks.

![My Attendance: days, sessions and totals](15-my-attendance.png)

## Several sessions on one day

A day can contain several sessions, for example an office morning and a client-site afternoon. Each session is listed separately with its work mode and times, and the day heading shows the sum of all sessions.

![A day with two sessions: time between sessions is not counted](diagram:day)

## How hours are calculated

- **Gross** = check-out time minus check-in time.
- **Break** = the sum of all breaks in the session.
- **Net** = gross minus break.

Example (synthetic): check-in 08:40, check-out 17:15 gives gross **8h 35m**. A lunch break 12:30-13:15 is **0h 45m**, so net is **7h 50m**.

## Session details

Select a session to see its work mode, check-in, check-out, each break, the totals and the session status. Select **Request correction** to ask for a change.

![Session details](16-session-detail.png){crop=0-420}

## Session statuses, verified and unverified time

| Status | Meaning |
|---|---|
| **Active** | The session is still open. |
| **Completed** | Checked out normally. Its time counts. |
| **Corrected** | Changed or added by an approved request. Its time counts. |
| **Unverified** | Open longer than the threshold. Its time is shown as elapsed time only and is not counted in totals, reports or exports. |

Elapsed time is simply how long a session has been open. Counted working time comes only from completed, corrected or confirmed sessions. An unverified session is counted only when Management **approves a correction that confirms its real times**; a correction that only changes the work mode does not confirm it.

# Corrections and missing sessions

*Who can use this: everyone linked to an employee record.*

## When to request a correction

| Situation | Request |
|---|---|
| A recorded check-in or check-out time is wrong | **Correction** of that session |
| The work mode is wrong | **Correction** of that session |
| A break is missing or wrong | **Correction** of that session: add, change or remove breaks |
| You forgot to check out | **Correction** with your real check-out time |
| You worked but no session was recorded | **Missing session** request |

Your official record **does not change** while a request is pending.

## Correct a session

1. Open the session (from **My Attendance**, from **Today**, or with **My Requests** → **Correct a session**) and select **Request correction**.
2. Change what is wrong: **Work mode**, **Check-in**, **Check-out**, and breaks (**Add break**, or the bin icon to remove one). Enter times in the business time zone.
3. Enter a **Reason**. Explain what happened so Management can check it.
4. Select **Submit request**.

![A correction request: a new check-out time and a reason](17-correction-form.png){crop=60-700}

Expected result: the request appears in **My Requests** as **Pending**. Managers are notified.

## Report a missing session

1. On **My Attendance** or **My Requests** select **Request missing session** (or **Request a missing session** on Today).
2. Enter the **Work mode**, **Check-in**, **Check-out**, any breaks and a **Reason**.
3. Select **Submit request**.

![A missing session request](18-missing-session-form.png){crop=0-720}

Use a missing-session request only for time with **no** session at all. To change a session that exists, request a correction.

## Follow your requests

Open **My Requests**. Each request shows its type, when you submitted it, your reason, and a table of **Original** and **Proposed** values with the changes highlighted. Use **Status** to show **All**, **Pending**, **Approved**, **Rejected** or **Withdrawn**.

![My Requests: pending, approved, rejected and withdrawn requests](19-my-requests.png){crop=0-1180}

| Status | Meaning |
|---|---|
| **Pending** | Waiting for a manager. You can still withdraw it. |
| **Approved** | Your official record has been changed. The manager's note, if any, is shown. |
| **Rejected** | Nothing changed. The manager's reason is shown; you can submit a new request with better information. |
| **Withdrawn** | You cancelled it. Nothing changed. |

![How a request changes, or does not change, the official record](diagram:lifecycle)

## Withdraw a request

Select **Withdraw** on a pending request. It is withdrawn immediately, without a confirmation step. To ask again, submit a new request.

## After a decision

- **Approved:** the session shows **Corrected** in My Attendance (or the missing session is added), totals are recalculated, and the original values stay in the audit history.
- **Rejected:** nothing changes; read the reason in **My Requests**.

You are notified of either decision. **You cannot approve your own request**, and this applies to managers too.

# Notifications

*Who can use this: everyone.*

DijiAtWork notifications appear inside DijiOne: on the **bell** in the top bar (with a count of unread items) and under **Recent activity** on DijiOne Home. DijiAtWork does not send email.

![An employee's notifications: a rejected and an approved correction](20-notifications-decisions.png){crop=0-480}

| Notification | Who receives it | When |
|---|---|---|
| **Check-out may have been missed** | You | Your session has been open longer than the threshold. |
| **Attendance correction approved** | You | A manager approved your request. |
| **Attendance correction rejected** | You | A manager rejected your request; the reason is included. |
| **Attendance correction awaiting review** | Managers | An employee submitted a request. |
| **Attendance correction withdrawn** | Managers | An employee withdrew a pending request. |
| **Attendance corrections awaiting review** | Managers | A daily reminder from 09:00 when requests have waited more than 24 hours. |

![A missed check-out notification](13-notification-missed-check-out.png){crop=0-480}

Select a notification to open the related page: the missed check-out notice opens a correction form for that session, decisions open **My Requests**, and manager notices open **Corrections**. Notifications are delivered automatically every few minutes, so a new one can take a short time to appear.
