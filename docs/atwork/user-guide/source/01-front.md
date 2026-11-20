@@doccontrol

# About this guide

This guide explains how to use **DijiAtWork**, the DijiOne application for recording your working day and managing attendance at Dijital Team. It covers every page in the released application (DijiAtWork V1, version 0.5.0) for its three kinds of user:

- **Employee** - records their own check-in, breaks and check-out, reviews their history and requests corrections.
- **DijiAtWork Manager** - everything an employee can do, plus the **Management** area: who is working, correction decisions, reports, exports, settings and audit history.
- **DijiOne administrator** - assigns the DijiAtWork Manager role in DijiOne administration.

Chapters 1 to 6 and 12 to 14 are for everyone. Chapters 7 to 11 are for DijiAtWork Managers. Each chapter starts with a short "Who can use this" line.

> **Note:** Use the Production address for all normal work: **https://dijione.dijitalteam.com/atwork**. The DEV and UAT environments are for testing only and may contain test data.

## How the screenshots were made

All screenshots in this guide were captured from the released DijiAtWork V1 application code (0.5.0) running with **synthetic (fictional) data**. Names such as "Nimali Fernando", "Ayesha Silva", "Kasun Jayasinghe" and "Front Desk Kiosk", and all example.com addresses, are invented. No real employee, attendance record or email address appears in this guide.

Because the screenshots come from a test copy of the application:

- the footer shows "Build dev" instead of a build number and release date;
- the demonstration day is Friday 20 November 2026 in the Asia/Colombo time zone; dates, totals and times are illustrative and will differ from what you see;
- the item that signs you out is labelled **Switch persona** (see section 2.6).

The layout, labels, buttons and behaviour are the same as in Production.

## Conventions

| Convention | Meaning |
|---|---|
| **Bold text** | A label, button or menu item exactly as it appears on screen. |
| Numbered steps | A procedure to follow in order. |
| "Expected result" | What you should see after the steps. |
| Note / Important boxes | Extra information, or information you must not miss. |

# Introduction

*Who can use this: everyone.*

## What DijiAtWork is

DijiAtWork is part of **DijiOne**, the Dijital Team digital workspace. You use it to record **when you work**: you check in when you start, record your breaks, and check out when you finish. DijiAtWork keeps your personal attendance history and lets you ask Management to correct mistakes. Managers see who is working, decide correction requests and produce reports.

DijiAtWork records **operational working hours. It is not a payroll system.** It is also separate from Diji On-site (the fingerprint readers); the two do not share data.

## How access to DijiAtWork works

![How access to DijiAtWork works](diagram:access)

1. You sign in to DijiOne with your **Dijital Team Microsoft account**.
2. Every **active** DijiOne user can open DijiAtWork automatically. Nobody has to request or assign it.
3. To **record attendance**, your account must also be linked to your HR **employee record**. Most employees are linked automatically when they sign in.
4. The **Management** area is added only for people a DijiOne administrator has given the **DijiAtWork Manager** role.

## Employee and Management functions

| | Employee functions | Management functions |
|---|---|---|
| Pages | **Today**, **My Attendance**, **My Requests** | **Overview**, **Employees**, **Corrections**, **Reports**, **Audit History**, **Settings** |
| Scope | Your own attendance only | Every employee's attendance |
| Who | Every employee linked to an employee record | DijiAtWork Managers only |

## Attendance terminology

| Term | Meaning |
|---|---|
| **Session** | One period of work from check-in to check-out. You can have several sessions in a day. |
| **Work mode** | Where you work for a session: **Office**, **Remote** or **Client Site**. |
| **Break** | A pause inside a session, recorded with **Start Break** and **End Break**. |
| **Gross time** | The total time from check-in to check-out. |
| **Break time** | The total time of all breaks in the session. |
| **Net working time** | Gross time minus break time. |
| **Missed check-out threshold** | The number of hours (12 by default) after which an open session is treated as a possible missed check-out. |
| **Unverified time** | Time from a session that ran longer than the threshold. It is shown separately and is **not counted** until Management confirms the real times. |
| **Correction request** | Your request to change a recorded session. |
| **Missing session request** | Your request to add a session that was never recorded. |
| **Business time zone** | The single time zone DijiAtWork uses for every time (Asia/Colombo). |

## Attendance recording principles

- You can have **one open session at a time**. Checking in again after a check-out starts a **new session**; sessions on the same day add up.
- **Time between sessions is not counted** unless Management approves a request for it.
- **Check Out asks for confirmation and cannot be undone.** A completed session changes only through an approved correction.
- **Nobody is checked out automatically.** A session left open longer than the threshold becomes **unverified**.
- Your official record changes only when **Management approves** a request, and **nobody can approve their own request**.

