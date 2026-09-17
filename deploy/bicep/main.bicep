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

@description('DEV only: create a Manual bootstrap-identity job that seeds the 5 staff dev-login personas (no business data). UAT/PROD create real users via the Admin Center.')
param seedDevIdentities bool = false

@description('Create a Manual bootstrap-talent-clients job that runs talent-api/scripts/seed.py — it pulls the canonical client directory from platform-api (GET /api/platform/internal/clients) and creates ONLY the talent-api clients extension rows (platform_client_id + name) in this environment, idempotent, no business data. Needed for the governed DTC tag -> Client resolution.')
param seedTalentClientExtensions bool = false

@description('Internal identity mode for platform-api. "dev" = the passwordless persona switcher; "entra" = real Microsoft Entra ID OIDC (Authorization Code + PKCE). "entra" also requires entraTenantId, entraClientId, publicBaseUrl, and the entra-client-secret-<env> Key Vault secret.')
@allowed([ 'dev', 'entra' ])
param authMode string = 'dev'

@description('Entra directory (tenant) id. Only used when authMode == entra.')
param entraTenantId string = ''

@description('Application (client) id of the per-environment DijiOne Entra app registration. Only used when authMode == entra.')
param entraClientId string = ''

@description('Public HTTPS origin of shell-web for this environment, e.g. https://shell-web.<env-domain>. Backs the Entra redirect URI and the front-channel logout redirect.')
param publicBaseUrl string = ''

@description('recruitment-api provider mode. "mock" = MockLeverClient; "live" = the GET-only LiveLeverClient, which also needs the lever-api-key-<env> Key Vault secret. Lever is READ-ONLY by construction (CLAUDE.md §60).')
@allowed([ 'mock', 'live' ])
param recruitmentIntegrationsMode string = 'mock'

@description('people-api provider mode. "mock" = MockBambooHrClient; "live" = the read-only live client, which also needs the bamboohr-api-key-<env> Key Vault secret and bamboohrSubdomain. Never writes to BambooHR.')
@allowed([ 'mock', 'live' ])
param peopleIntegrationsMode string = 'mock'

@description('BambooHR company subdomain (the <sub> in api.bamboohr.com/api/gateway.php/<sub>/v1). Only used when peopleIntegrationsMode == live.')
param bamboohrSubdomain string = ''

@description('birthday-api People-source mode. "mock" = MockEmployeeSource; "live" = PeopleApiEmployeeSource (consumes people-api over HTTP; birthday-api still holds NO BambooHR credential and no employee mirror). EMAIL_SENDING_MODE stays mock regardless (Phase 1 §1.9).')
@allowed([ 'mock', 'live' ])
param birthdayIntegrationsMode string = 'mock'

@description('Birthday Supplier Portal auth. "dev" = the seeded SupplierUser persona picker; "entra" = real Microsoft Entra ID B2B guest sign-in (Auth Code + PKCE) via birthday-api, which also needs the birthday-supplier-entra-secret-<env> Key Vault secret. Independent of the internal DijiOne authMode.')
@allowed([ 'dev', 'entra' ])
param supplierAuthMode string = 'dev'

@description('Entra directory (tenant) id for supplier B2B guest sign-in. Only used when supplierAuthMode == entra. Same directory as the internal tenant.')
param supplierEntraTenantId string = ''

@description('Application (client) id of the per-environment dijione-birthday-supplier Entra app registration. Only used when supplierAuthMode == entra.')
param supplierEntraClientId string = ''

