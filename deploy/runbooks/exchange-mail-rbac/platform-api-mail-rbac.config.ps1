# Shared constants for the platform-api Exchange RBAC scripts. Dot-sourced; changes nothing.
# Identities are each environment's platform-api SYSTEM-ASSIGNED managed identity (the one
# DefaultAzureCredential selects: no AZURE_CLIENT_ID is set on platform-api). Never the shared
# user-assigned id-dijione-<env> identity. Not secrets — public object identifiers.
# Re-check before use:  az containerapp show -g rg-dijione-<env> -n platform-api --query identity.principalId
#                       az ad sp show --id <principalId> --query appId

$SharedMailbox = 'appassistant@dijitalteam.com'
# platform-api's OWN scope (CLAUDE.md rule 21a: own scope per sending service). Same one-mailbox filter as
# DijiBirthday's 'DijiApps-AppAssistant-Mailbox-Scope', which these scripts only ever READ, never change.
$MailboxScopeName = 'DijiOnePlatform-MailSender-Scope'
$MailboxScopeFilter = "PrimarySmtpAddress -eq '$SharedMailbox'"
$BirthdayScopeName = 'DijiApps-AppAssistant-Mailbox-Scope'

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
