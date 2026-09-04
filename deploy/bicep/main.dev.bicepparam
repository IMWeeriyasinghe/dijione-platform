using './main.bicep'

// DijiOne DEV. `imageTag` and `pgAdminPassword` are supplied at deploy time
// (deploy/deploy.sh) — never committed here.
param environmentName = 'dev'
param location = 'southeastasia'
param imageTag = 'REPLACED_AT_DEPLOY'
param pgAdminPassword = ''

// Full platform incl. DijiBirthday for the first DEV (confirmed).
param deployBirthday = true
param deployCommercial = false

// DEV exception: public PostgreSQL endpoint + "Allow Azure services" +
// sslmode=require. NO wide internet rule. UAT/PROD flip to 'private' and
// supply pgDelegatedSubnetId / pgPrivateDnsZoneId. See deploy/README.md.
param pgNetworkMode = 'public'

// talent-api min-1 for DEV acceptance responsiveness (cost lever: 0 later).
param minReplicas = {
  'shell-web': 1
  'platform-api': 1
  'talent-api': 1
}
