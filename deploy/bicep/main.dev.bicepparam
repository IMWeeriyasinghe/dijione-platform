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
param seedDevIdentities = true
// Populate talent_dev.clients extension rows from the canonical directory so
// the governed DTC tags resolve (PostingClientMapping VERIFIED).
param seedTalentClientExtensions = true

// Phase 4: real Microsoft Entra ID internal authentication for hosted DEV.
// authMode=entra disables the passwordless persona switcher (platform-api
// /api/auth/dev-* -> 404) and turns on the OIDC Authorization Code + PKCE
// flow. Requires the `entra-client-secret-dev` Key Vault secret (client
// secret of the `dijione-dev` app registration, appId below). The dev
// personas stay in the database for an explicit fallback: flip authMode
// back to 'dev' and redeploy.
param authMode = 'entra'
param entraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param entraClientId = '2ea7f6b8-d3c2-4dda-b806-32549efeadb6'
param publicBaseUrl = 'https://shell-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io'

// Phase 4: controlled read-only source integrations. Flip a service to
// 'live' ONLY after its Key Vault key exists:
//   recruitment-api  -> lever-api-key-dev        (Lever, GET-only)
//   people-api       -> bamboohr-api-key-dev  + bamboohrSubdomain (read-only)
// Left 'mock' until the DEV provider credentials are provisioned.
param recruitmentIntegrationsMode = 'live'
param peopleIntegrationsMode = 'live'
param bamboohrSubdomain = 'dijitalteam'

// Post-completion DEV improvement: real Microsoft Entra ID B2B guest sign-in
// for the Birthday Supplier Portal. supplierAuthMode=entra 404s the
// dev persona routes (/api/birthday/internal/dev/supplier-*). Requires the
// `birthday-supplier-entra-secret-dev` Key Vault secret (client secret of
// the `dijione-birthday-supplier-dev` app registration, appId below). A
// verified guest still gets NO access without an ACTIVE Birthday
// SupplierUser. Flip back to 'dev' + redeploy to restore the persona picker.
param supplierAuthMode = 'entra'
param supplierEntraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param supplierEntraClientId = '30e36193-f0e4-40d5-875b-db1ef6a3f2b0'
param supplierPublicBaseUrl = 'https://birthday-supplier-web.livelypebble-890e141a.southeastasia.azurecontainerapps.io'
