# Common tasks

*Who can use this: everyone, except where marked Manager.*

## Start work

1. Open **Today**, choose **Office**, **Remote** or **Client Site**.
2. Select **Check In**.

## Take a break

Select **Start Break**; when you return, select **End Break**.

## Finish work

Select **Check Out**, check the net time shown, then select **Confirm Check Out**.

## Fix a check-out you forgot

1. On **Today**, select **Check Out**.
2. Select **Request correction**, enter the real check-out time and a reason, and select **Submit request**.

## Add time that was never recorded

Select **Request missing session**, enter the work mode, times and a reason, and select **Submit request**.

## See your hours for a period

Open **My Attendance**, choose **From** and **To**, and select **Apply**.

## Withdraw a request

Open **My Requests** and select **Withdraw** on the pending request.

## See who is working now (Manager)

Open **Management → Overview**.

## Decide a correction (Manager)

Open **Corrections**, open the request, compare **Original** and **Proposed**, and select **Approve** or **Reject**.

## Export hours for a period (Manager)

Open **Reports**, choose the period and work mode, select **Apply**, then choose the export and select **Download CSV** or **Download Excel**.

# Troubleshooting and FAQs

| Problem | What you see | What it generally means | What to do | Who can help |
|---|---|---|---|---|
| DijiAtWork is not on Home | No DijiAtWork card | Your DijiOne account is inactive, or you are not signed in with your Dijital Team account. | Sign out and sign in again with your Dijital Team Microsoft account. | DijiOne administrator. |
| DijiAtWork does not open | "DijiAtWork is unavailable right now" | The application is starting or briefly unavailable. | Wait a few seconds and select **Try again**, or reload the page. | IT, if it persists. |
| The card shows Idle or Starting | **Idle** / **Starting…** | DijiAtWork is waking up. | Open it; it is ready within a few seconds. | - |
| Attendance is not available | "Attendance is not set up for your account" | Your account is not linked to an employee record. | Ask for your employee record to be linked, then sign out and in again. | HR or DijiOne administrator. |
| Check In is not shown | Today shows an open session | You already have an open session. | Check out first; end any running break. | - |
| Already checked in from yesterday | Session elapsed (unverified) | You forgot to check out. | Check out, then request a correction with your real check-out time. | A manager decides. |
| Checked out by mistake | "You are checked out." | Check-out cannot be undone. | Check in again; request a missing session for the gap if it should count. | A manager decides. |
| Cannot start or end a break | No **Start Break** / **End Break** | You are not checked in, or a break is already running. | Check in first; end the running break. | - |
| Hours are missing from totals | Lower totals than expected | The session is still open or unverified. | Check out and request a correction with the real times. | A manager decides. |
| Correction rejected | **Rejected** in My Requests | The manager could not confirm it. | Read the reason and submit a new request with better information. | Your manager. |
| Cannot open Management | "Management access required" | You do not have the DijiAtWork Manager role. | Ask whether you should have it. | DijiOne administrator. |
| Cannot decide a request | No **Approve** / **Reject** buttons | It is your own request, or it is stale. | Another manager decides your own request; reject a stale one. | Another manager. |
| Export does not download | Nothing downloads | The period is longer than 366 days, or the browser blocked the download. | Shorten the period; allow downloads from DijiOne in the browser's download bar. | IT, if it persists. |
| Asked to sign in again | The DijiOne sign-in page | Your session expired (normal security timeout). | Select **Sign in with Microsoft**. Your records are not affected. | - |
| Times look wrong | Unexpected times | DijiAtWork uses the business time zone. | Read and enter times in the time zone shown on the page. | - |

> **Important:** Do not try to work around a permission message or change browser security settings. Contact your DijiOne administrator instead.

## Frequently asked questions

