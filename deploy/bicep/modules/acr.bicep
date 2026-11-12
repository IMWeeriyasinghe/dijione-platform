// Azure Container Registry. Basic tier is enough for DijiOne DEV; the reason
// it is preferred over free GHCR is managed-identity pull — no registry
// credential is stored on any Container App.

@description('Registry name — alphanumeric only, 5-50 chars, e.g. crdijionedev.')
param name string
param location string = resourceGroup().location
param tags object = {}

@allowed([ 'Basic', 'Standard', 'Premium' ])
param sku string = 'Basic'

resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

output id string = acr.id
output loginServer string = acr.properties.loginServer
output name string = acr.name
