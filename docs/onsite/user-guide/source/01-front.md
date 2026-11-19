@@doccontrol

# About this guide

This guide explains how to use **Diji On-site**, the DijiOne application that shows fingerprint activity recorded at Dijital Team office sites. It covers every page in the released application (version 0.9.1) for both application roles:

- **On-site User** - views the dashboard, recorded fingerprint activity, reports and attendance review cases.
- **On-site Admin** - everything an On-site User can do, plus attendance reviews, identity management, site settings, access management and site health.

Chapters 1 to 8 and 13 to 16 are for everyone. Chapters 9 to 12 are for On-site Admins. Each chapter starts with a short "Who can use this" line.

> **Note:** Use the Production address for all normal work: **https://dijione.dijitalteam.com/onsite/**. The DEV and UAT environments are for testing only and may contain test data.

## How the screenshots were made

All screenshots in this guide were captured from the released version 0.9.1 application code running with **synthetic (fictional) data**. Names such as "Synthetic Person 13", "Alex Sample" or "Avery Sample", the site "Sample Office" and all example.com addresses are invented. No real employee, attendance record, email address or photograph appears in this guide.

Because the screenshots come from a test copy of the application:

- the footer shows "Build dev" instead of a build number and release date;
- dates, counts and times are illustrative and will differ from what you see;
- profile pictures in the Access examples are plain generated silhouettes.

The layout, labels, buttons and behaviour are the same as in Production.

## Conventions

| Convention | Meaning |
|---|---|
| **Bold text** | A label, button or menu item exactly as it appears on screen. |
| Numbered steps | A procedure to follow in order. |
| "Expected result" | What you should see after the steps. |
| — | Shown on screen where a value is unavailable, for example no Recorded Span on a day with a single fingerprint. |
| Note / Important boxes | Extra information, or information you must not miss. |

# Introduction

*Who can use this: everyone.*

## What Diji On-site is

Diji On-site is part of **DijiOne**, the Dijital Team digital workspace. It shows the fingerprint activity recorded by the biometric reader at each enabled office site, in the site's local time, and helps administrators link biometric IDs to the right team members.

Diji On-site is used by:

- team leads and operations staff who need to see recorded fingerprint activity (On-site Users);
- the administrators who keep identity mappings, reviews, site settings and access correct (On-site Admins).

Its purpose is to give a clear, honest view of **what the fingerprint reader recorded**. It does not decide whether anyone was present, late, absent or working.

## How fingerprint activity reaches Diji On-site

![How a recorded fingerprint reaches Diji On-site](diagram:flow)

1. A team member places their finger on the **entry-side fingerprint reader** outside the office door. The reader identifies them by their **ZKBioTime ID** (a number stored in the biometric system).
2. **ZKBioTime**, the biometric system on site, stores the event.
3. The **Diji On-site Agent**, a small Windows service on site, reads new events from ZKBioTime and sends them securely to DijiOne.
4. **DijiOne** stores each event and synchronises its copy every minute.
5. Diji On-site displays the events. An event is linked to a named team member **only** when an On-site Admin has verified that the ZKBioTime ID belonged to that person on that day (a **verified mapping**). Names and employee details come from **BambooHR**.

## Application users and recorded team members

Two different groups of people appear in Diji On-site:

| | Application users | Team members in recorded activity |
|---|---|---|
| Who they are | People who sign in to Diji On-site with an On-site User or On-site Admin role. | Anyone whose fingerprint was recorded at a site. |
| Where they are managed | **Access** page (On-site Admin) and DijiOne administration. | BambooHR (employee details) and **Identity Management** (mapping of ZKBioTime IDs). |
| Example | A team lead who checks the dashboard. | Every team member who used the reader. |

Most team members who use the reader do **not** have access to Diji On-site, and having access to Diji On-site does not change how your own fingerprints are shown.

## Fingerprint terminology: what the data can and cannot establish

> **Important:** The fingerprint reader is installed **outside the office entrance**. People leave through an **anonymous push-to-exit button**, which records nobody. Read this section before interpreting any figure in Diji On-site.

