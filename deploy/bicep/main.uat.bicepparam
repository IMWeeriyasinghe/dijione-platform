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
// for the fully-wired reference (DEV itself already runs authMode=entra).
// entraTenantId / entraClientId / publicBaseUrl and the supplier equivalents
// are intentionally left unset here — they require UAT's own Entra app
// registrations (dijione-uat, dijione-birthday-supplier-uat), a human
// Entra-tenant action outside this repository's authority (CLAUDE.md). Until
// those are provisioned and these four params are filled in (plus the
// entra-client-secret-uat / birthday-supplier-entra-secret-uat Key Vault
// secrets), a UAT deployment attempt correctly FAILS rather than silently
// falling back to DEV identity mode.
param authMode = 'entra'
param supplierAuthMode = 'entra'
