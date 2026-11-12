// Targeted Diji On-site release template (UAT/PROD bring-up).
//
//   az deployment group create -g rg-dijione-<env> \
//     -f deploy/bicep/onsite-release.bicep -p environmentName=<env> ... imageDigests='{...}'
//
// Creates ONLY the Diji On-site footprint inside an existing environment —
// onsite-api, onsite-web, migrate-onsite-api, optional onsite-sync-job — plus
// the generic people-workforce-sync-job. It deliberately does not touch the
// full main.bicep surface, so no unrelated app (DijiBirthday, DijiTalentFlow,
// Admin, …) can be re-imaged by a release that does not change it.
//
// Every resource mirrors main.bicep (same modules, env vars and Key Vault
// wiring) so a later full main.bicep deployment with deployOnsite=true is a
// no-op for these resources. Pre-requisites (done outside this template):
// the onsite_<env> database and the `database-url-onsite` Key Vault secret
// (foundation.bicep / init-secrets.sh conventions).

@allowed([ 'uat', 'prod' ])
param environmentName string

param location string = 'southeastasia'

@description('Registry login server holding the release images, e.g. crdijionenonprod.azurecr.io (UAT) or crdijioneprod.azurecr.io (PROD).')
param imageRegistryLoginServer string

@description('Exact digests: { "onsite-api": "sha256:…", "onsite-web": "sha256:…", "people-api": "sha256:…" }')
param imageDigests object

@description('"none" = no attendance source yet (nothing is synced); "live" = Azure SQL onsite.* via the onsite-api managed identity. Never "mock" in UAT/PROD.')
@allowed([ 'none', 'live' ])
param onsiteIntegrationsMode string = 'none'

param onsiteSqlServer string = ''
param onsiteSqlDatabase string = ''

@description('Create the scheduled onsite-sync-job. Leave false until a real attendance source exists for this environment.')
param deployOnsiteSyncJob bool = false
param onsiteSyncCron string = '* * * * *'

@description('Create the generic people-workforce-sync-job (Workforce Directory refresh, 6-hourly).')
param deployWorkforceSyncJob bool = true

var tags = {
  platform: 'dijione'
  env: environmentName
  managedBy: 'bicep'
}
var appEnv = environmentName

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: 'cae-dijione-${environmentName}'
}
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: 'kv-dijione-${environmentName}'
}
// The environment's existing resource-access identity (Key Vault Secrets User
// + AcrPull already granted by the original main.bicep bring-up).
resource uami 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: 'id-dijione-${environmentName}'
}

var kvUri = kv.properties.vaultUri
var envDomain = cae.properties.defaultDomain
var corsOrigins = join([
  'https://shell-web.${envDomain}'
  'https://talentflow-portal-web.${envDomain}'
  'https://birthday-supplier-web.${envDomain}'
], ',')

var commonApiEnv = [
  { name: 'APP_ENV', value: appEnv }
  { name: 'EMAIL_SENDING_MODE', value: 'mock' }
  { name: 'API_CORS_ORIGINS', value: corsOrigins }
]
var trustSecrets = [
  { name: 'jwt-${environmentName}-secret', keyVaultUrl: '${kvUri}secrets/jwt-${environmentName}-secret', envName: 'PLATFORM_JWT_SECRET' }
  { name: 'internal-service-secret', keyVaultUrl: '${kvUri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' }
]
var onsiteDbSecret = { name: 'database-url-onsite', keyVaultUrl: '${kvUri}secrets/database-url-onsite', envName: 'DATABASE_URL' }

module onsiteApi 'modules/containerapp.bicep' = {
  name: 'app-onsite-api'
  params: {
    name: 'onsite-api'
    image: '${imageRegistryLoginServer}/dijione/onsite-api@${imageDigests['onsite-api']}'
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: uami.id
    targetPort: 8000
    isApi: true
    external: false
    minReplicas: 0
    maxReplicas: 1
    location: location
    tags: tags
    envVars: concat(commonApiEnv, [
      { name: 'INTEGRATIONS_MODE', value: onsiteIntegrationsMode }
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'PEOPLE_API_URL', value: 'http://people-api' }
      { name: 'PEOPLE_API_TIMEOUT_SECONDS', value: '30' }
    ], onsiteIntegrationsMode == 'live' ? [
      { name: 'ONSITE_SQL_SERVER', value: onsiteSqlServer }
      { name: 'ONSITE_SQL_DATABASE', value: onsiteSqlDatabase }
    ] : [])
    secretRefs: concat(trustSecrets, [ onsiteDbSecret ])
  }
}

module onsiteWeb 'modules/containerapp.bicep' = {
  name: 'app-onsite-web'
  params: {
    name: 'onsite-web'
    image: '${imageRegistryLoginServer}/dijione/onsite-web@${imageDigests['onsite-web']}'
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: uami.id
    targetPort: 3000
    isApi: false
    external: false
    minReplicas: 0
    maxReplicas: 1
    location: location
    tags: tags
    envVars: [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'ONSITE_API_URL', value: 'http://onsite-api' }
    ]
  }
}

module migrateOnsite 'modules/job.bicep' = {
  name: 'job-migrate-onsite-api'
  params: {
    name: 'migrate-onsite-api'
    image: '${imageRegistryLoginServer}/dijione/onsite-api@${imageDigests['onsite-api']}'
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
    secretRefs: [ onsiteDbSecret ]
  }
}

var scheduled = concat(
  deployWorkforceSyncJob ? [
    { name: 'people-workforce-sync-job', image: 'people-api', cron: '15 */6 * * *', url: 'http://people-api/api/people/internal/workforce-directory/scheduled-sync', timeout: 1800 }
  ] : [],
  deployOnsiteSyncJob ? [
    { name: 'onsite-sync-job', image: 'onsite-api', cron: onsiteSyncCron, url: 'http://onsite-api/api/onsite/internal/scheduled-sync', timeout: 120 }
  ] : []
)

module syncJobs 'modules/job.bicep' = [
  for j in scheduled: {
    name: 'job-${j.name}'
    params: {
      name: j.name
      image: '${imageRegistryLoginServer}/dijione/${j.image}@${imageDigests[j.image]}'
      managedEnvironmentId: cae.id
      acrLoginServer: imageRegistryLoginServer
      userAssignedIdentityId: uami.id
      triggerType: 'Schedule'
      cronExpression: j.cron
      replicaTimeout: j.timeout
      location: location
      tags: tags
      command: [ '/bin/sh', '-c' ]
      args: [ 'curl -fsS -X POST -H "X-Internal-Token: $INTERNAL_SERVICE_SECRET" -H "X-Internal-Caller: ${j.name}" ${j.url}' ]
      secretRefs: [
        { name: 'internal-service-secret', keyVaultUrl: '${kvUri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' }
      ]
    }
  }
]

output onsiteApiPrincipalId string = onsiteApi.outputs.systemPrincipalId
