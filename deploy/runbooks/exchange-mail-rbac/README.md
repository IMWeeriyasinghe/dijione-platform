# platform-api — Exchange RBAC for Applications (Mail.Send)

Lets DijiOne `platform-api` send access notifications **as `appassistant@dijitalteam.com`
only** ("Diji Apps Notify"). It uses Exchange Online RBAC for Applications, and the grant is
made separately for each environment. Design background: `docs/platform/email-architecture.md`,
`docs/platform/email-notifications.md`.

| File | Changes anything? | Purpose |
|---|---|---|
| `platform-api-mail-rbac.config.ps1` | no | Identities, mailbox and scope name (dot-sourced) |
| `verify-platform-api-mail-rbac.ps1` | **no** (read-only) | Preflight and post-grant verification |
| `grant-platform-api-mail-rbac.ps1` | **yes**, needs owner approval per environment | Idempotent grant; supports `-WhatIf` |

## What is granted, and what is not

- **One Exchange service principal per environment**, pointing at that environment's
  platform-api **system-assigned** managed identity. It is never the shared
  `id-dijione-<env>` user-assigned identity. `DefaultAzureCredential` picks the system
  identity because platform-api sets no `AZURE_CLIENT_ID`. The DEV directory reader
  already proves this: it uses the same credential, and its Graph roles exist only on the
  system identity.
- **The existing management scope `DijiApps-AppAssistant-Mailbox-Scope`**, with filter
  `PrimarySmtpAddress -eq 'appassistant@dijitalteam.com'`. Exchange Online refuses a second
  scope with an identical filter, so every sender of this mailbox (DijiBirthday,
  CustomerPortalV2, Zapier and platform-api) references this one scope. Rule 21a still holds:
  each service has its own identity and its own role assignment. These scripts never create,
  edit or remove the scope.
- **One role assignment per environment, `DijiOnePlatform-<Env>-MailSend`**, with role
  `Application Mail.Send` limited to that scope.
- **Not granted:** a Microsoft Graph `Mail.Send` application permission (tenant-wide),
  `Application Mail.ReadWrite`, an Application Access Policy, a client secret, or a new
  mailbox.

| Env | platform-api system identity | AppId | Exchange SP display name |
|---|---|---|---|
| Dev | `6b26bb56-0759-4760-a0b7-4a5f20620d52` | `7ed96daa-05a4-47a1-a52c-8cf43ca39e09` | `DijiOnePlatform-Dev-API-MI` |
| Uat | `fa7d3bb3-12dc-4f88-98b0-9593d6d312c6` | `579f1c99-7efb-4ca0-8d67-9015a71d2157` | `DijiOnePlatform-Uat-API-MI` |
| Prod | `b6c6caa0-0ae5-4a4b-9f17-f25a482a85a0` | `26320838-423a-4aeb-b88b-8acc18b0724f` | `DijiOnePlatform-Prod-API-MI` |

Graph app roles on all three identities, verified read-only on 2026-11-21: `User.Read.All` and
`GroupMember.Read.All` only. None of them has Mail.Send.

## Administrator prerequisites

- PowerShell 7+ with `Install-Module ExchangeOnlineManagement` (3.x), then run `Connect-ExchangeOnline`.
- **To verify:** any Exchange role that can read RBAC, for example *View-Only Organization Management*.
- **To grant:** *Organization Management*, or any role group that holds **Role Management**.
- **The verify script also needs** the Azure CLI signed in (`az login`) as a user who can read
  service principals. Exchange can't see Entra Graph app roles, so the script checks separately
  that no tenant-wide Graph `Mail.*` permission exists, which would bypass the mailbox scope.
- No Entra permission change and no Azure change is needed for this step.

## Procedure, one environment at a time (DEV first)

```powershell
cd deploy/runbooks/exchange-mail-rbac
# 1. Read-only preflight. Before the grant this reports "NOT authorized", which is expected; send the output for review.
./verify-platform-api-mail-rbac.ps1 -Environment Dev -NegativeMailbox <another real mailbox>
# 2. Dry run: shows exactly which objects would be created.
./grant-platform-api-mail-rbac.ps1 -Environment Dev -WhatIf
# 3. Grant. This step needs explicit owner approval.
./grant-platform-api-mail-rbac.ps1 -Environment Dev
# 4. Verify. Must end "RESULT: ... authorized to send as appassistant@dijitalteam.com only." (exit 0)
./verify-platform-api-mail-rbac.ps1 -Environment Dev -NegativeMailbox <another real mailbox>
```

Running the grant again is safe: existing objects are reported, not recreated. The script
stops and changes nothing if an existing scope, service principal or assignment differs
from what is expected, if the identity already holds any other
assignment, or if more than one Exchange service principal exists for the AppId. Graph can take up to about an hour to honour a new grant, so a
`403` on the first send is expected to be temporary. Only enable `MAIL_TRANSPORT=graph`
after step 4 passes.

## Rollback

- **Fastest:** turn delivery off in the app by removing `MAIL_TRANSPORT`, `MAIL_POLICY` and
  `MAIL_SHARED_MAILBOX` from platform-api. Emails go back to SIMULATED.
- **Remove the permission:**
  `Remove-ManagementRoleAssignment DijiOnePlatform-<Env>-MailSend`. Optionally also run
  `Remove-ServicePrincipal` for that environment's identity. Never
  remove the shared scope, because other services use it. None of these steps affects DijiBirthday.