Because of this design:

- every recorded fingerprint is an **entry-side biometric observation** - it shows that a finger was placed on the reader at that time;
- a fingerprint never shows an identifiable **departure**, so the last fingerprint of the day is **not** an exit time;
- Diji On-site cannot confirm how long anyone was inside the office;
- Diji On-site cannot calculate hours worked or attendance compliance.

The application uses these terms consistently:

| Term | Meaning |
|---|---|
| **First Recorded Fingerprint** | The earliest fingerprint of one identity on one site-local day. |
| **Last Recorded Fingerprint** (also shown as **Latest Recorded Fingerprint**) | The latest fingerprint of that identity on that day. It is not an exit. |
| **Recorded Span** | The time between the first and the last recorded fingerprint on the same identity-day, shown only when there are **at least two** fingerprints. It is a measured interval between two observations, not time on site or hours worked. |
| **Single Recorded Fingerprint** | A day with only one fingerprint. There is no measurable Recorded Span, shown as —. |
| **Declared departure** | A time stated by a person (for example the team member or a manager) and recorded by an On-site Admin as an **administrative declaration**. It is never a fingerprint. |
| **Reviewed Estimated Interval** (on screen: **Estimated interval**) | First recorded fingerprint to declared departure, calculated by the system when an On-site Admin records a declaration. It is a reviewed estimate, **not a confirmed duration**. |

A resolved review case never turns a declared departure into a fingerprint and never confirms attendance hours. Recorded fingerprints are never changed by reviews.

![Recorded Span, Single Recorded Fingerprint and the separate Reviewed Estimated Interval](diagram:span)

# Getting started

*Who can use this: everyone.*

## Opening Diji On-site

1. Open **https://dijione.dijitalteam.com/** in a current version of Microsoft Edge, Google Chrome, Safari or Firefox.
2. Sign in with your Dijital Team Microsoft account (**Microsoft Entra ID**). Follow your normal Microsoft sign-in and multi-factor prompts.
3. On DijiOne Home, select the **Diji On-site** application. You can also go directly to **https://dijione.dijitalteam.com/onsite/**.

Expected result: the Diji On-site **Attendance overview** opens.

> **Note:** You only see Diji On-site if you hold the **On-site User** or **On-site Admin** role. If you do not, the application shows "No Diji On-site access". See *Troubleshooting* (chapter 15).

## Page layout

Every page has the same layout:

- **Navigation (left)** - the Diji On-site pages you may use. The **Admin** group appears only for On-site Admins. Select **«** (top of the navigation) to collapse it to icons.
- **Top bar** - **DijiOne Home** (back to the DijiOne workspace), the DijiOne search box, **Ask DijiOne**, notifications, your current role (for example **On-site User**) and your profile menu.
- **Page header** - the page title, a short description and page actions such as **Export report…**.
- **Footer (bottom of the navigation)** - the application name and version, for example *v0.9.1*.

![Diji On-site as seen by an On-site User: only the five operational pages are listed](viewer_overview.png){crop=0-430 nav=1}

![The same layout for an On-site Admin, with the Admin group (Identity Management, Sites, Access, Site Health)](admin_today.png){crop=0-560 nav=1}

| Navigation item | On-site User | On-site Admin |
|---|---|---|
| Overview | Yes | Yes |
| Today | Yes | Yes |
| Activity | Yes | Yes |
| Team Members | Yes | Yes |
| Exceptions | Yes (view cases) | Yes (manage cases) |
| Identity Management | - | Yes |
| Sites | - | Yes |
| Access | - | Yes |
| Site Health | - | Yes |

If you open an administration page without permission, Diji On-site shows **Administrator access required**.

![Administration pages are refused to On-site Users](viewer_admin_denied.png){crop=0-330 nav=1}

## Common controls

**Site.** The site selector (for example **Sample Office**) shows which site you are viewing. All times are in that site's local time zone, shown in the page description (for example *Asia/Colombo*). If you have access to only one enabled site it is selected automatically.

