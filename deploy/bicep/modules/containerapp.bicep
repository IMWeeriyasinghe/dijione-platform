// One DijiOne Container App (API or web). Loop this from main.bicep over the
// service definition array. System-assigned identity for ACR pull + Key
// Vault secret read (the role assignments are made in main.bicep).

@description('Container App name — also the internal DNS hostname (http://<name>).')
param name string

@description('Full image reference, e.g. crdijionedev.azurecr.io/dijione/platform-api:<gitsha>')
param image string

@description('ACA managed environment resource id.')
param managedEnvironmentId string

@description('ACR login server, e.g. crdijionedev.azurecr.io')
param acrLoginServer string

@description('ACR resource name — for the AcrPull role assignment on this app\'s identity.')
param acrName string

@description('Key Vault name — for the Key Vault Secrets User role assignment on this app\'s identity.')
param keyVaultName string

@description('8000 for APIs, 3000 for web apps.')
param targetPort int

@description('true = public ingress (shell-web + the two external portals only).')
param external bool = false

param minReplicas int = 0
param maxReplicas int = 2
param cpu string = '0.25'
param memory string = '0.5Gi'

@description('Plain (non-secret) env vars: [{ name, value }].')
param envVars array = []

@description('Key Vault-backed secrets: [{ name, keyVaultUrl }]. Each becomes an ACA secret (read via managed identity) and an env var <NAME_UPPER> = secretRef(name).')
param secretRefs array = []

param location string = resourceGroup().location
param tags object = {}

var acaSecrets = [
  for s in secretRefs: {
    name: s.name
    keyVaultUrl: s.keyVaultUrl
    identity: 'system'
  }
]
var secretEnv = [
  for s in secretRefs: {
    name: s.envName
    secretRef: s.name
  }
]

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: external
        targetPort: targetPort
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          identity: 'system'
        }
      ]
      secrets: acaSecrets
    }
    template: {
      containers: [
        {
          name: name
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: concat(envVars, secretEnv)
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: targetPort
              }
              initialDelaySeconds: 5
              periodSeconds: 15
              failureThreshold: 4
            }
            {
              // DEV: readiness also points at /health — NOT /health/deep,
              // which returns 200 even when degraded and never checks the
              // migration head. /health/deep stays a diagnostic (smoke).
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: targetPort
              }
              initialDelaySeconds: 5
              periodSeconds: 15
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

// --- least-privilege role assignments for this app's identity ---
var acrPullRoleId = '7f951dda-4ed3-4680-a7ca-43fe172d538d'
var kvSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' existing = {
  name: acrName
}
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: keyVaultName
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, name, acrPullRoleId)
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', acrPullRoleId)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}
resource kvSecrets 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, name, kvSecretsUserRoleId)
  scope: kv
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', kvSecretsUserRoleId)
    principalId: app.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

output principalId string = app.identity.principalId
output fqdn string = external ? app.properties.configuration.ingress.fqdn : ''
output name string = app.name
