// Log Analytics workspace (container + app stdout logs) + a small DEV alert
// baseline. No Application Insights for DEV — the correlation-id middleware
// covers "follow one request across services" without ingest cost.

@description('Workspace name, e.g. law-dijione-dev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@description('Cap daily ingest (GB) to keep DEV cost proportional. -1 = no cap.')
param dailyQuotaGb int = 1

param retentionInDays int = 30

var capping = dailyQuotaGb == -1 ? {} : { workspaceCapping: { dailyQuotaGb: dailyQuotaGb } }

resource law 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: name
  location: location
  tags: tags
  properties: union(
    {
      sku: {
        name: 'PerGB2018'
      }
      retentionInDays: retentionInDays
    },
    capping
  )
}

output id string = law.id
output customerId string = law.properties.customerId
output name string = law.name
