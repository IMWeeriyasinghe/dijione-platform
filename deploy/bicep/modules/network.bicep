// DijiOne per-environment network for PRIVATE PostgreSQL (Amendment 2).
//
// Model: Flexible Server *Private access (VNet integration)* — NOT Private
// Link / Private Endpoint. The server is injected into a delegated subnet and
// reached over an Azure Private DNS zone ending in
// `.postgres.database.azure.com` (there is no `privatelink.*` zone and no
// `privateEndpoints` resource). The Container Apps environment is placed on
// its own delegated infrastructure subnet in the same VNet.
//
//   vnet-dijione-<env>           <vnetCidr>        (/21 — headroom, no peering)
//     ├─ snet-aca                <acaSubnetCidr>   (/23) delegated Microsoft.App/environments
//     └─ snet-postgres           <pgSubnetCidr>    (/27) delegated Microsoft.DBforPostgreSQL/flexibleServers
//   psql-dijione-<env>.private.postgres.database.azure.com   (Private DNS zone, linked to the VNet)

@description('dev | uat | prod — used in resource names.')
param environmentName string
param location string = resourceGroup().location
param tags object = {}

@description('VNet address space, e.g. 10.60.0.0/21. One /21 per environment, no peering.')
param vnetCidr string

@description('ACA infrastructure subnet, e.g. 10.60.0.0/23 (min /27 for a workload-profiles env; /23 recommended).')
param acaSubnetCidr string

@description('PostgreSQL delegated subnet, e.g. 10.60.4.0/27. Hosts only Flexible Servers.')
param pgSubnetCidr string

var vnetName = 'vnet-dijione-${environmentName}'
var pgDnsZoneName = 'psql-dijione-${environmentName}.private.postgres.database.azure.com'

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [ vnetCidr ]
    }
    subnets: [
      {
        name: 'snet-aca'
        properties: {
          addressPrefix: acaSubnetCidr
          delegations: [
            {
              name: 'aca'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: pgSubnetCidr
          delegations: [
            {
              name: 'pg'
              properties: {
                serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers'
              }
            }
          ]
        }
      }
    ]
  }
}

resource pgDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: pgDnsZoneName
  location: 'global'
  tags: tags
}

resource pgDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: pgDnsZone
  name: 'link-${vnetName}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: vnet.id
    }
  }
}

output vnetId string = vnet.id
output acaSubnetId string = vnet.properties.subnets[0].id
output pgSubnetId string = vnet.properties.subnets[1].id
output pgPrivateDnsZoneId string = pgDnsZone.id
