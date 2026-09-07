// One DijiOne Container App (API or web). Loop this from main.bicep over the
// service definition array.
//
// Identity model: the app keeps a SYSTEM-assigned identity (for future
// per-service grants) AND attaches the shared USER-assigned identity
// `id-dijione-dev` which carries AcrPull + Key Vault Secrets User. Image pull
// and secret resolution use the UAMI, so the first revision can provision
// without waiting on a per-app role assignment (which would deadlock).

@description('Container App name — also the internal DNS hostname (http://<name>).')
param name string

@description('Full image reference, e.g. crdijionedev.azurecr.io/dijione/platform-api:<gitsha>')
param image string

@description('ACA managed environment resource id.')
param managedEnvironmentId string

@description('ACR login server, e.g. crdijionedev.azurecr.io')
param acrLoginServer string

@description('Resource id of the shared user-assigned identity (id-dijione-<env>) used for ACR pull + Key Vault secret resolution.')
param userAssignedIdentityId string

@description('Workload profile to run on. Consumption on every DijiOne env.')
param workloadProfileName string = 'Consumption'

@description('8000 for APIs, 3000 for web apps.')
param targetPort int

@description('true = FastAPI service with a GET /health route (gets HTTP probes). false = Next.js web app (no /health; uses the platform default TCP probe).')
param isApi bool = true

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
    identity: userAssignedIdentityId
  }
]
var secretEnv = [
  for s in secretRefs: {
    name: s.envName
    secretRef: s.name
  }
]

// FastAPI services expose GET /health; Next.js web apps do not. Empty = ACA's
// default TCP probe on the target port (correct for a plain HTTP server).
var httpProbes = isApi ? [
  {
    type: 'Liveness'
    httpGet: { path: '/health', port: targetPort }
    initialDelaySeconds: 5
    periodSeconds: 15
    failureThreshold: 4
  }
  {
    // readiness on /health — NOT /health/deep, which 200s when degraded and
    // never checks the migration head (/health/deep stays a smoke diagnostic).
    type: 'Readiness'
    httpGet: { path: '/health', port: targetPort }
    initialDelaySeconds: 5
    periodSeconds: 15
    failureThreshold: 6
  }
] : []

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${userAssignedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: managedEnvironmentId
    workloadProfileName: workloadProfileName
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
          identity: userAssignedIdentityId
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
          // HTTP probes only for FastAPI services (they expose GET /health).
          // Next.js web apps have no /health route — an HTTP probe there 404s
          // and the replica never goes Ready; they use the platform default
          // TCP probe on the target port instead (probes: []).
          probes: httpProbes
        }
      ]
      scale: {
        minReplicas: minReplicas
        maxReplicas: maxReplicas
      }
    }
  }
}

// ACR pull + Key Vault secret access come from the shared UAMI
// (userAssignedIdentityId), granted before this module runs. The
// system-assigned identity is retained for future per-service grants but
// carries no role assignment here.

output systemPrincipalId string = app.identity.principalId
output fqdn string = external ? app.properties.configuration.ingress.fqdn : ''
output name string = app.name