@description('Public HTTPS origin of birthday-supplier-web, e.g. https://birthday-supplier-web.<env-domain>. Backs the supplier Entra redirect URI.')
param supplierPublicBaseUrl string = ''

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
// `db` is a LOGICAL domain key (e.g. 'platform'), never a physical,
// environment-baked database name. It is used only to build the
// environment-NEUTRAL Key Vault secret name 'database-url-<key>' below
// (_apiSecretRefs/_dbFor) — the secret's VALUE, written by
// init-secrets.sh, is what actually points at this environment's real
// '<key>_${environmentName}' database. Previously this field held a
// literal '<key>_dev' string regardless of environmentName, which is the
// root cause of UAT/PROD deployments resolving DEV-named databases.
var coreServices = [
  { name: 'platform-api', kind: 'api', db: 'platform', external: false }
  { name: 'admin-api', kind: 'api', db: '', external: false }
  { name: 'talent-api', kind: 'api', db: 'talent', external: false }
  { name: 'recruitment-api', kind: 'api', db: 'recruitment', external: false }
  { name: 'shell-web', kind: 'web', db: '', external: true }
  { name: 'admin-web', kind: 'web', db: '', external: false }
  { name: 'talent-web', kind: 'web', db: '', external: false }
  { name: 'talentflow-portal-web', kind: 'web', db: '', external: true }
]
var birthdayServices = [
  { name: 'people-api', kind: 'api', db: 'people', external: false }
  { name: 'birthday-api', kind: 'api', db: 'birthday', external: false }
  { name: 'birthday-web', kind: 'web', db: '', external: false }
  { name: 'birthday-supplier-web', kind: 'web', db: '', external: true }
]
var commercialServices = [
  { name: 'commercial-api', kind: 'api', db: 'commercial', external: false }
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

// INTEGRATIONS_MODE is per-service (see _perServiceEnv): recruitment-api and
// people-api can be flipped to "live" independently; every other API stays
// "mock". EMAIL_SENDING_MODE stays mock platform-wide for Phase 4.
var commonApiEnv = [
  { name: 'APP_ENV', value: environmentName == 'dev' ? 'development' : environmentName }
  { name: 'EMAIL_SENDING_MODE', value: 'mock' }
  { name: 'API_CORS_ORIGINS', value: corsOrigins }
]

// Per-service configuration — internal service URLs (ACA internal DNS is
// http://<app-name>) + module modes. Declarative here so a redeploy does not
// wipe them (Bicep env is desired-state, not a merge). `AUTH_MODE=dev` on
// platform-api = the dev-login identity provider (no real Entra in DEV).
func _perServiceEnv(svc string, authMode string, entraTenantId string, entraClientId string, publicBaseUrl string, recruitmentMode string, peopleMode string, bamboohrSubdomain string, supplierAuthMode string, supplierEntraTenantId string, supplierEntraClientId string, supplierPublicBaseUrl string, birthdayMode string) array =>
  svc == 'shell-web' ? [
    { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
    { name: 'ADMIN_API_URL', value: 'http://admin-api' }
    { name: 'TALENT_API_URL', value: 'http://talent-api' }
    { name: 'BIRTHDAY_API_URL', value: 'http://birthday-api' }
    { name: 'SPARK_API_URL', value: 'http://spark-api' }
    { name: 'ADMIN_WEB_URL', value: 'http://admin-web' }
    { name: 'TALENT_WEB_URL', value: 'http://talent-web' }
    { name: 'BIRTHDAY_WEB_URL', value: 'http://birthday-web' }
    { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
  ]
  : svc == 'platform-api' ? concat(
      [
        { name: 'INTEGRATIONS_MODE', value: 'mock' }
        { name: 'AUTH_MODE', value: authMode }
        { name: 'TALENT_API_URL', value: 'http://talent-api' }
      ],
      authMode == 'entra' ? [
        { name: 'ENTRA_TENANT_ID', value: entraTenantId }
        { name: 'ENTRA_CLIENT_ID', value: entraClientId }
        { name: 'ENTRA_REDIRECT_URI', value: '${publicBaseUrl}/api/auth/callback' }
        { name: 'PUBLIC_BASE_URL', value: publicBaseUrl }
      ] : [
        { name: 'DEV_IDENTITY_MODE', value: 'true' }
      ]
    )
  : svc == 'admin-api' ? [
      { name: 'INTEGRATIONS_MODE', value: 'mock' }
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'TALENT_API_URL', value: 'http://talent-api' }
    ]
  : svc == 'talent-api' ? [
      { name: 'INTEGRATIONS_MODE', value: 'mock' }
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'RECRUITMENT_API_URL', value: 'http://recruitment-api' }
    ]
  : svc == 'recruitment-api' ? [
      { name: 'INTEGRATIONS_MODE', value: recruitmentMode }
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      { name: 'OPPORTUNITY_SYNC_LIMIT', value: '200' }
    ]
  : svc == 'people-api' ? concat(
      [
        { name: 'INTEGRATIONS_MODE', value: peopleMode }
        { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
      ],
      peopleMode == 'live' && !empty(bamboohrSubdomain) ? [
        { name: 'BAMBOOHR_SUBDOMAIN', value: bamboohrSubdomain }
      ] : []
    )
  : svc == 'birthday-api' ? concat(
      [
        { name: 'INTEGRATIONS_MODE', value: birthdayMode }
        { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
        { name: 'PEOPLE_API_URL', value: 'http://people-api' }
        // Phase 1.6 §9: people-api scales to zero in DEV; a measured cold
        // start took 23s. Deployment-visible, not a buried code constant.
        { name: 'PEOPLE_API_TIMEOUT_SECONDS', value: '30' }
        { name: 'SUPPLIER_AUTH_MODE', value: supplierAuthMode }
      ],
      supplierAuthMode == 'entra' ? [
        { name: 'SUPPLIER_ENTRA_TENANT_ID', value: supplierEntraTenantId }
        { name: 'SUPPLIER_ENTRA_CLIENT_ID', value: supplierEntraClientId }
        { name: 'SUPPLIER_ENTRA_REDIRECT_URI', value: '${supplierPublicBaseUrl}/api/auth/callback' }
        { name: 'SUPPLIER_PUBLIC_BASE_URL', value: supplierPublicBaseUrl }
      ] : []
    )
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
  : svc == 'birthday-supplier-web' ? [
      { name: 'BIRTHDAY_API_URL', value: 'http://birthday-api' }
      { name: 'SUPPLIER_PUBLIC_BASE_URL', value: supplierPublicBaseUrl }
    ]
  : svc == 'talentflow-portal-web' ? [
      { name: 'TALENT_API_URL', value: 'http://talent-api' }
    ]
  : []

// KV secret wiring per API: shared trust anchors + this service's own db url.
func _apiSecretRefs(svc string, db string, uri string, authMode string, env string, recruitmentMode string, peopleMode string, supplierAuthMode string) array => concat(
  [
    // jwt-<env>-secret: the Key Vault secret NAME is environment-specific
    // (each environment gets its own independently-generated signing
    // secret) — but the container env var name it's injected as
    // (JWT_DEV_SECRET) is a fixed application-code constant across every
    // environment, read by every service's Settings.jwt_dev_secret field.
    { name: 'jwt-${env}-secret', keyVaultUrl: '${uri}secrets/jwt-${env}-secret', envName: 'JWT_DEV_SECRET' }
    { name: 'internal-service-secret', keyVaultUrl: '${uri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' }
  ],
  svc == 'talent-api' ? [
    { name: 'external-session-jwt-secret', keyVaultUrl: '${uri}secrets/external-session-jwt-secret', envName: 'EXTERNAL_SESSION_JWT_SECRET' }
  ] : [],
  (svc == 'platform-api' && authMode == 'entra') ? [
    { name: 'entra-client-secret-${env}', keyVaultUrl: '${uri}secrets/entra-client-secret-${env}', envName: 'ENTRA_CLIENT_SECRET' }
  ] : [],
  (svc == 'recruitment-api' && recruitmentMode == 'live') ? [
    { name: 'lever-api-key-${env}', keyVaultUrl: '${uri}secrets/lever-api-key-${env}', envName: 'LEVER_API_KEY' }
  ] : [],
  (svc == 'people-api' && peopleMode == 'live') ? [
    { name: 'bamboohr-api-key-${env}', keyVaultUrl: '${uri}secrets/bamboohr-api-key-${env}', envName: 'BAMBOOHR_API_KEY' }
  ] : [],
  (svc == 'birthday-api' && supplierAuthMode == 'entra') ? [
    { name: 'birthday-supplier-entra-secret-${env}', keyVaultUrl: '${uri}secrets/birthday-supplier-entra-secret-${env}', envName: 'SUPPLIER_ENTRA_CLIENT_SECRET' }
  ] : [],
  // `db` is already the neutral logical domain key ('platform', 'talent',
  // …) — no environment-suffix replacement needed. The secret NAME stays
  // identical across DEV/UAT/PROD; only its VALUE (written by
  // init-secrets.sh) differs per environment.
  db == '' ? [] : [
    { name: 'database-url-${db}', keyVaultUrl: '${uri}secrets/database-url-${db}', envName: 'DATABASE_URL' }
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
      envVars: concat(s.kind == 'api' ? commonApiEnv : [], _perServiceEnv(s.name, authMode, entraTenantId, entraClientId, publicBaseUrl, recruitmentIntegrationsMode, peopleIntegrationsMode, bamboohrSubdomain, supplierAuthMode, supplierEntraTenantId, supplierEntraClientId, supplierPublicBaseUrl, birthdayIntegrationsMode))
      secretRefs: s.kind == 'api' ? _apiSecretRefs(s.name, s.db, kvUri, authMode, environmentName, recruitmentIntegrationsMode, peopleIntegrationsMode, supplierAuthMode) : []
      // ^ lever-api-key-<env> / bamboohr-api-key-<env> attach only when the
      //   matching *IntegrationsMode == 'live'
    }
  }
]

// ---- migration jobs (one per DB-owning service, on its OWN image) --------
var migrateTargets = concat(
  [ 'platform-api', 'talent-api', 'recruitment-api' ],
  deployBirthday ? [ 'people-api', 'birthday-api' ] : [],
  deployCommercial ? [ 'commercial-api' ] : []
)

// Same logical domain keys as the service catalogue's own `db` field above
// — kept as an explicit mapping (not derived from `services`) because
// migrateTargets is service-name-only, but never environment-suffixed;
// _apiSecretRefs's db == '' branch is why platform-api/talent-api/etc.
// can't just reuse `services[].db` directly without an extra lookup.
func _dbFor(svc string) string =>
  svc == 'platform-api' ? 'platform'
    : svc == 'talent-api' ? 'talent'
    : svc == 'recruitment-api' ? 'recruitment'
    : svc == 'people-api' ? 'people'
    : svc == 'birthday-api' ? 'birthday'
    : 'commercial'

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
          name: 'database-url-${_dbFor(t)}'
          keyVaultUrl: '${kvUri}secrets/database-url-${_dbFor(t)}'
          envName: 'DATABASE_URL'
        }
      ]
    }
  }
]

