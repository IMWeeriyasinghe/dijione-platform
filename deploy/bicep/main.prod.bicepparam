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

// Phase 4: controlled read-only source integrations. Flip a service to
// 'live' ONLY after its Key Vault key exists:
//   recruitment-api  -> lever-api-key-prod        (Lever, GET-only)
//   people-api       -> bamboohr-api-key-prod  + bamboohrSubdomain (read-only)
// Validated first in UAT (339 real BambooHR employee records, 880 read /
// 1028 created Lever recruitment records, zero errors) before this flip.
param recruitmentIntegrationsMode = 'live'
param peopleIntegrationsMode = 'live'
param birthdayIntegrationsMode = 'live'
param bamboohrSubdomain = 'dijitalteam'

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
//
// PROD's own Entra app registrations now exist (confirmed values, no
// secrets here — client secrets live only in kv-dijione-prod as
// entra-client-secret-prod / birthday-supplier-entra-secret-prod, never in
// source control):
//   dijione-prod                     (internal DijiOne sign-in)
//   dijione-birthday-supplier-prod   (Birthday Supplier Portal B2B guest sign-in)
param authMode = 'entra'
param entraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param entraClientId = '98b1f056-68a2-492e-9d37-ae2e5eb0d218'
// Custom domain (docs/platform/... custom-domain auth remediation). The old
// shell-web.icybush-52a8142b... callback stays registered in Entra as a
// rollback fallback but is no longer the primary public URL.
param publicBaseUrl = 'https://dijione.dijitalteam.com'

param supplierAuthMode = 'entra'
param supplierEntraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param supplierEntraClientId = '572564e5-acad-495b-92e7-029ecabba8e7'
param supplierPublicBaseUrl = 'https://supplierportal.dijitalteam.com'