**Date range.** Most pages offer **Today**, **Yesterday**, **Last 7 days**, **Last 30 days** and **Custom**. With **Custom** you choose a start and end date; a range can be up to 92 days. **Today** uses a single date with previous and next day arrows.

**Data freshness.** A freshness bar appears below the date controls:

| Label | Meaning |
|---|---|
| **Feed current** | Data is up to date. |
| **Feed delayed** | DijiOne has not completed a sync for a few minutes, or the Agent has deliveries pending. Recent fingerprints may be missing. |
| **Feed stale** | The Diji On-site Agent has not sent a heartbeat recently. New fingerprints may not be reaching DijiOne. |
| **Source unavailable** | The attendance source could not be reached. |
| **Not yet synced** | The site has never been synchronised. |

The bar also shows when the page was updated, the last sync, the latest event received and the last Agent heartbeat. Select **Refresh** to reload. When the feed is delayed or stale, treat "no activity" with care.

**Search and filters.** Filter panels accept a name, BHR ID or EMP Number in **Search name, BHR ID or EMP Number**, and an exact biometric number in **ZKBioTime ID**. Drop-down filters (department, mapping status, review flag, terminal, review status) apply immediately. Active filters are kept in the page address, so you can bookmark or share a filtered view with someone who has the same access.

**Sorting.** Column headings with arrows can be sorted. Select once to sort, again to reverse.

**Pagination.** Below each table, **Rows per page** sets the page size and the arrows move between pages. The text on the left shows the range, for example "1-10 of 43 team members".

**Expanding rows.** Rows with a **⌄** arrow open details in place. Select the arrow again to close them.

**Help icons.** An **ⓘ** next to a label shows a short definition when you point at it or focus it.

## Mobile use

On a phone or small tablet the navigation is replaced by a menu button, and tables become cards. All features are available, but large tables and exports are easier on a computer.

![Diji On-site on a phone](mobile_overview.png){width=60}

## Signing out

Open your profile menu (your initials, top right) and sign out of DijiOne. Close the browser when using a shared computer. Sessions also expire after a period of inactivity, after which you are asked to sign in again.

# Overview dashboard

*Who can use this: everyone. On-site Admins also see **Sync now**.*

The **Attendance overview** summarises recorded activity at one site for a day or a period.

![Attendance overview (Today)](admin_overview.png){crop=0-770}

## Period and site

Choose the site and the period at the top. For **Today**, the page shows "day in progress, figures grow as activity is recorded". Some cards (Earliest and Latest Recorded Fingerprint) need a single day; for longer periods they show "select a single day".

## Key figures (cards)

| Card | What it shows |
|---|---|
| **Team members with activity** | Verified team members with at least one recorded fingerprint in the period. **Open Today** lists them. |
| **Recorded events** | All recorded fingerprints at the site, with the split, for example "47 verified · 7 needs review (1 conflict)". **Open Activity** shows them. |
| **Needing review** | Verified team-member days with a review flag. **Open Exceptions** lists them. |
| **Single Recorded Fingerprint** | Verified team members with only one fingerprint on a **completed** day. Today's single fingerprints are not counted until the day is over. |
| **Earliest Recorded Fingerprint** | The earliest fingerprint of the day at the site, with the identity. If several identities share the same time, "+N tied" is shown. For today, "May change as fingerprints are recorded". **Open in Activity** shows the event. |
| **Latest Recorded Fingerprint** | The latest fingerprint of the day so far. It is not an exit time. |
| **Identified team members** | Verified team members with activity. |
| **Feed** | The data freshness state and the latest event time. |

Earliest and Latest include **all** recorded fingerprints, also unmapped and conflict IDs; an unmapped identity is shown by its ZKBioTime ID only.

## Charts

![Activity by hour of day and Daily activity trend](admin_overview.png){crop=735-1190}

Above the charts, **All recorded**, **Verified** and **Needs review** choose which events are counted.

