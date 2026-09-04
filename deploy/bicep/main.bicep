// DijiOne — Azure environment (DEV / UAT / PROD).
// Deploy: az deployment group create -g rg-dijione-<env> \
//           -f deploy/bicep/main.bicep -p deploy/bicep/main.<env>.bicepparam \
//           -p imageTag=<gitsha> -p pgAdminPassword=<...>
//
// Nothing environment-specific is hard-coded here — see main.<env>.bicepparam.
// See deploy/README.md for the full runbook and the PostgreSQL networking
// comparison, and docs/platform/hosted-dev-data.md for the migrate / seed /
// business-data split.

targetScope = 'resourceGroup'

@description('dev | uat | prod — used only in resource names / tags.')
param environmentName string = 'dev'

@description('Azure region. DijiOne DEV approved region: southeastasia.')
param location string = 'southeastasia'

@description('Immutable image tag to deploy — a git SHA. Build once, promote the same tag.')
param imageTag string

@description('ACR login server, e.g. crdijionedev.azurecr.io. The registry itself is created here.')
param acrName string = 'crdijione${environmentName}'

@description('PostgreSQL admin password. Passed at deploy time, never stored in a param file.')
@secure()
param pgAdminPassword string

@description('Deploy DijiBirthday (people-api, birthday-api, birthday-web, birthday-supplier-web + 2 databases + 2 jobs).')
param deployBirthday bool = true

@description('Deploy the commercial-api skeleton + commercial_dev.')
param deployCommercial bool = false

@description('PostgreSQL networking: public (DEV exception) or private (UAT/PROD target). See postgres.bicep.')
@allowed([ 'public', 'private' ])
param pgNetworkMode string = 'public'
param pgDelegatedSubnetId string = ''
param pgPrivateDnsZoneId string = ''

@description('Per-workload replica floors. talent-api = 1 for DEV acceptance responsiveness (cost lever: set 0 later).')
param minReplicas object = {
  'shell-web': 1
  'platform-api': 1
  'talent-api': 1
}

var tags = {
  platform: 'dijione'
  env: environmentName
  managedBy: 'bicep'
}

// ---- names ---------------------------------------------------------------
var lawName = 'law-dijione-${environmentName}'
var kvName = 'kv-dijione-${environmentName}'
var pgName = 'psql-dijione-${environmentName}'
var caeName = 'cae-dijione-${environmentName}'

// ---- service catalogue ------------------------------------------------------
// One row per Container App. `kind` drives target port; `db` names the logical
// database (empty = none); `external` marks the 3 public apps.
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

var databases = concat(
  [ 'platform_dev', 'talent_dev', 'recruitment_dev' ],
  deployBirthday ? [ 'people_dev', 'birthday_dev' ] : [],
  deployCommercial ? [ 'commercial_dev' ] : []
)

// Secrets held in Key Vault (values set out-of-band by deploy.sh).
var kvSecretNamesCore = [
  'jwt-dev-secret'
  'internal-service-secret'
  'external-session-jwt-secret'
  'database-url-platform'
  'database-url-talent'
  'database-url-recruitment'
]
var kvSecretNames = concat(
  kvSecretNamesCore,
  deployBirthday ? [ 'database-url-people', 'database-url-birthday' ] : [],
  deployCommercial ? [ 'database-url-commercial' ] : []
)

// ---- shared infra -------------------------------------------------------
module observability 'modules/observability.bicep' = {
  name: 'observability'
  params: { name: lawName, location: location, tags: tags }
}

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: lawName
}

module acr 'modules/acr.bicep' = {
  name: 'acr'
  params: { name: acrName, location: location, tags: tags }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: { name: kvName, location: location, tags: tags, secretNames: kvSecretNames }
}

module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: pgName
    location: location
    tags: tags
    administratorPassword: pgAdminPassword
    databases: databases
    networkMode: pgNetworkMode
    delegatedSubnetId: pgDelegatedSubnetId
    privateDnsZoneId: pgPrivateDnsZoneId
  }
}

module cae 'modules/containerapp-env.bicep' = {
  name: 'cae'
  params: {
    name: caeName
    location: location
    tags: tags
    logAnalyticsCustomerId: observability.outputs.customerId
    logAnalyticsSharedKey: law.listKeys().primarySharedKey
  }
}

