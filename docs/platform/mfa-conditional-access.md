# DijiOne: requiring MFA with Microsoft Entra Conditional Access

**Status: not enforced by DijiOne yet.** This runbook is for a Microsoft Entra administrator who
holds **Conditional Access Administrator** or **Security Administrator**. The operator account
used for DijiOne deployments cannot read or create Conditional Access policies (Graph answered
403), and it must not be given those roles for this. MFA counts as enforced only after the policy
below is **On** and a real interactive sign-in has been seen to require MFA.

DijiOne has no password and no OTP of its own. Sign-in is Microsoft Entra (Authorization Code +
PKCE), so MFA is an Entra decision applied to the DijiOne app registrations. No DijiOne code change
is needed.

## Facts this runbook is based on (checked 2026-11-17)

- Tenant `2abce006-6ea2-4675-b39d-33e0a54c46c7` (dijitalteam.com) has Microsoft Entra ID P1/P2
  (`AADPremiumService` enabled), so Conditional Access is available.
- Existing Conditional Access policies and the Security Defaults state could **not** be read with
  the operator account. The administrator must review them first (step 1).
- Each environment has its own single-tenant app registration for staff sign-in:

| Environment | App registration | Application (client) ID |
|---|---|---|
| DEV | `dijione-dev` | `2ea7f6b8-d3c2-4dda-b806-32549efeadb6` |
| UAT | `dijione-uat` | `f7455106-f91b-42e0-9a6a-2f3dc256727c` |
| PROD | `dijione-prod` | `98b1f056-68a2-492e-9d37-ae2e5eb0d218` |

- **Out of scope, must not be targeted:** the supplier sign-in apps
  (`dijione-birthday-supplier-dev/uat/prod`, external guests with their own controls), managed
  identities and service-to-service calls (non-interactive, unaffected by a user sign-in policy),
  Security Defaults, and every other existing Conditional Access policy.

## Steps

1. **Review what exists.** Entra admin center → Protection → Conditional Access → Policies. Note
   any policy already requiring MFA for all cloud apps. If one already covers the three apps, record
   it and go to step 4 (validation) instead of creating a duplicate. Confirm whether Security
   Defaults is on (Identity → Overview → Properties); do not change it.
2. **Identify the emergency-access accounts** (break-glass). They are excluded from this policy, as
   from every other.
3. **Create the policy in Report-only.**
   - Name: `DijiOne - require MFA`
   - Users: *All users*. Exclude: the emergency-access accounts (and the directory-synchronisation
     account if one exists).
   - Target resources → Cloud apps → *Select apps*: `dijione-dev`, `dijione-uat`, `dijione-prod`
     (search by the client IDs above). Nothing else.
   - Grant: *Grant access*, *Require multifactor authentication* (or the authentication strength
     *Multifactor authentication*).
   - Session: none.
   - Enable policy: **Report-only**.
4. **Validate in Report-only (at least one working day).** Sign-in logs → filter Application =
   `dijione-uat` (then `dijione-prod`) → each sign-in's *Report-only* tab should show
   `DijiOne - require MFA: Report-only: Failure` for single-factor sign-ins (the policy *would*
   have required MFA) and `Success` where MFA was already satisfied. No other app may appear.
5. **Turn it On**, DEV first, then UAT, then PROD (one policy covers all three; if a staged rollout
   is wanted, temporarily select only `dijione-dev`, then add the others).
6. **Interactive verification (required before MFA is reported as enforced).** In a private browser
   window, sign in to DijiOne PROD with a normal staff account that has not completed MFA in the
   session. Expected: Microsoft prompts for the second factor before returning to DijiOne. Then check
   the sign-in log entry: *Conditional Access: Success*, policy `DijiOne - require MFA` applied,
   *Authentication requirement: Multifactor authentication*.
7. **Confirm nothing else changed:** a supplier sign-in to the Birthday supplier portal still works
   as before; scheduled jobs and service calls keep running (they never sign in interactively).

## Rollback

Set the policy to **Report-only** (or Off). No DijiOne deployment is involved.
