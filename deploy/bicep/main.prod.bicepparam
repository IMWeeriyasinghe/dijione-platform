using './main.bicep'

// DijiOne PROD workloads. SKELETON — own production subscription.
// The EXACT digest validated in UAT, imported into crdijioneprod
// (deploy/promote.sh uat prod) and deployed here. Never rebuilt.
param environmentName = 'prod'
param location = 'southeastasia'

// Isolated production registry, in rg-dijione-prod.
param imageRegistryLoginServer = 'crdijioneprod.azurecr.io'
param imageRegistryName = 'crdijioneprod'
param imageRegistryResourceGroup = 'rg-dijione-prod'

param imageDigests = {}
param imageTag = 'REPLACED_AT_DEPLOY'

param deployBirthday = true
param deployCommercial = false

// Initial PROD (Amendment 8): smallest validated container size; ONLY the JWT
// issuer + the entry point stay warm, everything else scales to zero. Raise
// per the scaling-trigger table, not preemptively.
param containerCpu = '0.25'
param containerMemory = '0.5Gi'
param minReplicas = {
  'platform-api': 1
  'shell-web': 1
}
param maxReplicasDefault = 2
param maxReplicasOverrides = {
  'platform-api': 3
  'shell-web': 3
}