# Getting started

*Who can use this: everyone.*

## Opening DijiAtWork

1. Open **https://dijione.dijitalteam.com/** in a current version of Microsoft Edge, Google Chrome, Safari or Firefox.
2. Select **Sign in with Microsoft** and sign in with your Dijital Team Microsoft account (**Microsoft Entra ID**). Follow your normal Microsoft sign-in and multi-factor prompts.
3. On DijiOne Home, select **Open** on the **DijiAtWork** card. You can also go directly to **https://dijione.dijitalteam.com/atwork**.

Expected result: DijiAtWork opens on **Today**.

![DijiOne Home with the DijiAtWork card, your role and Open](01-dijione-home.png){nav=1 crop=0-760}

The card shows your role (for example **Atwork User**) and the application status. **Idle** or **Starting…** is normal: DijiAtWork wakes up when you open it, which can take a few seconds.

## Automatic access and attendance eligibility

**You do not need to request DijiAtWork.** Every active DijiOne user receives the **DijiAtWork User** role automatically, including people who sign in for the first time.

Opening DijiAtWork and recording attendance are two different things:

| | Who | What you can do |
|---|---|---|
| **Application access** | Every active DijiOne user | Open DijiAtWork |
| **Attendance eligibility** | Employees whose Dijital Team Microsoft account is linked to their HR employee record | Check in and out, take breaks, view your history and request corrections |

Accounts that are not employees, for example a shared or service account, can open DijiAtWork but cannot record attendance. This keeps every attendance record tied to a real employee.

![An account without an employee record still sees DijiAtWork on Home](04-home-access-only-user.png){nav=1 crop=0-560}

If your account is not linked, **Today** shows **Attendance is not set up for your account** and the navigation has no attendance pages:

![Attendance is not set up for your account](05-access-only-today.png){crop=0-400}

> **Note:** If you are a Dijital Team employee and see this message, contact HR or your DijiOne administrator so your employee record can be linked. Then sign out and sign in again. You do not need a new account.

## Page layout

Every page has the same layout:

- **Navigation (left)** - the DijiAtWork pages you may use. The **Management** group appears only for DijiAtWork Managers. Select **«** (top of the navigation) to collapse it to icons.
- **Top bar** - **DijiOne Home** (back to the DijiOne workspace), the DijiOne search box, **Ask DijiOne**, notifications, your current role (for example **DijiAtWork User**) and your profile menu.
- **Page header** - the page title, a short description and page actions, for example **Request missing session**.
- **Footer (bottom of the navigation)** - the application name and version, for example *v0.5.0*.

![DijiAtWork as seen by an employee: Today, My Attendance and My Requests](03-today-not-checked-in.png){nav=1 crop=0-640}

| Navigation item | Employee | DijiAtWork Manager |
|---|---|---|
| Today | Yes | Yes |
| My Attendance | Yes | Yes |
| My Requests | Yes | Yes |
| Management → Overview | - | Yes |
| Management → Employees | - | Yes |
| Management → Corrections | - | Yes |
| Management → Reports | - | Yes |
| Management → Audit History | - | Yes |
| Management → Settings | - | Yes |

If you open a Management page without the Manager role, DijiAtWork shows **Management access required**.

![Management pages are refused to employees](21-management-access-required.png){crop=0-420}

All times are in the business time zone, stated on each page (for example "Times are shown in Asia/Colombo.").

## Collapsible navigation

1. Select **«** at the top of the navigation. The navigation collapses to icons and the page uses the extra width.
2. Point at an icon, or move to it with the keyboard, to see the page name. The current page stays highlighted.
3. Select **»** to expand it again.

DijiAtWork remembers your choice on that browser.

![The collapsed navigation shows icons only](11-sidebar-collapsed.png){nav=1 crop=0-560}

## Mobile use

On a phone or small tablet the navigation is replaced by a menu button. All employee features are available; Management pages and exports are easier on a computer.

![DijiAtWork on a phone](14-today-phone.png)

## Signing out

Open your profile menu (your initials, top right) and select the item below your name. It is currently labelled **Switch persona**, and it signs you out of DijiOne. Close the browser when using a shared computer. Sessions also expire after a period of inactivity, after which you are asked to sign in again.

![The profile menu: the item below your name signs you out](02-user-menu-sign-out.png){nav=1 crop=0-330}
