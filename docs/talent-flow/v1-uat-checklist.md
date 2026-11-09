# DijiTalentFlow V1 UAT checklist

Use controlled test accounts, a non-sensitive test client and a second test
client for isolation. Do not issue links to real clients. Record the actual
result, tester and date in the last columns. A blank is not a pass.

Roles needed: TA Manager, TA Member with restricted portfolio, Customer Success,
Talent Client user, plus one external contact for each test client.

| # | Area | Steps | Expected outcome | Actual result | Tester / date |
|---|---|---|---|---|---|
| 1 | TA login and dashboard | Sign in through Entra as TA Manager; open the dashboard | Workspace loads; counts match the lists they link to; a user without a role is refused | | |
| 2 | Client portfolio | Open Client Portfolios as TA Manager, then as restricted TA Member | Manager sees all; restricted user sees and can open only assigned clients | | |
| 3 | Lever sync | Run or observe a sync; open the sync panel | Run completes as `SUCCEEDED`, or `PARTIAL` with a stated reason. Candidate totals match Lever for sampled postings. No Lever data changes | | |
| 4 | `DTC - <Client Name>` tags | Check one matching, one unknown and one untagged posting | Matching maps to that client; unknown and untagged stay unmapped and invisible to clients. TA reviews the 30 unknown tags | | |
| 5 | Talent requests | After reconcile, open the new request; update its stage; change a Lever title and reconcile | One request per verified posting; rerun makes no duplicate; TA stage is kept; Lever facts update | | |
| 6 | Candidates and applications | Compare a request's candidates and stages with Lever | Same candidates; stage and status follow Lever and are read-only; none shared by default | | |
| 7 | Sharing | Share one candidate; leave another unshared | Only the shared candidate reaches the client | | |
| 8 | Portal access | Issue a link for the test client; open it | Portal opens at the configured URL; token leaves the address bar; only that client's data appears | | |
| 9 | Client candidate review | As the client, open the request and candidate | Approved fields only: no notes, TA status, priority or internal IDs. Portal is read-only | | |
| 10 | Interviews | Schedule for a shared and an unshared candidate | Client sees only the shared candidate's interview; cancelled interviews are not counted | | |
| 11 | Withdrawal | Withdraw the shared candidate; refresh the portal; try the old address | Candidate disappears at once and direct access is refused | | |
| 12 | Notifications and audit | Perform share, review, mapping and message actions | Audit entries exist for each. Expected notifications arrive; delivery is best-effort, so check logs for `side effects undelivered` | | |
| 13 | Scheduled sync and recovery | Confirm the next two scheduled runs; on approval, stop a replica mid-run | Runs are recorded; heartbeat advances about every 30 s; a killed run is marked abandoned after about 10 minutes and the next run proceeds | | |
| 14 | Cross-client and revocation | As client A, try client B's addresses and IDs; unmap or re-tag a test posting; revoke, expire and regenerate links; test rate limiting from two networks | All refused. Re-tag removes old-client access and starts new client with nothing shared. Revoked and expired links fail and live sessions end. One client's attempts do not lock out another | | |

## Sign-off

| Role | Name | Decision | Date |
|---|---|---|---|
| TA lead | | | |
| Customer Success | | | |
| Engineering | | | |
