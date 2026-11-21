# Shared constants for the platform-api Exchange RBAC scripts. Dot-sourced; changes nothing.
# Identities are each environment's platform-api SYSTEM-ASSIGNED managed identity (the one
# DefaultAzureCredential selects: no AZURE_CLIENT_ID is set on platform-api). Never the shared
# user-assigned id-dijione-<env> identity. Not secrets - public object identifiers.
# Re-check before use:  az containerapp show -g rg-dijione-<env> -n platform-api --query identity.principalId
#                       az ad sp show --id <principalId> --query appId

$SharedMailbox = 'appassistant@dijitalteam.com'
# The tenant's existing one-mailbox scope. Exchange Online refuses a second scope with an identical
# filter ("Use the existing management scope instead of creating a new one"), so every sender of
# appassistant@ (DijiBirthday, CustomerPortalV2, Zapier, platform-api) references this one scope.
# Each service still has its OWN identity and OWN role assignment. These scripts never create,
# edit or remove this scope.
$MailboxScopeName = 'DijiApps-AppAssistant-Mailbox-Scope'
$MailboxScopeFilter = "PrimarySmtpAddress -eq '$SharedMailbox'"
$BirthdayScopeName = $MailboxScopeName

$PlatformApiIdentities = @{
  Dev  = @{ AppId = '7ed96daa-05a4-47a1-a52c-8cf43ca39e09'; ObjectId = '6b26bb56-0759-4760-a0b7-4a5f20620d52'; DisplayName = 'DijiOnePlatform-Dev-API-MI';  Assignment = 'DijiOnePlatform-Dev-MailSend' }
  Uat  = @{ AppId = '579f1c99-7efb-4ca0-8d67-9015a71d2157'; ObjectId = 'fa7d3bb3-12dc-4f88-98b0-9593d6d312c6'; DisplayName = 'DijiOnePlatform-Uat-API-MI';  Assignment = 'DijiOnePlatform-Uat-MailSend' }
  Prod = @{ AppId = '26320838-423a-4aeb-b88b-8acc18b0724f'; ObjectId = 'b6c6caa0-0ae5-4a4b-9f17-f25a482a85a0'; DisplayName = 'DijiOnePlatform-Prod-API-MI'; Assignment = 'DijiOnePlatform-Prod-MailSend' }
}

function Test-ScopeFilter([string]$filter) {
  # Accept only a single equality on the shared mailbox (quote style / spacing / case tolerant).
  $norm = ($filter -replace '\s+', ' ').Trim().ToLower() -replace '"', "'"
  return $norm -eq "primarysmtpaddress -eq '$SharedMailbox'"
}

function Get-PlatformApiExchangeSp([string]$appId) {
  # Exactly zero or one Exchange service principal per AppId; anything else is unexpected state.
  $found = @(Get-ServicePrincipal | Where-Object { $_.AppId -eq $appId })
  if ($found.Count -gt 1) { throw "Multiple Exchange service principals for AppId $appId - stop; review manually." }
  if ($found.Count -eq 1) { return $found[0] }
  return $null
}

function Test-IsAssignee($assignment, $sp) {
  # Exchange may report the assignee by display name, identity, object id or app id, on either
  # RoleAssigneeName or RoleAssignee; accept any of those forms, nothing else.
  $known = @($sp.DisplayName, "$($sp.Identity)", "$($sp.ObjectId)", "$($sp.AppId)") | Where-Object { $_ }
  foreach ($prop in 'RoleAssigneeName', 'RoleAssignee') {
    if ($assignment.PSObject.Properties[$prop] -and "$($assignment.$prop)" -in $known) { return $true }
  }
  return $false
}

function Get-ExoObjectOrNull([scriptblock]$lookup) {
  # First-run safe lookup: "not found" -> $null; any other error (auth, throttling) still stops.
  try { return & $lookup }
  catch {
    if ("$_" -match "couldn't be found|could not be found|was not found|ManagementObjectNotFound") { return $null }
    throw
  }
}

function Get-GraphPaged([string]$url) {
  # Follows @odata.nextLink; throws on any az failure (fail closed).
  $items = @()
  while ($url) {
    $json = az rest --method get --url $url -o json 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $json) { throw "az rest failed: $url" }
    $page = $json | ConvertFrom-Json
    $items += @($page.value)
    $url = if ($page.PSObject.Properties['@odata.nextLink']) { $page.'@odata.nextLink' } else { $null }
  }
  return ,$items
}

function Test-InScope($result) {
  # Exchange Online returns InScope as the STRING 'True'/'False'; a non-empty string is truthy in
  # PowerShell, so never test it directly. Anything other than an exact true is "not in scope".
  return "$($result.InScope)".Trim() -eq 'True'
}
