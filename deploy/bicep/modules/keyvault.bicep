// Key Vault — the DijiOne secret store from DEV onward (same shape for
// UAT/PROD). RBAC authorization; each Container App / Job identity gets
// `Key Vault Secrets User` (assigned in modules/containerapp.bicep and
// modules/job.bicep). Secret *values* are set out-of-band by
// deploy/init-secrets.sh between the foundation and workloads deployments
// (Amendment 3) — this module NEVER creates a secret value, not even a
// placeholder. `secretNames` is published as a contract only.

@description('Key Vault name — 3-24 chars, e.g. kv-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@description('Names of the secrets this vault is expected to hold. Contract only — no values are created here.')
param secretNames array = []

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    enablePurgeProtection: null
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

output id string = kv.id
output name string = kv.name
output uri string = kv.properties.vaultUri
// The secret NAMES this vault must hold before workloads deploy. deploy.sh
// asserts every one has a real value (init-secrets.sh writes them).
output expectedSecretNames array = secretNames
