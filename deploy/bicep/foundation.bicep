// DijiOne — Azure FOUNDATION for one environment (DEV / UAT / PROD).
//
//   az deployment group create -g rg-dijione-<env> \
//     -f deploy/bicep/foundation.bicep -p deploy/bicep/foundation.<env>.bicepparam \
//     -p pgAdminPassword=<generated>
//
// Creates the shared, long-lived infrastructure: VNet + private DNS (for
// private PostgreSQL), Log Analytics, Key Vault (EMPTY — no secret values),
// PostgreSQL Flexible Server, and the Container Apps Environment.
//
// Then deploy/init-secrets.sh writes the real Key Vault secret values, and
// deploy/bicep/main.bicep deploys the Container Apps + Jobs that reference
// them. See deploy/README.md for the full runbook and
// docs/platform/release-pipeline.md for the lifecycle.
//
// The container REGISTRY is NOT created here — it is a one-time
// `az deployment group create -f modules/acr.bicep` (crdijionenonprod in
// rg-dijione-shared for DEV+UAT; crdijioneprod for PROD).

targetScope = 'resourceGroup'

@description('dev | uat | prod — used in resource names / tags.')
param environmentName string = 'dev'

@description('Azure region.')
param location string = 'southeastasia'

@description('PostgreSQL admin password. Passed at deploy time, never stored in a param file.')
@secure()
param pgAdminPassword string

@description('Deploy DijiBirthday databases (people_<env>, birthday_<env>).')
param deployBirthday bool = true

@description('Deploy the commercial_<env> database.')
param deployCommercial bool = false

@description('Deploy the Diji On-site onsite_<env> database. people_<env> is deployed whenever DijiBirthday or Diji On-site is.')
param deployOnsite bool = false

var deployPeople = deployBirthday || deployOnsite

@description('PostgreSQL networking. private = VNet integration (default, all envs). public = escape hatch only.')
@allowed([ 'public', 'private' ])
param pgNetworkMode string = 'private'

@description('VNet address space (only used when pgNetworkMode == private). One /21 per environment, no peering.')
param vnetCidr string = '10.60.0.0/21'
param acaSubnetCidr string = '10.60.0.0/23'
param pgSubnetCidr string = '10.60.4.0/27'

@description('PostgreSQL sizing — lean by default (Amendment 8).')
param postgresSku string = 'Standard_B1ms'
param postgresTier string = 'Burstable'
param postgresStorageGb int = 32
param backupRetentionDays int = 7
@allowed([ 'Disabled', 'ZoneRedundant', 'SameZone' ])
param postgresHaMode string = 'Disabled'

@description('Log Analytics retention (days) and daily ingest cap (GB, string — "-1" = no cap).')
param logRetentionDays int = 30
param logDailyCapGb string = '0.3'

var tags = {
  platform: 'dijione'
  env: environmentName
  managedBy: 'bicep'
}

var lawName = 'law-dijione-${environmentName}'
var kvName = 'kv-dijione-${environmentName}'
var pgName = 'psql-dijione-${environmentName}'
var caeName = 'cae-dijione-${environmentName}'

// Logical DB-owning domain keys — environment-independent. The actual
// per-environment database name is always derived as '<key>_${environmentName}'
// below, never hardcoded to a single environment (this was the DEV-leak bug:
// these used to be literal 'platform_dev' etc. regardless of environmentName,
// so a UAT/PROD foundation deployment silently created *_dev databases on
// its own Postgres server). init-secrets.sh's DBS mapping must stay in sync
// with this same '<key>_${environmentName}' pattern.
var dbDomainKeys = concat(
  [ 'platform', 'talent', 'recruitment' ],
  deployPeople ? [ 'people' ] : [],
  deployBirthday ? [ 'birthday' ] : [],
  deployCommercial ? [ 'commercial' ] : [],
  deployOnsite ? [ 'onsite' ] : []
)
var databases = map(dbDomainKeys, key => '${key}_${environmentName}')

// Key Vault secret NAMES (contract only — values written by init-secrets.sh).
// database-url-<domain> stays environment-NEUTRAL by design (main.bicep looks
// up the same secret name in every environment; only the secret VALUE differs
// per environment, written by init-secrets.sh from the resolved per-env
// PostgreSQL FQDN + this same '<key>_${environmentName}' database name).
// jwt-<env>-secret is deliberately environment-SPECIFIC — each environment
// gets its own independently-generated signing secret, never shared.
var kvSecretNamesCore = [
  'jwt-${environmentName}-secret'
  'internal-service-secret'
  'external-session-jwt-secret'
  'database-url-platform'
  'database-url-talent'
  'database-url-recruitment'
]
var kvSecretNames = concat(
  kvSecretNamesCore,
  deployPeople ? [ 'database-url-people' ] : [],
  deployBirthday ? [ 'database-url-birthday' ] : [],
  deployCommercial ? [ 'database-url-commercial' ] : [],
  deployOnsite ? [ 'database-url-onsite' ] : []
)

// ---- network (private PostgreSQL) --------------------------------------
module network 'modules/network.bicep' = if (pgNetworkMode == 'private') {
  name: 'network'
  params: {
    environmentName: environmentName
    location: location
    tags: tags
    vnetCidr: vnetCidr
    acaSubnetCidr: acaSubnetCidr
    pgSubnetCidr: pgSubnetCidr
  }
}

// ---- observability ----------------------------------------------------
module observability 'modules/observability.bicep' = {
  name: 'observability'
  params: {
    name: lawName
    location: location
    tags: tags
    retentionInDays: logRetentionDays
    dailyQuotaGb: logDailyCapGb
  }
}

// ---- key vault (empty — no secret values) ---------------------------
module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: { name: kvName, location: location, tags: tags, secretNames: kvSecretNames }
}

// ---- postgres -------------------------------------------------------
module postgres 'modules/postgres.bicep' = {
  name: 'postgres'
  params: {
    name: pgName
    location: location
    tags: tags
    administratorPassword: pgAdminPassword
    databases: databases
    skuName: postgresSku
    skuTier: postgresTier
    storageSizeGB: postgresStorageGb
    backupRetentionDays: backupRetentionDays
    haMode: postgresHaMode
    networkMode: pgNetworkMode
    delegatedSubnetId: pgNetworkMode == 'private' ? network!.outputs.pgSubnetId : ''
    privateDnsZoneId: pgNetworkMode == 'private' ? network!.outputs.pgPrivateDnsZoneId : ''
  }
}

// ---- container apps environment -----------------------------------
module cae 'modules/containerapp-env.bicep' = {
  name: 'cae'
  params: {
    name: caeName
    location: location
    tags: tags
    logAnalyticsCustomerId: observability.outputs.customerId
    logAnalyticsSharedKey: observability.outputs.primarySharedKey
    infrastructureSubnetId: pgNetworkMode == 'private' ? network!.outputs.acaSubnetId : ''
  }
}

// ---- outputs (consumed by main.bicep + init-secrets.sh + deploy.sh) --
output caeId string = cae.outputs.id
output caeName string = cae.outputs.name
output caeDefaultDomain string = cae.outputs.defaultDomain
output keyVaultName string = keyvault.outputs.name
output keyVaultUri string = keyvault.outputs.uri
output expectedSecretNames array = keyvault.outputs.expectedSecretNames
output postgresServerName string = postgres.outputs.serverName
output postgresFqdn string = postgres.outputs.fqdn
