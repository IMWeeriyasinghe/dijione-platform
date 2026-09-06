// The single Container Apps Environment for one DijiOne environment.
// Internal DNS: http://<app-name> resolves inside it. All DijiOne services
// (APIs, web zones, jobs) live in this one environment.
//
// Amendment 2: a WORKLOAD-PROFILES environment (Consumption profile only —
// bills identically to a Consumption-only environment, no fixed fee) so it can
// be VNet-integrated for private PostgreSQL. `infrastructureSubnetId` points at
// the ACA-delegated subnet from modules/network.bicep. The VNet choice is
// create-time and cannot be toggled later.

@description('Environment name, e.g. cae-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@description('Log Analytics customerId (workspace id).')
param logAnalyticsCustomerId string
@secure()
@description('Log Analytics primary shared key.')
param logAnalyticsSharedKey string

@description('ACA infrastructure subnet id (snet-aca, delegated Microsoft.App/environments). Empty = no VNet (escape hatch only).')
param infrastructureSubnetId string = ''

var vnetConfig = empty(infrastructureSubnetId) ? {} : {
  vnetConfiguration: {
    infrastructureSubnetId: infrastructureSubnetId
    internal: false
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: union(
    {
      appLogsConfiguration: {
        destination: 'log-analytics'
        logAnalyticsConfiguration: {
          customerId: logAnalyticsCustomerId
          sharedKey: logAnalyticsSharedKey
        }
      }
      // Consumption profile only — no Dedicated reservation, so no fixed fee.
      // A Dedicated profile can be added later without recreating the env.
      workloadProfiles: [
        {
          name: 'Consumption'
          workloadProfileType: 'Consumption'
        }
      ]
      zoneRedundant: false
    },
    vnetConfig
  )
}

output id string = env.id
output name string = env.name
output defaultDomain string = env.properties.defaultDomain
