using './main.bicep'

// DijiOne DEV workloads. Run AFTER foundation.dev + init-secrets.sh.
// `imageDigests` is injected at deploy time from the build record; `imageTag`
// is only for a first bring-up before the pipeline records digests.
param environmentName = 'dev'
param location = 'southeastasia'

// Shared non-prod registry (DEV + UAT), lives in rg-dijione-shared.
param imageRegistryLoginServer = 'crdijionenonprod.azurecr.io'
param imageRegistryName = 'crdijionenonprod'
param imageRegistryResourceGroup = 'rg-dijione-shared'

// Digest-first. Leave empty + pass imageTag for the very first bring-up.
param imageDigests = {}
param imageTag = 'REPLACED_AT_DEPLOY'

param deployBirthday = true
param deployCommercial = false

// Lean DEV (Amendment 8): smallest container size; EVERY service scales to
// zero (minReplicas empty => 0); ceiling of 1. Cold start is acceptable in DEV.
param containerCpu = '0.25'
param containerMemory = '0.5Gi'
param minReplicas = {}
param maxReplicasDefault = 1
param maxReplicasOverrides = {}
