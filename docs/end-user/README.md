# DijiOne end-user documentation

| Manual | Audience | Source | PDF |
|---|---|---|---|
| **DijiAtWork V1 User Manual**, version 2.0 (20 November 2026) | All employees; managers; DijiOne administrators | [04-diji-at-work/user-manual.md](04-diji-at-work/user-manual.md) | `pdf/DijiAtWork_V1_User_Manual.pdf` (generated, not committed) |

## Build and check

From the repository root, after `npm ci`:

```sh
node docs/end-user/tools/check-docs.mjs                  # links, images, required sections, sensitive-text scan
node docs/end-user/tools/build-pdf.mjs 04-diji-at-work   # writes docs/end-user/pdf/04-diji-at-work-user-manual.pdf
```

The Markdown is the source of truth. Generated PDFs go to `docs/end-user/pdf/`, which Git ignores. The distributable copy is named `DijiAtWork_V1_User_Manual.pdf`.

## DijiAtWork screenshots and sample exports

`04-diji-at-work/assets/screenshots/` holds 36 captures; `capture-log.tsv` lists each one's screen and role.

- **What they show:** the DijiAtWork V1 release code (commit `d877a31`, the code in Production since 19 November 2026 UTC), run locally in demo sign-in mode.
- **When:** taken on 20 November 2026.
- **Data:** fictional people (reserved `example.com` addresses) and fictional attendance only.
- **The demonstration day:** Friday 20 November 2026, 13:20, Asia/Colombo.
- **How the data was made:** records were created through the application, then their times were moved in the local database to show past days and a missed check-out.
- **Edits:** one capture, `34-audit-history.png`, is cropped to its top 1800 px; nothing else was edited.
- **Not used:** hosted DEV, UAT and Production.

`04-diji-at-work/assets/sample-exports/` holds the CSV and Excel files that **Reports → Download CSV / Download Excel** produced from the same demonstration data.

## Verification limits

- Every workflow was exercised in the running V1 code with demonstration data.
- Microsoft sign-in itself, and notification delivery timing in Production, were checked against the code and the Production deployment, not with a real user.
- The footer in the screenshots reads "Build dev"; Production shows the release build.

## Product findings recorded while writing the manual

| ID | Finding |
|---|---|
| PF-14 | The user-menu item that signs you out is labelled **Switch persona** in every environment, including Production. The manual tells users it signs them out. A UI correction is tracked separately. |
| PF-15 | On a phone, the "You are checked out…" notice on Today wraps into a narrow column next to the **Request a missing session** link. |
| PF-16 | Management → **Employees** lists only people who have recorded attendance or made a request. |
