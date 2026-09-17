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

// Canonical client-directory sync (talent-api's clients extension rows,
// keyed on platform_client_id) — a one-time bootstrap task needed for the
// governed DTC tag -> Client resolution, NOT DEV persona/seeding behavior.
// seedDevIdentities is deliberately left at its default (false): PROD uses
// real Microsoft Entra sign-in (authMode=entra below), so the passwordless
// dev-login persona switcher must never be seeded/exposed here.
param seedTalentClientExtensions = true

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

// SECURITY: pinned explicitly (never left to main.bicep's default, which is
// 'dev') — an unset authMode/supplierAuthMode here would silently deploy
// PROD with the passwordless DEV_IDENTITY_MODE persona switcher exposed
// instead of real Microsoft Entra ID sign-in. Found during the
// PLATFORM_JWT_SECRET environment-cleanliness audit; see main.dev.bicepparam
// for the fully-wired reference (DEV itself already runs authMode=entra).
// entraTenantId / entraClientId / publicBaseUrl and the supplier equivalents
// are intentionally left unset here — they require PROD's own Entra app
// registrations, a human Entra-tenant action outside this repository's
// authority (CLAUDE.md). Until those are provisioned and these four params
// are filled in (plus the entra-client-secret-prod /
// birthday-supplier-entra-secret-prod Key Vault secrets), a PROD deployment
// attempt correctly FAILS rather than silently falling back to DEV identity
// mode.
param authMode = 'entra'
param supplierAuthMode = 'entra'
