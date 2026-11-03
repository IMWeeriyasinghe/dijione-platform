# Diji On-site — employee photos, pagination, lazy loading and chart drill-down

## Employee profile photos

**Source: BambooHR `photoUrl`, via people-api.** This is the approach Customer
Portal V2 already runs in production (`apps/api/app/api/v1/staff.py`
`GET /staff/{id}/photo`, verified live for 489/489 employees). Customer Portal
V2 does **not** read employee photos from Microsoft Graph: its Graph usage is
the signed-in user's own photo (MSAL, delegated) and a `User.Read.All`
directory read. Diji On-site therefore needs **no Microsoft Graph permission,
no new credential and no new secret**.

| Step | Where | What |
|---|---|---|
| Collect | people-api Workforce Directory sync | `GET /employees/directory` (BambooHR API key people-api already holds) → `photoUrl` per BambooHR id, kept only if `https://`. Best-effort: a failure never fails the sync. Stored in `workforce_directory.photo_url` (migration `0004`). |
| Publish | people-api | Directory DTO gains `has_photo` (boolean). The URL itself is never returned. |
| Serve | people-api `GET /api/people/workforce-directory/{bamboohr_id}/photo` | Internal token only. Fetches the image server-side: https-only including redirects (SSRF guard), image type sniffed, 2 MB cap, `private, max-age=86400`. 404 for none/failed; 503 + `Retry-After` when BambooHR throttles. |
| Authorize | onsite-api `GET /api/onsite/employees/{emp_code}/photo` | Requires `onsite.attendance.read` (same as the employee lists). 404 unless the Employee Code matches **exactly one** directory entry (by Employee Number) that has a photo. |
| Display | onsite-web avatar | Circular, `object-cover`, layered over the initials (initials are the loading state and the fallback; no broken-image icon). Profile header uses alt text "Profile photo of …"; list avatars are decorative because the name is beside them. |

**Identity mapping.** Attendance EmpCode → Workforce Directory Employee Number
(exact, case-sensitive — the same rule as identity matching) → that entry's
`bamboohr_id`. Ambiguous, unmatched or blank numbers get no photo. Display
names, e-mail addresses and Entra object ids are never used to guess.

**Caching and load.**
- Browser: a photo is requested only when its avatar is within 200 px of the
  viewport, only when the row reports `has_photo`, once per employee per
  session (TanStack Query, `staleTime: Infinity`, not part of the 30-second
  refresh), plus the HTTP cache (`private`, 24 h).
- onsite-api: bounded LRU (3,000 entries) — hits 24 h, "no photo" 6 h,
  throttling for `Retry-After`, other failures 2–5 min; single-flight per
  employee; at most 4 concurrent upstream photo calls per replica.
- Measured in a browser (preview, 10 rows per page): first load 4 photo
  requests (rows on screen only); 30-second refresh 0; next page 7; returning
  to page 1 0.

**Failure handling.** Missing photo, no BambooHR photo, inactive/left employee
with no photo, people-api or BambooHR unavailable, throttling, auth failure,
or no reliable identity match → the initials stay; no banner, no error.

## Server-side pagination

All lists page on the server, default **10** rows, choice of 10/20/50/100:
Today, Activity, Employees, Exceptions, Identity Match (`page`/`page_size`;
the CSV export stays complete), the hour drill-down, and an employee's daily
events. The employee profile's daily list (at most 92 days, already in the
summary response) pages in the browser.

- API defaults are now `page_size=10` (max 200). Ordering is total and stable:
  events by `(punch_time_utc, event_id)`; employee/exception sorts end in a
  stable tie-break.
- The chosen size is remembered per view in `localStorage`
  (`onsite.pageSize.<view>` — a number only, never attendance data) and carried
  in the URL (`size`).
- Changing filters, sort, period or size returns to page 1; a page left beyond
  the end (e.g. after a refresh) moves to the last valid page. Text search is
  debounced 300 ms and always runs on the full dataset server-side.
- Offset paging is used: queries are bounded by the 92-day range and indexed
  on `(site_id, site_local_date, …)`; measured deep paging (Activity page 500
  of 61k events) 0.35 s. Keyset paging can replace it if volumes grow by
  orders of magnitude.

## Lazy loading

- Employee profile: the first request returns the profile and the period's
  daily summary only (`include_events=false`); a day's raw events are fetched
  (paged) when that day is selected or expanded. Longer history only on
  choosing 90 days.
- Photos: on approach to the viewport.
- Hour drill-down: events fetched when a bar is selected, paged.
- Background refresh (30 s) refetches only the active queries, keeps previous
  data on screen (no loading flash), and keeps page, size, filters, open
  drawers and scroll position (all in the URL / component state).

## Chart drill-down (Overview)

Daily trend → select a day → every widget shows that day ("Selected day" strip
with **View all events** and **Clear selection**) → Activity by hour → select
an hour → that hour's events (sheet: side panel on desktop, full screen on
phones) → select an employee → employee profile. Escape closes only the
top-most panel; the URL keeps `from`, `to`, `hour` and `open`, so Back and
refresh restore the same view.

- Hour filter: `GET /api/onsite/activity?hour=H` keeps events with
  `start <= punch_time_utc < end`, where `[start, end)` is the site-local hour
  H converted to UTC with the site's time zone, on **every date** in the range
  (multi-day hours are labelled "combined across N days"). Drill-down totals
  equal the hourly bar (tested for every hour, single and multi-day). The
  Activity Excel export applies the same filter.
- Activity rows now carry their employee-day's `review_flags` (computed for the
  page's rows only).
- Bars are buttons (keyboard and touch); tooltips show hour, exact count and
  time zone; on narrow screens the hourly chart scrolls sideways so each bar
  stays at least 18 px wide.

## Performance (local preview, SQLite, 10,000 directory employees, 61,094 events)

| Request (10 rows) | Time |
|---|---|
| Employees, 30 days (also with search / sort / page 50 of 100-row pages) | 0.71–0.80 s |
| Activity, 30 days, page 1 / page 500 | 0.28 / 0.35 s |
| Hour drill-down | 0.30 s |
| Today | 0.26 s |
| Exceptions, 7 days | 0.35 s |
| Overview, 30-day period | 0.64–0.74 s |
| Employee profile summary (no events) | 0.26 s |
| Identity Match page | 0.28 s |

Real DEV mirror (44.9k events, 509 directory employees): 30-day employees list
0.10 s, 7-day overview 0.21 s. No change was made to the authoritative Diji
On-site Attendance database.
