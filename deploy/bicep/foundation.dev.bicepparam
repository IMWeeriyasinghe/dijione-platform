using './foundation.bicep'

// DijiOne DEV foundation. `pgAdminPassword` is supplied at deploy time
// (deploy/deploy.sh / an operator) — never committed here.
param environmentName = 'dev'
param location = 'southeastasia'
param pgAdminPassword = ''

// Full platform incl. DijiBirthday for the first DEV (confirmed).
param deployBirthday = true
param deployCommercial = false
param deployOnsite = true

// Private PostgreSQL via VNet integration (Amendment 2). One /21 per env, no peering.
param pgNetworkMode = 'private'
param vnetCidr = '10.60.0.0/21'
param acaSubnetCidr = '10.60.0.0/23'
param pgSubnetCidr = '10.60.4.0/27'

// Lean DEV database (Amendment 8): smallest burstable SKU, min storage,
// min backup retention, HA off. Parked outside working sessions (park-dev.sh).
param postgresSku = 'Standard_B1ms'
param postgresTier = 'Burstable'
param postgresStorageGb = 32
param backupRetentionDays = 7
param postgresHaMode = 'Disabled'

// Lean DEV logging: min retention, tight daily cap.
param logRetentionDays = 30
param logDailyCapGb = '0.3'
