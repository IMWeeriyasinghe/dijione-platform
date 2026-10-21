# People / Workforce Directory — generic workforce identity contract

**Owner:** `apps/people-api` (the sole BambooHR owner — see
`docs/platform/people-source.md`). **Status:** delivered by PR 1.1.

## Why it exists

The existing Employee contract (`GET /api/people/employees`, table
`employees`) is shaped for DijiBirthday: it holds only *Active* employees
with a usable birthday, and DijiBirthday relies on exactly that population.
Workforce consumers (attendance, utilisation, reporting) need the full
roster — Active **and** Inactive — to resolve historical identifiers such as
the BambooHR **Employee Number**.

Rather than change the Birthday-oriented model, the Workforce Directory is a
**separate, additive read model and contract**. The Employee contract, its
`employees` table, `people_sync_runs`, `people-sync-job` and the Birthday-path
BambooHR adapter are untouched.

```
BambooHR (Custom Report API, read-only)
   ↓
people-api
   ├── Employee contract  GET /api/people/employees            → DijiBirthday (unchanged)
   └── Workforce Directory GET /api/people/workforce-directory → workforce consumers
```

## Data (minimum-data DTO, CLAUDE.md rule 9)

Table `workforce_directory`, keyed on the stable BambooHR internal id:

| Field | Notes |
|---|---|
| `bamboohr_id` | Unique, stable key |
| `employee_number` | BambooHR `employeeNumber`, stored exactly as received (text, never cast). **Nullable and not unique** — blanks and duplicates are real and are reported by consumers, never resolved here |
| `display_name` | BambooHR `displayName` (already handles preferred names) |
| `department`, `job_title`, `location` | As in BambooHR. For this tenant `department` holds the client engagement / bench assignment |
| `employment_status` | `Active` / `Inactive` — authoritative on every sync |
| `hire_date`, `termination_date` | ISO dates; BambooHR's `0000-00-00` sentinel normalized to null |
| `present_in_source` | `false` once a record stops appearing in BambooHR; rows are never deleted |
| `first_synced_at`, `last_synced_at` | Sync metadata |

Never requested or stored here: birthday, address, email, phone,
compensation.

## API (internal token only)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/people/workforce-directory?status=all\|active\|inactive` | Default `all` |
| GET | `/api/people/workforce-directory/freshness` | `last_successful_sync_at` + latest run |
| GET | `/api/people/workforce-directory/sync/history?limit=` | Max 50 |
| POST | `/api/people/internal/workforce-directory/sync` | `202 {run_id, status, started}`; body requires `requested_by_application` |
| POST | `/api/people/internal/workforce-directory/scheduled-sync` | `202`; for the scheduled job |

Python consumers use `auth_client_py.WorkforceDirectoryClient`.

## Sync lifecycle (CLAUDE.md rules 10–17)

- Separate run table `workforce_sync_runs` — Workforce runs never appear in
  `/api/people/freshness` or `people_sync_runs`.
- Single-flight: an active run is returned instead of starting another.
- Asynchronous: ad-hoc and scheduled requests return `202` and run in the
  background.
- Idempotent upsert by `bamboohr_id`; status is authoritative; missing
  records get `present_in_source=false`; a failed run rolls back and keeps
  the previous directory.
- Failure notifications go through the existing best-effort `platform_notify`.
- Schedule: `people-workforce-sync-job` every 6 hours (rule 10 default) —
  added with the deployment changes (PR 1.4). Until then, sync is ad hoc.

## Mock mode

`INTEGRATIONS_MODE=mock` uses `MockBambooHRWorkforceClient`, a fixture
separate from the Birthday mock roster, covering Active, Inactive, a blank
Employee Number, a duplicated Employee Number, a leading-zero Employee
Number and a future starter.
