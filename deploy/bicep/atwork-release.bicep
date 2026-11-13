// Targeted DijiAtWork release. Creates ONLY atwork-api, atwork-web,
// migrate-atwork-api and atwork-notifications-job in an existing environment,
// mirroring main.bicep, so no other application can be re-imaged by it.
// Pre-requisites: the atwork_<env> database and the database-url-atwork secret.

@allowed([ 'dev', 'uat', 'prod' ])
param environmentName string = 'dev'
param location string = 'southeastasia'

@description('crdijionenonprod.azurecr.io for DEV and UAT; crdijioneprod.azurecr.io for PROD (digests imported, never rebuilt).')
param imageRegistryLoginServer string = 'crdijionenonprod.azurecr.io'

@description('Exact digests: { "atwork-api": "sha256:…", "atwork-web": "sha256:…" }')
param imageDigests object

@description('Replica floor for atwork-api and atwork-web. PROD keeps one warm replica (2026-11 performance decision; keep in step with main.prod.bicepparam); DEV and UAT scale to zero.')
@minValue(0)
@maxValue(1)
param minReplicas int = environmentName == 'prod' ? 1 : 0

var tags = { platform: 'dijione', env: environmentName, managedBy: 'bicep' }
var appEnv = environmentName == 'dev' ? 'development' : environmentName

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: 'cae-dijione-${environmentName}'
}
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-dijione-${environmentName}'
}
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-dijione-${environmentName}'
}

var kvUri = kv.properties.vaultUri
var envDomain = cae.properties.defaultDomain
var trustSecrets = [
  { name: 'jwt-${environmentName}-secret', keyVaultUrl: '${kvUri}secrets/jwt-${environmentName}-secret', envName: 'PLATFORM_JWT_SECRET' }
  { name: 'internal-service-secret', keyVaultUrl: '${kvUri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' }
]
var dbSecret = { name: 'database-url-atwork', keyVaultUrl: '${kvUri}secrets/database-url-atwork', envName: 'DATABASE_URL' }
var apiImage = '${imageRegistryLoginServer}/dijione/atwork-api@${imageDigests['atwork-api']}'

module atworkApi 'modules/containerapp.bicep' = {
  name: 'app-atwork-api'
  params: {
    name: 'atwork-api'
    image: apiImage
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: uami.id
    targetPort: 8000
    isApi: true
    external: false
    minReplicas: minReplicas
    maxReplicas: 1
    location: location
    tags: tags
    envVars: [
      { name: 'APP_ENV', value: appEnv }
      { name: 'EMAIL_SENDING_MODE', value: 'mock' }
      { name: 'API_CORS_ORIGINS', value: 'https://shell-web.${envDomain}' }
      { name: 'INTEGRATIONS_MODE', value: 'mock' }
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
    ]
    secretRefs: concat(trustSecrets, [ dbSecret ])
  }
}

module atworkWeb 'modules/containerapp.bicep' = {
  name: 'app-atwork-web'
  params: {
    name: 'atwork-web'
    image: '${imageRegistryLoginServer}/dijione/atwork-web@${imageDigests['atwork-web']}'
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: uami.id
    targetPort: 3000
    isApi: false
    external: false
    minReplicas: minReplicas
    maxReplicas: 1
    location: location
    tags: tags
    envVars: [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'ATWORK_API_URL', value: 'http://atwork-api' }
    ]
  }
}

module migrateAtwork 'modules/job.bicep' = {
  name: 'job-migrate-atwork-api'
  params: {
    name: 'migrate-atwork-api'
    image: apiImage
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: uami.id
    triggerType: 'Manual'
    replicaTimeout: 900
    location: location
    tags: tags
    command: [ '/bin/sh', '-c' ]
    args: [ 'alembic upgrade head' ]
    envVars: [ { name: 'APP_ENV', value: appEnv } ]
    secretRefs: [ dbSecret ]
  }
}

module notificationsJob 'modules/job.bicep' = {
  name: 'job-atwork-notifications-job'
  params: {
    name: 'atwork-notifications-job'
    image: apiImage
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: uami.id
    triggerType: 'Schedule'
    cronExpression: '*/15 * * * *'
    replicaTimeout: 300
    location: location
    tags: tags
    command: [ '/bin/sh', '-c' ]
    args: [ 'curl -fsS -X POST -H "X-Internal-Token: $INTERNAL_SERVICE_SECRET" -H "X-Internal-Caller: atwork-notifications-job" http://atwork-api/api/atwork/internal/notifications/run' ]
    secretRefs: [ { name: 'internal-service-secret', keyVaultUrl: '${kvUri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' } ]
  }
}
