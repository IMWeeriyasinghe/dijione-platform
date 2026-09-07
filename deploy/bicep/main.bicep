// DijiOne — Azure WORKLOADS for one environment (DEV / UAT / PROD).
//
//   az deployment group create -g rg-dijione-<env> \
//     -f deploy/bicep/main.bicep -p deploy/bicep/main.<env>.bicepparam \
//     -p imageDigests='{...}'   (or -p imageTag=<gitsha> for a first bring-up)
//
// PREREQUISITES (Amendment 3): deploy/bicep/foundation.bicep has run AND
// deploy/init-secrets.sh has written every Key Vault secret value. This
// template only creates the Container Apps + Jobs; it references the Container
// Apps Environment and Key Vault as existing, and FAILS if a referenced secret
// is missing (correct — that means secret-init was skipped).
//
// Immutable-artifact model (Amendment 4): images are built ONCE and deployed by
// sha256 digest. `imageDigests` maps every deployed service to its digest;
// `imageTag` is retained only for the very first bring-up before the pipeline
// records digests. The SAME digest is promoted DEV -> UAT -> PROD (PROD via
// `az acr import`, see deploy/promote.sh).

targetScope = 'resourceGroup'

@description('dev | uat | prod.')
param environmentName string = 'dev'

@description('Azure region.')
param location string = 'southeastasia'

@description('Registry login server for THIS environment, e.g. crdijionenonprod.azurecr.io (dev/uat) or crdijioneprod.azurecr.io (prod).')
param imageRegistryLoginServer string

@description('Registry name, e.g. crdijionenonprod.')
param imageRegistryName string

@description('Resource group the registry lives in (rg-dijione-shared for dev/uat; rg-dijione-prod for prod).')
param imageRegistryResourceGroup string

@description('service -> sha256 digest, e.g. { "platform-api": "sha256:abc..." }. When set it MUST cover every deployed service.')
param imageDigests object = {}

@description('Fallback tag for a first bring-up only, when imageDigests is empty. A git SHA.')
param imageTag string = ''

@description('Deploy DijiBirthday (people-api, birthday-api, birthday-web, birthday-supplier-web + 2 jobs).')
param deployBirthday bool = true

@description('Deploy the commercial-api skeleton.')
param deployCommercial bool = false

@description('Container size — lean floor by default (Amendment 8).')
param containerCpu string = '0.25'
param containerMemory string = '0.5Gi'

@description('Per-service replica floor. Empty = every service scales to zero (DEV/UAT). PROD sets platform-api + shell-web to 1.')
param minReplicas object = {}

@description('Default replica ceiling and per-service overrides.')
param maxReplicasDefault int = 1
param maxReplicasOverrides object = {}

var tags = {
  platform: 'dijione'
  env: environmentName
  managedBy: 'bicep'
}

var kvName = 'kv-dijione-${environmentName}'
var caeName = 'cae-dijione-${environmentName}'
var uamiName = 'id-dijione-${environmentName}'

resource cae 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: caeName
}
resource kv 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: kvName
}
var kvUri = kv.properties.vaultUri

// ---- bootstrap resource-access identity (breaks the ACA first-revision
// deadlock — see modules/identity.bicep). Created, and granted BOTH data-plane
// roles, before any Container App / Job.
module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    name: uamiName
    location: location
    tags: tags
    keyVaultName: kvName
  }
}

// The single AcrPull grant for that identity, in the registry's resource group.
module uamiAcrPull 'modules/acr-pull.bicep' = {
  name: 'acrpull-${uamiName}'
  scope: resourceGroup(imageRegistryResourceGroup)
  params: {
    acrName: imageRegistryName
    granteeName: uamiName
    principalId: identity.outputs.principalId
  }
}

// ---- service catalogue ---------------------------------------------------
var coreServices = [
  { name: 'platform-api', kind: 'api', db: 'platform_dev', external: false }
  { name: 'admin-api', kind: 'api', db: '', external: false }
  { name: 'talent-api', kind: 'api', db: 'talent_dev', external: false }
  { name: 'recruitment-api', kind: 'api', db: 'recruitment_dev', external: false }
  { name: 'shell-web', kind: 'web', db: '', external: true }
  { name: 'admin-web', kind: 'web', db: '', external: false }
  { name: 'talent-web', kind: 'web', db: '', external: false }
  { name: 'talentflow-portal-web', kind: 'web', db: '', external: true }
]
var birthdayServices = [
  { name: 'people-api', kind: 'api', db: 'people_dev', external: false }
  { name: 'birthday-api', kind: 'api', db: 'birthday_dev', external: false }
  { name: 'birthday-web', kind: 'web', db: '', external: false }
  { name: 'birthday-supplier-web', kind: 'web', db: '', external: true }
]
var commercialServices = [
  { name: 'commercial-api', kind: 'api', db: 'commercial_dev', external: false }
]
var services = concat(
  coreServices,
  deployBirthday ? birthdayServices : [],
  deployCommercial ? commercialServices : []
)