// Deterministic external FQDNs (ACA: <app>.<env-default-domain>) so
// API_CORS_ORIGINS is set in one pass, no read-back required.
var envDomain = cae.outputs.defaultDomain
var corsOrigins = join([
  'https://shell-web.${envDomain}'
  'https://talentflow-portal-web.${envDomain}'
  deployBirthday ? 'https://birthday-supplier-web.${envDomain}' : ''
], ',')

// Common env for every backend.
var commonApiEnv = [
  { name: 'APP_ENV', value: environmentName == 'dev' ? 'development' : environmentName }
  { name: 'INTEGRATIONS_MODE', value: 'mock' }
  { name: 'EMAIL_SENDING_MODE', value: 'mock' }
  { name: 'API_CORS_ORIGINS', value: corsOrigins }
]

var kvUri = keyvault.outputs.uri

// ---- the apps --------------------------------------------------------------
@batchSize(4)
module apps 'modules/containerapp.bicep' = [
  for s in services: {
    name: 'app-${s.name}'
    params: {
      name: s.name
      image: '${acr.outputs.loginServer}/dijione/${s.name}:${imageTag}'
      managedEnvironmentId: cae.outputs.id
      acrLoginServer: acr.outputs.loginServer
      acrName: acr.outputs.name
      keyVaultName: keyvault.outputs.name
      targetPort: s.kind == 'api' ? 8000 : 3000
      external: s.external
      minReplicas: minReplicas[?s.name] ?? 0
      maxReplicas: s.name == 'shell-web' || s.name == 'platform-api' || s.name == 'talent-api' ? 3 : 2
      location: location
      tags: tags
      // Per-service env is layered in a second pass by deploy.sh
      // (`az containerapp update --set-env-vars`) — see deploy/README.md
      // §"Per-service env". This module wires the common env + KV secrets.
      envVars: s.kind == 'api' ? commonApiEnv : []
      secretRefs: s.kind == 'api' ? _apiSecretRefs(s.name, s.db, kvUri) : []
    }
  }
]

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

// ---- jobs ---------------------------------------------------------------
// Migration jobs: ONE per DB-owning service, each on its OWN image
// (migration-execution ownership stays with the schema owner — Amendment 4).
var migrateTargets = concat(
  [ 'platform-api', 'talent-api', 'recruitment-api' ],
  deployBirthday ? [ 'people-api', 'birthday-api' ] : [],
  deployCommercial ? [ 'commercial-api' ] : []
)

module migrateJobs 'modules/job.bicep' = [
  for t in migrateTargets: {
    name: 'job-migrate-${t}'
    params: {
      name: 'migrate-${t}'
      image: '${acr.outputs.loginServer}/dijione/${t}:${imageTag}'
      managedEnvironmentId: cae.outputs.id
      acrLoginServer: acr.outputs.loginServer
      acrName: acr.outputs.name
      keyVaultName: keyvault.outputs.name
      triggerType: 'Manual'
      replicaTimeout: 900
      location: location
      tags: tags
      command: [ '/bin/sh', '-c' ]
      args: [ 'python -m alembic upgrade head' ]
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

func _dbFor(svc string) string =>
  svc == 'platform-api' ? 'platform_dev'
    : svc == 'talent-api' ? 'talent_dev'
    : svc == 'recruitment-api' ? 'recruitment_dev'
    : svc == 'people-api' ? 'people_dev'
    : svc == 'birthday-api' ? 'birthday_dev'
    : 'commercial_dev'

// Scheduled source-sync jobs (cron -> authenticated internal POST).
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
    params: {
      name: j.name
      image: '${acr.outputs.loginServer}/dijione/${j.image}:${imageTag}'
      managedEnvironmentId: cae.outputs.id
      acrLoginServer: acr.outputs.loginServer
      acrName: acr.outputs.name
      keyVaultName: keyvault.outputs.name
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

// Least-privilege RBAC (AcrPull + Key Vault Secrets User for each identity)
// is created inside modules/containerapp.bicep and modules/job.bicep — a
// role-assignment resource name must be a start-time-known guid(), which
// rules out doing it here off module outputs.

// ---- outputs ----------------------------------------------------------
output shellWebFqdn string = 'https://shell-web.${envDomain}'
output talentPortalFqdn string = 'https://talentflow-portal-web.${envDomain}'
output supplierPortalFqdn string = deployBirthday ? 'https://birthday-supplier-web.${envDomain}' : ''
output acrLoginServer string = acr.outputs.loginServer
output keyVaultUri string = kvUri
output postgresFqdn string = postgres.outputs.fqdn
