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

// PROD sizing (Amendment 8): smallest validated container size, unchanged.
// PROD replica floors (2026-11 performance decision, Phase 1): the JWT issuer,
// the entry point and the module paths that showed user-visible 15–24 s cold
// starts keep one warm replica; everything else scales to zero. Raise further
// per the scaling-trigger table, not preemptively.
// KEEP IN STEP: atwork-release.bicep and onsite-release.bicep set the same PROD
// floors for the apps they own. deployAtwork/deployOnsite are false here, so
// the onsite-*/atwork-* entries only take effect if main.bicep ever deploys
// them — they exist so that path cannot revert PROD to scale-to-zero.
param containerCpu = '0.25'
param containerMemory = '0.5Gi'
param minReplicas = {
  'platform-api': 1
  'shell-web': 1
  'people-api': 1
  'birthday-api': 1
  'onsite-api': 1
  'onsite-web': 1
  'atwork-api': 1
  'atwork-web': 1
  // DijiTalentFlow (2026-11-13, same decision, Phase 1b): Home card + app page.
  'talent-api': 1
  'talent-web': 1
}
param maxReplicasDefault = 2
param maxReplicasOverrides = {
  'platform-api': 3
  'shell-web': 3
  // Same ceilings as the targeted release templates, so a main.bicep run
  // never changes them.
  'onsite-api': 1
  'onsite-web': 1
  'atwork-api': 1
  'atwork-web': 1
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
// Default module access needs a verified internal employee (docs/atwork/deployment.md).
param entraInternalEmailDomains = 'dijitalteam.com'
param supplierAuthMode = 'entra'
