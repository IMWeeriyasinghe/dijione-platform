using './foundation.bicep'

// DijiOne UAT foundation. SKELETON — exercised only when UAT is provisioned.
// Same architecture as DEV; different address space + slightly higher log cap.
param environmentName = 'uat'
param location = 'southeastasia'
param pgAdminPassword = ''

param deployBirthday = true
param deployCommercial = false

param pgNetworkMode = 'private'
param vnetCidr = '10.61.0.0/21'
param acaSubnetCidr = '10.61.0.0/23'
param pgSubnetCidr = '10.61.4.0/27'

// Lean UAT database — parked outside test windows (park-uat.sh).
param postgresSku = 'Standard_B1ms'
param postgresTier = 'Burstable'
param postgresStorageGb = 32
param backupRetentionDays = 7
param postgresHaMode = 'Disabled'

param logRetentionDays = 30
param logDailyCapGb = '0.5'
