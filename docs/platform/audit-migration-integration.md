# Audit `event_id` migration: isolated DEV release and release-line integration

Status: proposal. Nothing here changes the release line until separately approved.

## Revisions involved

| Revision | Parent | Where | Change |
|---|---|---|---|
| `o5p6q7r8s9t0` | `n4o5p6q7r8s9` | DEV database head (read 10 Nov) | AtWork DEV activation |
| `a7e1d0c4b9f2` | `o5p6q7r8s9t0` | `release/platform-audit-dev-isolated` | `audit_logs.event_id` + `uq_audit_logs_event_id` |
| `p6q7r8s9t0u1` | `o5p6q7r8s9t0` | `release/onsite-v1` (#83) | internal-employee marker, module baseline roles |
| `q7r8s9t0u1v2` | `p6q7r8s9t0u1` | PR #89 only, unmerged | same DDL as `a7e1d0c4b9f2` |

Applied today: DEV at `o5p6q7r8s9t0` (read directly). UAT and PROD run and migrate
with the image built from `2f309e0`, which contains neither `p6q7r8s9t0u1` nor
`q7r8s9t0u1v2` (inferred from image provenance; their databases were not read).

## The hazard

If both `a7e1d0c4b9f2` and `q7r8s9t0u1v2` reach the release line, any database
that runs both adds `event_id` twice and the second fails. An Alembic merge
revision joins the graph but runs neither migration's DDL conditionally, so it
does not prevent this.

## Options

1. **Recommended: one audit migration, a branch plus an empty merge.** The
   release line takes `a7e1d0c4b9f2` unchanged, alongside `p6q7r8s9t0u1`, and
   adds a merge revision (no DDL) with both as parents. `q7r8s9t0u1v2` is
   withdrawn from PR #89 before it merges. No applied or shared migration is
   edited. DEV at `a7e1d0c4b9f2` then runs only `p6q7r8s9t0u1` and the merge;
   UAT and PROD run all three once.
2. Linear re-ordering: re-parent `p6q7r8s9t0u1` onto `a7e1d0c4b9f2`. Linear
   history, but it edits a shared, merged migration. Safe only while no
   environment has applied it.
3. Conditional DDL: make `q7r8s9t0u1v2` skip when the column exists. Two
   revisions own one column, and downgrade of either can remove the other's
   column. Not recommended.

## Needs separate approval

- Changing PR #89 to drop `q7r8s9t0u1v2` and carry `a7e1d0c4b9f2` (options 1-3 all touch #89).
- Adding the merge revision to `release/onsite-v1` (option 1).
- Any edit to `p6q7r8s9t0u1` (option 2).
- Updating the head literal in `test_atwork_registration.py` on the release line.