| Question | Answer |
|---|---|
| Do I need to ask for DijiAtWork access? | No. Every active DijiOne user has it automatically. |
| Why can I open DijiAtWork but not check in? | Your account is not linked to an employee record yet (section 2.2). |
| Can I undo a check-out? | No. Check in again, and request a missing session for the gap if needed. |
| Will DijiAtWork check me out automatically? | No. A session left open past the threshold becomes unverified until it is corrected. |
| Can I edit a session myself? | No. You request a correction and a manager decides it. |
| Can a manager approve their own correction? | No. Another manager must decide it. |
| Do managers see only their team? | No. In this release, managers see all employees. |
| Does DijiAtWork send email? | No. Notifications appear in DijiOne. |
| Is this used for payroll? | No. It records operational working hours. |
| Is DijiAtWork connected to the fingerprint readers? | No. Those belong to Diji On-site. |
| How do I become a DijiAtWork Manager? | A DijiOne administrator assigns the role. |

# Reference

## Glossary

| Term | Meaning |
|---|---|
| Attendance eligibility | Being linked to an HR employee record, which is required to record attendance. |
| Business time zone | The single time zone DijiAtWork uses for all times (Asia/Colombo). |
| Correction request | A request to change a recorded session. |
| Corrected | A session changed or added by an approved request. |
| DijiAtWork Manager | The role that adds the Management area. Assigned by a DijiOne administrator. |
| DijiAtWork User | The role every active DijiOne user receives automatically. |
| DijiOne | The Dijital Team digital workspace that hosts DijiAtWork. |
| Gross / Break / Net time | Total elapsed time / time on breaks / gross minus breaks. |
| Missed check-out threshold | Hours (default 12) after which an open session is flagged. |
| Missing session request | A request to add a session that was never recorded. |
| Session | One period of work from check-in to check-out. |
| Stale request | A request whose session changed before it was decided. |
| Unverified time | Time from a session open longer than the threshold; not counted until confirmed. |
| Work mode | Office, Remote or Client Site. |

## Role and permission matrix

| Capability | Employee | DijiAtWork Manager |
|---|---|---|
| Open DijiAtWork | Yes (every active DijiOne user) | Yes |
| Check in, breaks and check out (own) | Yes, when linked to an employee record | Yes |
| View own attendance | Yes | Yes |
| Request own corrections and missing sessions; withdraw own | Yes | Yes |
| Management Overview and Employees (everyone's attendance) | - | Yes |
| Approve or reject requests | - | Yes (never their own) |
| Reports and CSV / Excel exports | - | Yes |
| Audit History | - | Yes |
| Settings | - | Yes |

## Navigation index

| Page | Address (after https://dijione.dijitalteam.com/atwork) | Chapter |
|---|---|---|
| Today | / | 3 |
| My Attendance | /attendance | 4 |
| My Requests | /requests | 5 |
| Management Overview | /management | 7 |
| Employees | /management/employees | 8 |
| Corrections | /management/corrections | 9 |
| Reports | /management/reports | 10 |
| Audit History | /management/audit | 11 |
| Settings | /management/settings | 11 |

## Request-state reference

| From | Action | To | Who |
|---|---|---|---|
| (no request) | **Submit request** | Pending | The employee |
| Pending | **Withdraw** | Withdrawn | The employee |
| Pending | **Approve** | Approved; the session shows Corrected | Another manager |
| Pending | **Reject** (reason required) | Rejected | Another manager |

## Data interpretation and limitations

- DijiAtWork records operational working hours declared by each employee. It is not a payroll system.
- Time between sessions is not counted unless an approved request adds it.
- Unverified time is never added to totals, reports or exports until a correction confirms it.
- Managers see all employees; there is no team-based scope in this release.
- The Employees list shows only people who have recorded attendance or made a request.

## Related resources

- DijiOne Home: https://dijione.dijitalteam.com/
- DijiAtWork: https://dijione.dijitalteam.com/atwork
- For access or the Manager role, contact your DijiOne administrator. For your employee record, contact HR. For technical issues, contact IT through your usual internal channel.

## Document version history

See **Revision history** in Document control at the start of this guide.
