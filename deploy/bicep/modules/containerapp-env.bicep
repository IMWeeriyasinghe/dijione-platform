// The single Container Apps Environment for one DijiOne environment.
// Internal DNS: http://<app-name> resolves inside it. All DijiOne services
// (APIs, web zones, jobs) live in this one environment.

@description('Environment name, e.g. cae-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@description('Log Analytics customerId (workspace id).')
param logAnalyticsCustomerId string
@secure()
@description('Log Analytics primary shared key.')
param logAnalyticsSharedKey string

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    // DEV: no VNet, no zone redundancy, no environment-level mTLS
    // (latency; internal ingress is the boundary that matters).
    zoneRedundant: false
  }
}

output id string = env.id
output name string = env.name
output defaultDomain string = env.properties.defaultDomain
