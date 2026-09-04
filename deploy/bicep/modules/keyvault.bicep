// Key Vault — the DijiOne secret store from DEV onward (same shape for
// UAT/PROD). RBAC authorization; each Container App / Job identity gets
// `Key Vault Secrets User` (assigned in main.bicep). Secret *values* are
// set out-of-band (deploy/deploy.sh / an operator), never in Bicep.

@description('Key Vault name — 3-24 chars, e.g. kv-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@description('Names of the secrets this vault will hold (values set separately).')
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

// Placeholder secret versions so the KV references resolve on first deploy;
// the real values are set by deploy/deploy.sh via `az keyvault secret set`.
resource placeholders 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = [
  for s in secretNames: {
    parent: kv
    name: s
    properties: {
      value: 'set-me-via-deploy.sh'
    }
  }
]

output id string = kv.id
output name string = kv.name
output uri string = kv.properties.vaultUri
