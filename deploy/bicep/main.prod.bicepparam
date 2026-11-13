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
// Reconciled from 8dca96b (feat/onsite-dashboard-v1); equals live PROD env.
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
// Reconciled from d4efb92; the bootstrap-talent-clients job already exists in PROD.
param seedTalentClientExtensions = true

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
//
// PROD's own Entra app registrations exist (confirmed values, no secrets
// here — client secrets live only in kv-dijione-prod as
// entra-client-secret-prod / birthday-supplier-entra-secret-prod, never in
// source control):
//   dijione-prod                     (internal DijiOne sign-in)
//   dijione-birthday-supplier-prod   (Birthday Supplier Portal B2B guest sign-in)
// Reconciled from 9d1478b + 8dca96b; every value equals live PROD env
// (platform-api ENTRA_*, birthday-api SUPPLIER_ENTRA_*, shell-web
// PUBLIC_BASE_URL, birthday-supplier-web SUPPLIER_PUBLIC_BASE_URL).
param authMode = 'entra'
param entraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
// Default module access needs a verified internal employee (docs/atwork/deployment.md).
param entraInternalEmailDomains = 'dijitalteam.com'
param entraClientId = '98b1f056-68a2-492e-9d37-ae2e5eb0d218'
// Custom domain. The old shell-web.icybush-52a8142b... callback stays
// registered in Entra as a rollback fallback but is not the public URL.
param publicBaseUrl = 'https://dijione.dijitalteam.com'

param supplierAuthMode = 'entra'
param supplierEntraTenantId = '2abce006-6ea2-4675-b39d-33e0a54c46c7'
param supplierEntraClientId = '572564e5-acad-495b-92e7-029ecabba8e7'
param supplierPublicBaseUrl = 'https://supplierportal.dijitalteam.com'

// Custom-domain ingress bindings that exist live (DNS + managed certificate
// created out-of-band). Declared so a main.bicep run keeps them instead of
// silently removing them (ACA ingress is desired-state).
param customDomains = {
  'shell-web': [ { name: 'dijione.dijitalteam.com', certificateName: 'mc-cae-dijione-pr-dijione-dijitalt-2592' } ]
  'birthday-supplier-web': [ { name: 'supplierportal.dijitalteam.com', certificateName: 'mc-cae-dijione-pr-supplierportal-d-5970' } ]
}

// DijiBirthday outbound mail — equals live PROD birthday-api env (previously
// set ad hoc). PROD sends to the assigned supplier via birthday-api's own managed identity, Exchange RBAC-scoped to this one mailbox. Never internal_allowlist here (main.bicep refuses it).
param birthdayMailTransport = 'graph'
param birthdayMailPolicy = 'production'
param birthdayMailSharedMailbox = 'appassistant@dijitalteam.com'
