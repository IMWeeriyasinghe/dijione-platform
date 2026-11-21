<#
.SYNOPSIS
  READ-ONLY verification of Exchange RBAC for Applications for DijiOne platform-api
  (sending as appassistant@dijitalteam.com). Changes nothing.

.DESCRIPTION
  Reports, for one environment:
    1. platform-api's own mailbox scope exists and is restricted to exactly the shared mailbox.
    2. Whether the platform-api system-assigned managed identity is registered in Exchange.
    3. Every "Application Mail.*" role assignment in the tenant (so Birthday's are visible,
       never changed), and any assignment for this identity that is broader than intended.
    4. Positive (shared mailbox -> InScope True) and negative (other mailbox -> InScope False)
       authorization checks, when the identity is registered.
  Exits 0 only when the identity is authorized for the shared mailbox and nothing else.

.PREREQUISITES
  PowerShell 7+, module ExchangeOnlineManagement 3.x, and a session from
  Connect-ExchangeOnline as a user with an Exchange role that can read RBAC
  (View-Only Organization Management is enough for this script).

.EXAMPLE
  ./verify-platform-api-mail-rbac.ps1 -Environment Dev -NegativeMailbox someone.else@dijitalteam.com
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory)][ValidateSet('Dev', 'Uat', 'Prod')][string]$Environment,
  # Any real mailbox in the tenant OTHER than the shared mailbox; must come back InScope False.
  [Parameter(Mandatory)][string]$NegativeMailbox
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'platform-api-mail-rbac.config.ps1')

$id = $PlatformApiIdentities[$Environment]
$ok = $true
function Fail($msg) { Write-Host "FAIL  $msg" -ForegroundColor Red; $script:ok = $false }
function Pass($msg) { Write-Host "OK    $msg" -ForegroundColor Green }

if ($NegativeMailbox.Trim().ToLower() -eq $SharedMailbox) { throw 'NegativeMailbox must differ from the shared mailbox.' }

# 1. Scope
$scope = Get-ManagementScope -Identity $MailboxScopeName -ErrorAction SilentlyContinue
if (-not $scope) { Fail "management scope '$MailboxScopeName' not found" }
elseif (-not (Test-ScopeFilter $scope.RecipientRestrictionFilter)) {
  Fail "scope filter is '$($scope.RecipientRestrictionFilter)' — expected only PrimarySmtpAddress -eq '$SharedMailbox'"
} else { Pass "scope '$MailboxScopeName' filter: $($scope.RecipientRestrictionFilter)" }
$bScope = Get-ManagementScope -Identity $BirthdayScopeName -ErrorAction SilentlyContinue
if ($bScope) { Write-Host "INFO  DijiBirthday scope '$BirthdayScopeName' (read only): $($bScope.RecipientRestrictionFilter)" }

# 2. Exchange service principal for this identity
$sp = Get-PlatformApiExchangeSp $id.AppId
if (-not $sp) { Write-Host "INFO  platform-api $Environment identity (AppId $($id.AppId)) is NOT registered in Exchange" -ForegroundColor Yellow }
elseif ($sp.ObjectId -ne $id.ObjectId) { Fail "Exchange SP for AppId $($id.AppId) has ObjectId $($sp.ObjectId), expected $($id.ObjectId)" }
else { Pass "Exchange SP '$($sp.DisplayName)' AppId $($sp.AppId) ObjectId $($sp.ObjectId)" }

# 3. Application Mail.* assignments (all, read-only listing)
$all = @(Get-ManagementRoleAssignment -RoleAssigneeType ServicePrincipal |
  Where-Object { $_.Role -like 'Application Mail*' })
Write-Host "`nApplication Mail.* role assignments in the tenant:"
$all | Format-Table Name, Role, RoleAssigneeName, CustomResourceScope -AutoSize | Out-String | Write-Host
if ($sp) {
  $mine = @(Get-ManagementRoleAssignment -RoleAssigneeType ServicePrincipal | Where-Object { Test-IsAssignee $_ $sp })
  foreach ($a in $mine) {
    if ($a.Name -ne $id.Assignment) { Fail "unexpected extra assignment on this identity: $($a.Name) = $($a.Role) / $($a.CustomResourceScope)" }
    elseif ($a.Role -ne 'Application Mail.Send') { Fail "broader role on this identity: $($a.Name) = $($a.Role)" }
    elseif ($a.CustomResourceScope -ne $MailboxScopeName) { Fail "assignment $($a.Name) has scope '$($a.CustomResourceScope)' (expected $MailboxScopeName)" }
    else { Pass "assignment $($a.Name): $($a.Role) scoped to $($a.CustomResourceScope)" }
  }
  if ($mine.Count -eq 0) { Write-Host "INFO  no Application Mail.* assignment for this identity yet" -ForegroundColor Yellow; $ok = $false }

  # 4. Positive / negative authorization
  $pos = @(Test-ServicePrincipalAuthorization -Identity $sp.ObjectId -Resource $SharedMailbox |
    Where-Object { $_.RoleName -eq 'Application Mail.Send' })
  if ($pos.Count -and ($pos | Where-Object InScope)) { Pass "positive: Mail.Send InScope True for $SharedMailbox" }
  else { Fail "positive: Mail.Send NOT in scope for $SharedMailbox (new grants can take time to propagate)" }

  $neg = @(Test-ServicePrincipalAuthorization -Identity $sp.ObjectId -Resource $NegativeMailbox |
    Where-Object { $_.RoleName -like 'Application Mail*' -and $_.InScope })
  if ($neg.Count -eq 0) { Pass "negative: no Mail.* permission on $NegativeMailbox" }
  else { Fail "negative: identity CAN act on $NegativeMailbox ($($neg.RoleName -join ', ')) — scope is too broad" }
} else { $ok = $false }

# 5. Exchange cannot see Entra Graph app roles: a tenant-wide Graph Mail.* grant would bypass the scope.
#    Checked with the Azure CLI (az login as a user that can read service principals).
$graphMail = $null
try {
  $json = az rest --method get --url "https://graph.microsoft.com/v1.0/servicePrincipals/$($id.ObjectId)/appRoleAssignments" -o json 2>$null
  if ($LASTEXITCODE -ne 0 -or -not $json) { throw 'az rest failed' }
  $assigned = @(($json | ConvertFrom-Json).value | Where-Object { $_.resourceDisplayName -eq 'Microsoft Graph' })
  $graphSp = az ad sp show --id 00000003-0000-0000-c000-000000000000 --query "appRoles[].{id:id,v:value}" -o json | ConvertFrom-Json
  $graphMail = @($assigned | ForEach-Object { $r = $_.appRoleId; ($graphSp | Where-Object { $_.id -eq $r }).v } | Where-Object { $_ -like 'Mail.*' })
} catch { Fail "could not read Entra Graph app roles for $($id.ObjectId) (az login required): $_" }
if ($null -ne $graphMail) {
  if ($graphMail.Count -eq 0) { Pass 'Entra: no Microsoft Graph Mail.* application permission on this identity' }
  else { Fail "Entra: tenant-wide Graph permission(s) present: $($graphMail -join ', ') — remove before enabling" }
}

Write-Host ''
if ($ok) { Write-Host "RESULT: platform-api $Environment is authorized to send as $SharedMailbox only." -ForegroundColor Green; exit 0 }
Write-Host "RESULT: platform-api $Environment is NOT (fully/correctly) authorized. Do not enable MAIL_TRANSPORT=graph." -ForegroundColor Red
exit 1