// ---- image ref helper (digest first, tag only for first bring-up) --------
func imageRef(svc string, registry string, digests object, tag string) string =>
  empty(digests) ? '${registry}/dijione/${svc}:${tag}' : '${registry}/dijione/${svc}@${digests[svc]}'

// Deterministic external FQDNs so API_CORS_ORIGINS is set in one pass.
var envDomain = cae.properties.defaultDomain
var corsOrigins = join([
  'https://shell-web.${envDomain}'
  'https://talentflow-portal-web.${envDomain}'
  deployBirthday ? 'https://birthday-supplier-web.${envDomain}' : ''
], ',')

var commonApiEnv = [
  { name: 'APP_ENV', value: environmentName == 'dev' ? 'development' : environmentName }
  { name: 'INTEGRATIONS_MODE', value: 'mock' }
  { name: 'EMAIL_SENDING_MODE', value: 'mock' }
  { name: 'API_CORS_ORIGINS', value: corsOrigins }
]

// Per-service configuration — internal service URLs (ACA internal DNS is
// http://<app-name>) + module modes. Declarative here so a redeploy does not
// wipe them (Bicep env is desired-state, not a merge). `AUTH_MODE=dev` on
// platform-api = the dev-login identity provider (no real Entra in DEV).
func _perServiceEnv(svc string) array =>
  svc == 'shell-web' ? [
    { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
    { name: 'ADMIN_API_URL', value: 'http://admin-api' }
    { name: 'TALENT_API_URL', value: 'http://talent-api' }
    { name: 'BIRTHDAY_API_URL', value: 'http://birthday-api' }
    { name: 'SPARK_API_URL', value: 'http://spark-api' }
    { name: 'ADMIN_WEB_URL', value: 'http://admin-web' }
    { name: 'TALENT_WEB_URL', value: 'http://talent-web' }
    { name: 'BIRTHDAY_WEB_URL', value: 'http://birthday-web' }
  ]
  : svc == 'platform-api' ? [
      { name: 'AUTH_MODE', value: 'dev' }
      { name: 'DEV_IDENTITY_MODE', value: 'true' }
      { name: 'TALENT_API_URL', value: 'http://talent-api' }
    ]
  : svc == 'admin-api' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'TALENT_API_URL', value: 'http://talent-api' }
    ]
  : svc == 'talent-api' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'RECRUITMENT_API_URL', value: 'http://recruitment-api' }
    ]
  : svc == 'recruitment-api' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'OPPORTUNITY_SYNC_LIMIT', value: '200' }
    ]
  : svc == 'people-api' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
    ]
  : svc == 'birthday-api' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'PEOPLE_API_URL', value: 'http://people-api' }
    ]
  : svc == 'admin-web' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'ADMIN_API_URL', value: 'http://admin-api' }
    ]
  : svc == 'talent-web' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'TALENT_API_URL', value: 'http://talent-api' }
    ]
  : svc == 'birthday-web' ? [
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'BIRTHDAY_API_URL', value: 'http://birthday-api' }
    ]
  : svc == 'talentflow-portal-web' ? [
      { name: 'TALENT_API_URL', value: 'http://talent-api' }
    ]
  : []

// KV secret wiring per API: shared trust anchors + this service's own db url.
func _apiSecretRefs(svc string, db string, uri string) array => concat(
  [
    { name: 'jwt-dev-secret', keyVaultUrl: '${uri}secrets/jwt-dev-secret', envName: 'JWT_DEV_SECRET' }
    { name: 'internal-service-secret', keyVaultUrl: '${uri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' }
  ],
  svc == 'talent-api' ? [
    { name: 'external-session-jwt-secret', keyVaultUrl: '${uri}secrets/external-session-jwt-secret', envName: 'EXTERNAL_SESSION_JWT_SECRET' }
  ] : [],
  db == '' ? [] : [
    { name: 'database-url-${replace(db, '_dev', '')}', keyVaultUrl: '${uri}secrets/database-url-${replace(db, '_dev', '')}', envName: 'DATABASE_URL' }
  ]
)

