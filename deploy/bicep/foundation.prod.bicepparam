using './foundation.bicep'

// DijiOne PROD foundation. SKELETON — exercised only when PROD is provisioned,
// in its OWN production subscription (docs/platform/azure-subscriptions.md).
// Same architecture + Bicep as DEV/UAT; production-appropriate starting size.
param environmentName = 'prod'
param location = 'southeastasia'
param pgAdminPassword = ''

param deployBirthday = true
param deployCommercial = false

param pgNetworkMode = 'private'
param vnetCidr = '10.62.0.0/21'
param acaSubnetCidr = '10.62.0.0/23'
param pgSubnetCidr = '10.62.4.0/27'

// Initial PROD database (Amendment 8): still smallest burstable SKU, larger
// storage + longer backup, HA OFF initially (business-accepted). Raise SKU /
// enable ZoneRedundant HA only on a measured trigger — see the scaling-trigger
// table in the plan / docs/platform/deployment-topology.md.
param postgresSku = 'Standard_B1ms'
param postgresTier = 'Burstable'
param postgresStorageGb = 64
param backupRetentionDays = 14
param postgresHaMode = 'Disabled'

// PROD keeps more operational telemetry, still capped.
param logRetentionDays = 90
param logDailyCapGb = '2'
