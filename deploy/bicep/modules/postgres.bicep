// Azure Database for PostgreSQL Flexible Server + one logical database per
// DB-owning domain. ONE server for DEV keeps the database-per-domain
// OWNERSHIP boundary (each service's DATABASE_URL points at its own db, no
// cross-db queries) while paying for one Burstable instance.
//
// NETWORKING (Amendment 2). Two modes, param-driven:
//   networkMode = 'public'  -> public endpoint + firewall "Allow Azure
//        services" + sslmode=require. Simplest/cheapest; the DEV exception.
//        NO broad 0.0.0.0-255.255.255.255 rule.
//   networkMode = 'private' -> the server is injected into a delegated
//        subnet and reached over a Private DNS zone; requires a VNet +
//        subnet delegated to Microsoft.DBforPostgreSQL/flexibleServers and
//        the ACA environment on a peers/adjacent subnet. UAT/PROD target.
// See deploy/README.md "PostgreSQL networking comparison".

@description('Server name, e.g. psql-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

param administratorLogin string = 'dijione'
@secure()
param administratorPassword string

param version string = '16'
param skuName string = 'Standard_B1ms'
param skuTier string = 'Burstable'
param storageSizeGB int = 32
param backupRetentionDays int = 7

@description('Logical databases to create, one per DB-owning domain.')
param databases array = [
  'platform_dev'
  'talent_dev'
  'recruitment_dev'
]

@allowed([ 'public', 'private' ])
param networkMode string = 'public'

@description('Only for networkMode == private: the delegated subnet resource id.')
param delegatedSubnetId string = ''

@description('Only for networkMode == private: the Private DNS zone resource id.')
param privateDnsZoneId string = ''

resource pg 'Microsoft.DBforPostgreSQL/flexibleServers@2023-12-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: skuName
    tier: skuTier
  }
  properties: {
    version: version
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorPassword
    storage: {
      storageSizeGB: storageSizeGB
    }
    backup: {
      backupRetentionDays: backupRetentionDays
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    network: networkMode == 'private'
      ? {
          delegatedSubnetResourceId: delegatedSubnetId
          privateDnsZoneArmResourceId: privateDnsZoneId
          publicNetworkAccess: 'Disabled'
        }
      : {
          publicNetworkAccess: 'Enabled'
        }
  }
}

// PgBouncer (transaction mode) — free, prevents B1ms's ~50-connection ceiling
// being exhausted by uvicorn workers x replicas.
resource pgbouncer 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2023-12-01-preview' = {
  parent: pg
  name: 'pgbouncer.enabled'
  properties: {
    value: 'true'
    source: 'user-override'
  }
}

// public mode only: allow other Azure services (the ACA env's egress is
// dynamic). This is NOT a wide internet rule.
resource allowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2023-12-01-preview' = if (networkMode == 'public') {
  parent: pg
  name: 'allow-azure-services'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource dbs 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2023-12-01-preview' = [
  for db in databases: {
    parent: pg
    name: db
    properties: {
      charset: 'UTF8'
      collation: 'en_US.utf8'
    }
  }
]

output serverName string = pg.name
output fqdn string = pg.properties.fullyQualifiedDomainName