// ---- the apps --------------------------------------------------------------
@batchSize(4)
module apps 'modules/containerapp.bicep' = [
  for s in services: {
    name: 'app-${s.name}'
    // identity dependency is implied by identity.outputs.id; the AcrPull grant
    // must also be in place before the first revision pulls the image.
    dependsOn: [ uamiAcrPull ]
    params: {
      name: s.name
      image: imageRef(s.name, imageRegistryLoginServer, imageDigests, imageTag)
      managedEnvironmentId: cae.id
      acrLoginServer: imageRegistryLoginServer
      userAssignedIdentityId: identity.outputs.id
      targetPort: s.kind == 'api' ? 8000 : 3000
      isApi: s.kind == 'api'
      external: s.external
      minReplicas: minReplicas[?s.name] ?? 0
      maxReplicas: maxReplicasOverrides[?s.name] ?? maxReplicasDefault
      cpu: containerCpu
      memory: containerMemory
      location: location
      tags: tags
      envVars: concat(s.kind == 'api' ? commonApiEnv : [], _perServiceEnv(s.name))
      secretRefs: s.kind == 'api' ? _apiSecretRefs(s.name, s.db, kvUri) : []
    }
  }
]

// ---- migration jobs (one per DB-owning service, on its OWN image) --------
var migrateTargets = concat(
  [ 'platform-api', 'talent-api', 'recruitment-api' ],
  deployBirthday ? [ 'people-api', 'birthday-api' ] : [],
  deployCommercial ? [ 'commercial-api' ] : []
)

func _dbFor(svc string) string =>
  svc == 'platform-api' ? 'platform_dev'
    : svc == 'talent-api' ? 'talent_dev'
    : svc == 'recruitment-api' ? 'recruitment_dev'
    : svc == 'people-api' ? 'people_dev'
    : svc == 'birthday-api' ? 'birthday_dev'
    : 'commercial_dev'

module migrateJobs 'modules/job.bicep' = [
  for t in migrateTargets: {
    name: 'job-migrate-${t}'
    dependsOn: [ uamiAcrPull ]
    params: {
      name: 'migrate-${t}'
      image: imageRef(t, imageRegistryLoginServer, imageDigests, imageTag)
      managedEnvironmentId: cae.id
      acrLoginServer: imageRegistryLoginServer
      userAssignedIdentityId: identity.outputs.id
      triggerType: 'Manual'
      replicaTimeout: 900
      location: location
      tags: tags
      command: [ '/bin/sh', '-c' ]
      // `alembic` console script — `python -m alembic` is NOT runnable (the
      // package has no __main__). /opt/venv/bin is on PATH in the image.
      args: [ 'alembic upgrade head' ]
      envVars: [ { name: 'APP_ENV', value: environmentName == 'dev' ? 'development' : environmentName } ]
      secretRefs: [
        {
          name: 'database-url-${replace(_dbFor(t), '_dev', '')}'
          keyVaultUrl: '${kvUri}secrets/database-url-${replace(_dbFor(t), '_dev', '')}'
          envName: 'DATABASE_URL'
        }
      ]
    }
  }
]

// ---- scheduled source-sync jobs (cron -> authenticated internal POST) ----
var scheduledJobs = concat(
  [
    { name: 'recruitment-sync-job', image: 'recruitment-api', cron: '0 */6 * * *', url: 'http://recruitment-api/api/recruitment/internal/scheduled-sync', timeout: 1800 }
    { name: 'talent-reconcile-job', image: 'talent-api', cron: '15 */6 * * *', url: 'http://talent-api/api/talent/internal/recruitment/reconcile', timeout: 900 }
  ],
  deployBirthday ? [
    { name: 'people-sync-job', image: 'people-api', cron: '0 5 * * *', url: 'http://people-api/api/people/internal/scheduled-sync', timeout: 1800 }
    { name: 'birthday-scan-job', image: 'birthday-api', cron: '30 5 * * *', url: 'http://birthday-api/api/birthday/internal/run-daily-scan', timeout: 900 }
  ] : []
)

module syncJobs 'modules/job.bicep' = [
  for j in scheduledJobs: {
    name: 'job-${j.name}'
    dependsOn: [ uamiAcrPull ]
    params: {
      name: j.name
      image: imageRef(j.image, imageRegistryLoginServer, imageDigests, imageTag)
      managedEnvironmentId: cae.id
      acrLoginServer: imageRegistryLoginServer
      userAssignedIdentityId: identity.outputs.id
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

// ---- outputs ----------------------------------------------------------
output shellWebFqdn string = 'https://shell-web.${envDomain}'
output talentPortalFqdn string = 'https://talentflow-portal-web.${envDomain}'
output supplierPortalFqdn string = deployBirthday ? 'https://birthday-supplier-web.${envDomain}' : ''
