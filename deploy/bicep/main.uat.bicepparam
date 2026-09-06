using './main.bicep'

// DijiOne UAT workloads. SKELETON. Same immutable digest as DEV — promoted,
// never rebuilt (deploy/promote.sh dev uat).
param environmentName = 'uat'
param location = 'southeastasia'

// Same shared non-prod registry as DEV.
param imageRegistryLoginServer = 'crdijionenonprod.azurecr.io'
param imageRegistryName = 'crdijionenonprod'
param imageRegistryResourceGroup = 'rg-dijione-shared'

param imageDigests = {}
param imageTag = 'REPLACED_AT_DEPLOY'

param deployBirthday = true
param deployCommercial = false

// Lean UAT: all services scale to zero; ceiling of 2.
param containerCpu = '0.25'
param containerMemory = '0.5Gi'
param minReplicas = {}
param maxReplicasDefault = 2
param maxReplicasOverrides = {}
