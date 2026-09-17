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

// SECURITY: pinned explicitly (never left to main.bicep's default, which is
// 'dev') — an unset authMode/supplierAuthMode here would silently deploy
// UAT with the passwordless DEV_IDENTITY_MODE persona switcher exposed
// instead of real Microsoft Entra ID sign-in. Found during the
// PLATFORM_JWT_SECRET environment-cleanliness audit; see main.dev.bicepparam
// for the sibling DEV wiring.
//
// UAT's own Entra app registrations now exist (confirmed values, no secrets
// here — client secrets live only in kv-dijione-uat as entra-client-secret-uat
// / birthday-supplier-entra-secret-uat, written by init-secrets.sh, never in
// source control):
//   dijione-uat                     (internal DijiOne sign-in)
//   dijione-birthday-supplier-uat   (Birthday Supplier Portal B2B guest sign-in)
param authMode = 'entra'
param entraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param entraClientId = 'f7455106-f91b-42e0-9a6a-2f3dc256727c'
param publicBaseUrl = 'https://shell-web.mangofield-96838df7.southeastasia.azurecontainerapps.io'

param supplierAuthMode = 'entra'
param supplierEntraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param supplierEntraClientId = 'bdd98d91-1fe9-4b81-b621-96fa14d2e9b5'
param supplierPublicBaseUrl = 'https://birthday-supplier-web.mangofield-96838df7.southeastasia.azurecontainerapps.io'