// ---- DEV identity bootstrap (Manual) ------------------------------------
// Seeds the 5 staff dev-login personas + their platform/module role
// assignments (platform-api/scripts/seed.py --identity-only). NO business
// data, NO canonical Client set (that is migration-owned). DEV only — UAT/PROD
// create real users via the Admin Center. Run once after migrate-platform-api.
module bootstrapIdentityJob 'modules/job.bicep' = if (seedDevIdentities) {
  name: 'job-bootstrap-identity'
  dependsOn: [ uamiAcrPull ]
  params: {
    name: 'bootstrap-identity'
    image: imageRef('platform-api', imageRegistryLoginServer, imageDigests, imageTag)
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: identity.outputs.id
    triggerType: 'Manual'
    replicaTimeout: 600
    location: location
    tags: tags
    command: [ '/bin/sh', '-c' ]
    args: [ 'python scripts/seed.py --identity-only' ]
    envVars: [ { name: 'APP_ENV', value: environmentName == 'dev' ? 'development' : environmentName } ]
    secretRefs: [
      { name: 'database-url-platform', keyVaultUrl: '${kvUri}secrets/database-url-platform', envName: 'DATABASE_URL' }
    ]
  }
}

// ---- TalentFlow client-extension bootstrap (Manual) -------------------
// Runs talent-api/scripts/seed.py: fetches the canonical client directory
// from platform-api and creates ONLY the talent-api clients extension rows
// (platform_client_id + name) in this environment's own talent_${environmentName}
// database. Idempotent, no TalentRequest/Candidate/etc. Enables the governed
// `DTC - <name>` tag to resolve to a Client (PostingClientMapping VERIFIED).
// Run after migrate-talent-api + bootstrap-identity/migrations have
// populated this environment's own platform_${environmentName}.client table.
module bootstrapTalentClientsJob 'modules/job.bicep' = if (seedTalentClientExtensions) {
  name: 'job-bootstrap-talent-clients'
  dependsOn: [ uamiAcrPull ]
  params: {
    name: 'bootstrap-talent-clients'
    image: imageRef('talent-api', imageRegistryLoginServer, imageDigests, imageTag)
    managedEnvironmentId: cae.id
    acrLoginServer: imageRegistryLoginServer
    userAssignedIdentityId: identity.outputs.id
    triggerType: 'Manual'
    replicaTimeout: 600
    location: location
    tags: tags
    command: [ '/bin/sh', '-c' ]
    args: [ 'python scripts/seed.py' ]
    envVars: [
      { name: 'APP_ENV', value: environmentName == 'dev' ? 'development' : environmentName }
      { name: 'PLATFORM_API_URL', value: 'http://platform-api' }
    ]
    secretRefs: [
      { name: 'database-url-talent', keyVaultUrl: '${kvUri}secrets/database-url-talent', envName: 'DATABASE_URL' }
      { name: 'internal-service-secret', keyVaultUrl: '${kvUri}secrets/internal-service-secret', envName: 'INTERNAL_SERVICE_SECRET' }
      { name: 'jwt-${environmentName}-secret', keyVaultUrl: '${kvUri}secrets/jwt-${environmentName}-secret', envName: 'JWT_DEV_SECRET' }
    ]
  }
}