- **Activity by hour of day** - recorded events per site-local hour. "Busiest" names the hour with most events. Select a bar to open the hour detail panel.
- **Daily activity trend** - recorded events per day for the last **7 days** or **30 days**; the dashed line is the average per day with activity. Select a day to view it in the overview, or **open these 30 days in Activity**.

Chart colours show **identity-mapping states** in the official Dijital Team palette:

| Colour | State | Meaning |
|---|---|---|
| Orange (#F1592A) | **Verified** | The ZKBioTime ID has a verified mapping to a team member on that day. |
| Yellow (#FCB040) | **Unmapped** | No verified mapping exists for that ID on that day. |
| Red (#BF1E2E) | **Conflict** | More than one verified mapping covers the ID on that day, so it is never attributed. |

Bars use smooth colour gradients without patterns. Hover over or focus a bar to see exact counts. The colours describe identity mapping only - not performance, punctuality or compliance.

![Hour detail panel (08:00-08:59) opened from the hourly chart](overview_hour_sheet.png)

The hour panel shows the recorded events in that hour, the split between verified and needs-review events and the verified team members. Use the arrows to move between hours, or **View in Activity** for the full list. An hour with no activity says "This is not an absence record".

## Needs review and Recent activity

![Needs review and Recent activity](admin_overview.png){crop=1175-1620}

- **Needs review** lists team-member days per review category for the period (see chapter 7). Select a category to open it in **Exceptions**. Flags are prompts, not confirmed issues.
- **Recent activity** lists the latest verified team-member events. **Today's activity** and **Review queue (7 days)** are shortcuts; **All activity** opens the Activity page.

## Example: reading the overview

At 10:40 the overview shows Recorded events 54 (47 verified, 7 needs review), Earliest Recorded Fingerprint 07:31 and Latest 10:36. This means 54 fingerprints were recorded so far today; 47 belong to verified team members; 7 come from IDs without a single verified owner. It does **not** mean 47 people are in the office, or that anyone left at 10:36.

# Today

*Who can use this: everyone.*

**Today** lists every verified team member with recorded activity on one site-local day, with the first and last recorded fingerprint, Recorded Span and the number of fingerprints.

![Today](admin_today.png){crop=0-900}

## Choosing the day

Use the date box or the **‹** and **›** arrows. The summary line shows the date, whether the day is in progress, and the number of team members with recorded activity.

The **All / Needs review / No flags** switch narrows the list to rows with or without review flags.

## Filters and sorting

| Filter | Use |
|---|---|
| **Search name, BHR ID or EMP Number** | Part of a name, or an exact identifier. |
| **ZKBioTime ID** | Exact biometric ID. |
| **Department** | A BambooHR department. |
| **Mapping status** | **All verified** (default) or a narrower verified state. |
| **Review flag** | A review category (see chapter 7). |
| **Sort by** | For example **First recorded fingerprint**. You can also sort by column headings. |

## Columns

| Column | Meaning |
|---|---|
| **Team member** | Name, ZKBioTime ID (ZK), BHR ID and department. |
| **First recorded fingerprint** | Earliest fingerprint of the day. |
| **Last recorded fingerprint** | Latest fingerprint of the day; — when there is only one. |
| **Events** | Number of recorded fingerprints. |
| **Recorded span** | Last minus first, for example *1h 40m*; — for a Single Recorded Fingerprint. |
| **Terminals** | The reader(s) used, for example *Main Door*. |
| **Review** | Review flags and case status, or —. |

Select a team member to open their profile (chapter 6). Use **Export report…** to download the day (chapter 8).

## Walkthrough: find a colleague's recorded activity today

1. Open **Today**. The current site-local date is selected.
2. Type part of the colleague's name, their BHR ID or EMP Number in **Search name, BHR ID or EMP Number**.
3. Read the row: for example *First 07:34, Last 09:14, Events 2, Recorded span 1h 40m*.

Expected result: one row for the colleague. If nothing appears, see *Employee not found* in chapter 15. A row with **Events 1** and Recorded span — is a Single Recorded Fingerprint so far; later fingerprints may still be recorded today.
