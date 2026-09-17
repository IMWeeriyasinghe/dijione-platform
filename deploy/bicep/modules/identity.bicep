// DijiOne — DEV bootstrap resource-access identity.
//
// A single user-assigned managed identity used ONLY for ACA infrastructure
// bootstrap/runtime resource access:
//   * AcrPull on the shared registry   (granted by modules/acr-pull.bicep in
//     the registry's resource group — see main.bicep)
//   * Key Vault Secrets User on kv-dijione-<env>   (granted here — same RG)
//
// Why this exists: a Container App / Job cannot provision its FIRST revision
// without image-pull permission, but a per-workload system-assigned identity
// only exists after the workload is created — so a role assignment for it
// cannot be created early enough. A pre-created UAMI with the two required
// data-plane roles breaks that deadlock. It is NOT a service identity: no
// compute, management, or business-domain authorization is attached, and
// service-to-service auth stays on INTERNAL_SERVICE_SECRET. Each workload
// still keeps its own system-assigned identity for future per-service grants.

@description('UAMI name, e.g. id-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@description('Key Vault name (same RG) — this identity receives Key Vault Secrets User on it.')
param keyVaultName string

@description('Override the Key Vault Secrets User role-assignment NAME (a GUID) instead of the deterministic guid(kv.id, uami.id, roleId) this module computes by default. Only needed when that exact (scope, role, principal) grant already exists under a different assignment id — e.g. it was created out-of-band before this module ever ran for this environment — so a fresh incremental deployment does not collide with it as a duplicate RBAC assignment. Leave empty (the default) everywhere else.')
param existingKvSecretsUserRoleAssignmentName string = ''

resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
  tags: tags
}

// Key Vault Secrets User — read secret values only, one vault.
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource kvSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: empty(existingKvSecretsUserRoleAssignmentName) ? guid(kv.id, uami.id, kvSecretsUserRoleId) : existingKvSecretsUserRoleAssignmentName
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: uami.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

output id string = uami.id
output principalId string = uami.properties.principalId
output clientId string = uami.properties.clientId
output name string = uami.name