// ---- scheduled source-sync jobs (cron -> authenticated internal POST) ----
var scheduledJobs = concat(
  [
    { name: 'recruitment-sync-job', image: 'recruitment-api', cron: '0 */6 * * *', url: 'http://recruitment-api/api/recruitment/internal/scheduled-sync', timeout: 1800 }
    { name: 'talent-reconcile-job', image: 'talent-api', cron: '15 */6 * * *', url: 'http://talent-api/api/talent/internal/recruitment/reconcile', timeout: 900 }
  ],
  deployBirthday ? [
    // ACA Job cron is UTC. These are Asia/Colombo (UTC+5:30) — People
    // refreshes ~00:00 Colombo, detection ~00:30 (right after), the
    // attention digest ~02:00 (Phase 1.5 §B).
    { name: 'people-sync-job', image: 'people-api', cron: '30 18 * * *', url: 'http://people-api/api/people/internal/scheduled-sync', timeout: 1800 }
    { name: 'birthday-scan-job', image: 'birthday-api', cron: '0 19 * * *', url: 'http://birthday-api/api/birthday/internal/run-daily-scan', timeout: 900 }
    // Phase 1 §1.2/§1.3/§1.5: attention/SLA + detection-health digest (daily),
    // and outbound-email backoff retry + inbound supplier-email poll (~10 min).
    { name: 'birthday-attention-job', image: 'birthday-api', cron: '30 20 * * *', url: 'http://birthday-api/api/birthday/internal/run-attention', timeout: 600 }
    { name: 'birthday-comms-job', image: 'birthday-api', cron: '*/10 * * * *', url: 'http://birthday-api/api/birthday/internal/run-comms', timeout: 600 }
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
