<#
.SYNOPSIS
  AUTHORIZATION-CHANGING. Grants DijiOne platform-api (one environment) Exchange
  "Application Mail.Send" scoped to appassistant@dijitalteam.com only. Idempotent.

.DESCRIPTION
  Needs explicit owner approval per environment before it is run (see README.md).
  Supports -WhatIf: run with -WhatIf first to see exactly what would be created.
  - Creates platform-api's own management scope if absent; never edits an existing one.
  - Never touches any other assignment (DijiBirthday's included).
  - Never grants a Microsoft Graph application permission.
  - Refuses (changes nothing) on any unexpected existing state instead of "fixing" it.

.PREREQUISITES
  PowerShell 7+, ExchangeOnlineManagement 3.x, Connect-ExchangeOnline as an Exchange
  administrator holding the "Role Management" role (e.g. Organization Management).

.EXAMPLE
  ./grant-platform-api-mail-rbac.ps1 -Environment Dev -WhatIf
  ./grant-platform-api-mail-rbac.ps1 -Environment Dev
#>
[CmdletBinding(SupportsShouldProcess)]
param([Parameter(Mandatory)][ValidateSet('Dev', 'Uat', 'Prod')][string]$Environment)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'platform-api-mail-rbac.config.ps1')
$id = $PlatformApiIdentities[$Environment]

# 0. platform-api's own mailbox scope: create if absent; an existing one must already be exact.
$scope = Get-ManagementScope -Identity $MailboxScopeName -ErrorAction SilentlyContinue
if ($scope) {
  if (-not (Test-ScopeFilter $scope.RecipientRestrictionFilter)) { throw "Scope '$MailboxScopeName' filter '$($scope.RecipientRestrictionFilter)' is not restricted to $SharedMailbox — stop; review manually." }
  Write-Host "exists   scope $MailboxScopeName ($($scope.RecipientRestrictionFilter))"
} elseif ($PSCmdlet.ShouldProcess($MailboxScopeName, "New-ManagementScope -RecipientRestrictionFilter $MailboxScopeFilter")) {
  New-ManagementScope -Name $MailboxScopeName -RecipientRestrictionFilter $MailboxScopeFilter | Out-Null
  Write-Host "created  scope $MailboxScopeName"
}

# 1. Exchange service principal (pointer to the Entra managed identity).
$sp = Get-PlatformApiExchangeSp $id.AppId
if ($sp) {
  if ($sp.ObjectId -ne $id.ObjectId) { throw "Existing Exchange SP for AppId $($id.AppId) has ObjectId $($sp.ObjectId) (expected $($id.ObjectId)) — stop." }
  Write-Host "exists   service principal $($sp.DisplayName)"
} elseif ($PSCmdlet.ShouldProcess($id.DisplayName, 'New-ServicePrincipal')) {
  $sp = New-ServicePrincipal -AppId $id.AppId -ObjectId $id.ObjectId -DisplayName $id.DisplayName
  Write-Host "created  service principal $($id.DisplayName)"
}

# 2. The one role assignment. Refuse if this identity already holds any OTHER assignment.
if ($sp) {
  $other = @(Get-ManagementRoleAssignment -RoleAssigneeType ServicePrincipal |
    Where-Object { (Test-IsAssignee $_ $sp) -and $_.Name -ne $id.Assignment })
  if ($other.Count -gt 0) { throw "Identity already holds other assignment(s): $(($other | ForEach-Object { "$($_.Name)=$($_.Role)/$($_.CustomResourceScope)" }) -join ', ') — stop; review manually." }
}
$existing = Get-ManagementRoleAssignment -Identity $id.Assignment -ErrorAction SilentlyContinue
if ($existing) {
  if (-not $sp) { throw "Assignment $($id.Assignment) exists but the identity has no Exchange service principal — stop; review manually." }
  if ($existing.Role -ne 'Application Mail.Send' -or $existing.CustomResourceScope -ne $MailboxScopeName -or -not (Test-IsAssignee $existing $sp)) {
    throw "Assignment $($id.Assignment) exists with Role=$($existing.Role) Scope=$($existing.CustomResourceScope) Assignee=$($existing.RoleAssigneeName) — stop; review manually."
  }
  Write-Host "exists   assignment $($id.Assignment) (Application Mail.Send / $MailboxScopeName)"
} elseif ($PSCmdlet.ShouldProcess($id.Assignment, "New-ManagementRoleAssignment Application Mail.Send scoped to $MailboxScopeName")) {
  $spRef = if ($sp) { $sp.ObjectId } else { $id.ObjectId }
  New-ManagementRoleAssignment -Name $id.Assignment -Role 'Application Mail.Send' -App $spRef -CustomResourceScope $MailboxScopeName | Out-Null
  Write-Host "created  assignment $($id.Assignment)"
}

Write-Host "`nNext: run verify-platform-api-mail-rbac.ps1 -Environment $Environment -NegativeMailbox <other mailbox>."
Write-Host 'A fresh grant can take up to ~30-60 minutes to be honoured by Graph; verify before enabling MAIL_TRANSPORT=graph.'
