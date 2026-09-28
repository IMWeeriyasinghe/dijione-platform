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

// Phase 4: controlled read-only source integrations. Flip a service to
// 'live' ONLY after its Key Vault key exists:
//   recruitment-api  -> lever-api-key-uat        (Lever, GET-only)
//   people-api       -> bamboohr-api-key-uat  + bamboohrSubdomain (read-only)
param recruitmentIntegrationsMode = 'live'
param peopleIntegrationsMode = 'live'
param birthdayIntegrationsMode = 'live'
param bamboohrSubdomain = 'dijitalteam'

// Canonical client-directory sync (talent-api's clients extension rows,
// keyed on platform_client_id) — a one-time bootstrap task needed for the
// governed DTC tag -> Client resolution, NOT DEV persona/seeding behavior.
// seedDevIdentities is deliberately left at its default (false): UAT uses
// real Microsoft Entra sign-in (authMode=entra below), so the passwordless
// dev-login persona switcher must never be seeded/exposed here.
param seedTalentClientExtensions = true

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
// Custom domain (docs/platform/... custom-domain auth remediation). The old
// shell-web.mangofield-96838df7... callback stays registered in Entra as a
// rollback fallback but is no longer the primary public URL.
param publicBaseUrl = 'https://dijione-uat.dijitalteam.com'

param supplierAuthMode = 'entra'
param supplierEntraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param supplierEntraClientId = 'bdd98d91-1fe9-4b81-b621-96fa14d2e9b5'
param supplierPublicBaseUrl = 'https://supplierportal-uat.dijitalteam.com'

// id-dijione-uat already held "Key Vault Secrets User" on kv-dijione-uat
// before this template's identity module ever ran here (granted out-of-band
// during UAT bring-up) — under assignment id b7260736-9c22-4075-b254-95985f11206a,
// not the deterministic guid(kv.id, uami.id, roleId) modules/identity.bicep
// computes by default. Without this override, an incremental deployment
// tries to create a second, colliding assignment for the identical (scope,
// role, principal) and fails with RoleAssignmentExists. Pointing the module
// at the existing assignment id makes this idempotent instead.
param existingIdentityKvSecretsUserRoleAssignmentName = 'b7260736-9c22-4075-b254-95985f11206a'

// Same idempotency situation for id-dijione-uat's AcrPull grant on
// crdijionenonprod (rg-dijione-shared) — already existed under assignment id
// e9a143c7-fcbc-44dc-af44-393173e4ce66 before this template's acr-pull
// module ever ran here.
param existingIdentityAcrPullRoleAssignmentName = 'e9a143c7-fcbc-44dc-af44-393173e4ce66'
